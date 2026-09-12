"""Lightweight readers for public IDX website endpoints used by Market Overview.

The endpoints mirror data shown on IDX Digital Statistics / stock screener pages.
No credentials are stored. Network/provider failures are surfaced to the UI.
"""
from __future__ import annotations

import base64
import json
import re
import time
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pandas as pd

BASES = ("https://www.idx.co.id", "https://www.idx.id")
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    "Referer": "https://www.idx.co.id/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}


class IDXProviderError(RuntimeError):
    pass


class _Session:
    """Browser-like HTTP session. Prefer curl_cffi, fall back to urllib."""

    def __init__(self):
        self.kind = "urllib"
        self.s = None
        try:
            from curl_cffi import requests as curl_requests  # type: ignore

            self.s = curl_requests.Session(impersonate="chrome")
            self.s.headers.update(HEADERS)
            self.kind = "curl"
        except Exception:
            import http.cookiejar
            import urllib.request

            jar = http.cookiejar.CookieJar()
            self.s = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            self.kind = "urllib"

    def get(self, url: str, timeout: int = 20) -> Any:
        if self.kind == "curl":
            r = self.s.get(url, timeout=timeout)
            r.raise_for_status()
            return r.json()
        import urllib.request

        req = urllib.request.Request(url, headers=HEADERS)
        with self.s.open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def warm(self, base: str) -> None:
        """Prime cookies. Failure here is non-fatal; the API call may still work."""
        try:
            if self.kind == "curl":
                self.s.get(base + "/id", timeout=10)
            else:
                import urllib.request

                req = urllib.request.Request(base + "/id", headers=HEADERS)
                self.s.open(req, timeout=10).close()
        except Exception:
            pass


def _get_json(path: str, *, retries: int = 2) -> Any:
    errors: list[str] = []
    for base in BASES:
        sess = _Session()
        sess.warm(base)
        url = base + path
        for attempt in range(retries):
            try:
                return sess.get(url)
            except Exception as exc:
                errors.append(f"{base}: {type(exc).__name__}: {str(exc)[:160]}")
                if attempt + 1 < retries:
                    time.sleep(0.6 * (attempt + 1))
    raise IDXProviderError("IDX request failed. " + " | ".join(errors[-4:]))


def _query_b64(year: int, month: int) -> str:
    payload = {"year": str(year), "month": str(month), "quarter": 0, "type": "monthly"}
    raw = json.dumps(payload, separators=(",", ":")).encode("ascii")
    return base64.b64encode(raw).decode("ascii")


def _number(v: Any) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    text = str(v).strip().replace(",", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _date_value(v: Any) -> pd.Timestamp:
    if v is None:
        return pd.NaT
    text = str(v)
    ms = re.search(r"/Date\((\d+)", text)
    if ms:
        return pd.to_datetime(int(ms.group(1)), unit="ms", errors="coerce")
    return pd.to_datetime(v, errors="coerce", dayfirst=False)


def _investor_raw(kind: str, year: int, month: int) -> list[dict[str, Any]]:
    if kind not in {"FOREIGN", "DOMESTIC"}:
        raise ValueError("kind must be FOREIGN or DOMESTIC")
    q = _query_b64(year, month)
    params = urlencode(
        {
            "urlName": f"LINK_TABLE_DAILY_TRADING_INVESTOR_{kind}",
            "query": q,
            "isPrint": "False",
            "cumulative": "false",
        }
    )
    raw = _get_json("/primary/DigitalStatistic/GetApiData?" + params)
    rows = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        raise IDXProviderError(f"IDX {kind.lower()} investor response has no data array.")
    return rows


def _investor_frame(kind: str, year: int, month: int) -> pd.DataFrame:
    rows = _investor_raw(kind, year, month)
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    if "date" not in d.columns:
        return pd.DataFrame()
    d["Date"] = d["date"].map(_date_value)
    d = d[d.Date.notna()].copy()
    return d


def fetch_latest_investor_flow(now: datetime | None = None) -> dict[str, Any]:
    """Return latest official IDX daily foreign/domestic buy/sell aggregates.

    Formulas come from the four counterparty buckets in IDX's daily trading by
    investor table:
      FF = foreign seller -> foreign buyer
      FD = foreign seller -> domestic buyer
      DF = domestic seller -> foreign buyer
      DD = domestic seller -> domestic buyer
    Therefore foreign buy = FF+DF, foreign sell = FF+FD, etc.
    """
    now = now or datetime.now(ZoneInfo("Asia/Jakarta"))
    candidates: list[tuple[int, int]] = [(now.year, now.month)]
    prev = (now.replace(day=1) - timedelta(days=1))
    candidates.append((prev.year, prev.month))

    last_error: Exception | None = None
    for year, month in candidates:
        try:
            foreign = _investor_frame("FOREIGN", year, month)
            domestic = _investor_frame("DOMESTIC", year, month)
            if foreign.empty or domestic.empty:
                continue
            f = foreign.set_index("Date")
            d = domestic.set_index("Date")
            common = f.index.intersection(d.index)
            common = common[common.date <= now.date()]
            if len(common) == 0:
                continue
            day = max(common)
            fr = f.loc[day]
            dr = d.loc[day]
            if isinstance(fr, pd.DataFrame):
                fr = fr.iloc[-1]
            if isinstance(dr, pd.DataFrame):
                dr = dr.iloc[-1]

            ff = {
                "value": _number(fr.get("foreignForeignValue")),
                "volume": _number(fr.get("foreignForeignVolume")),
                "frequency": _number(fr.get("foreignForeignFreq")),
            }
            fd = {
                "value": _number(fr.get("foreignDomesticValue")),
                "volume": _number(fr.get("foreignDomesticVolume")),
                "frequency": _number(fr.get("foreignDomesticFreq")),
            }
            df = {
                "value": _number(dr.get("domesticForeignValue")),
                "volume": _number(dr.get("domesticForeignVolume")),
                "frequency": _number(dr.get("domesticForeignFreq")),
            }
            dd = {
                "value": _number(dr.get("domesticDomesticValue")),
                "volume": _number(dr.get("domesticDomesticVolume")),
                "frequency": _number(dr.get("domesticDomesticFreq")),
            }

            metrics: dict[str, Any] = {}
            for metric in ("value", "volume", "frequency"):
                f_buy = ff[metric] + df[metric]
                f_sell = ff[metric] + fd[metric]
                d_buy = dd[metric] + fd[metric]
                d_sell = dd[metric] + df[metric]
                metrics[metric] = {
                    "foreign_buy": f_buy,
                    "foreign_sell": f_sell,
                    "foreign_net": f_buy - f_sell,
                    "domestic_buy": d_buy,
                    "domestic_sell": d_sell,
                    "domestic_net": d_buy - d_sell,
                }
            return {
                "date": pd.Timestamp(day).date().isoformat(),
                "metrics": metrics,
                "source": "IDX Digital Statistics",
            }
        except Exception as exc:
            last_error = exc
    if last_error:
        raise IDXProviderError(str(last_error))
    raise IDXProviderError("IDX investor table returned no usable current or prior-month rows.")


def fetch_stock_screener_metadata() -> pd.DataFrame:
    """Fetch official IDX stock screener metadata: ticker, sector, market cap."""
    raw = _get_json("/support/stock-screener/api/v1/stock-screener/get?Sector=&SubSector=")
    rows = raw.get("results") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        raise IDXProviderError("IDX stock screener response has no results array.")
    out = []
    for item in rows:
        code = str(item.get("stockCode", "")).strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{4}", code):
            continue
        out.append(
            {
                "Symbol": code,
                "Company": str(item.get("companyName") or code),
                "Sector": str(item.get("sector") or "Other IDX"),
                "SubSector": str(item.get("subSector") or ""),
                "MarketCap": _number(item.get("marketCapital")),
            }
        )
    if not out:
        raise IDXProviderError("IDX stock screener returned no usable stocks.")
    return pd.DataFrame(out).drop_duplicates("Symbol", keep="last")


def _stock_summary_for_date(day: date) -> pd.DataFrame:
    date_str = day.strftime("%Y%m%d")
    raw = _get_json("/primary/TradingSummary/GetStockSummary?" + urlencode({"date": date_str}))
    rows = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(rows, list) or not rows:
        return pd.DataFrame()
    out = []
    for item in rows:
        code = str(item.get("StockCode", "")).strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{4}", code):
            continue
        previous = _number(item.get("Previous"))
        close = _number(item.get("Close"))
        change = _number(item.get("Change"))
        pct = (change / previous * 100.0) if previous else 0.0
        listed = _number(item.get("ListedShares"))
        out.append(
            {
                "Symbol": code,
                "CompanySummary": str(item.get("StockName") or code),
                "Date": str(item.get("Date") or day.isoformat()),
                "Previous": previous,
                "Close": close,
                "Change": change,
                "ChangePct": pct,
                "Volume": _number(item.get("Volume")),
                "TradedValue": _number(item.get("Value")),
                "Frequency": _number(item.get("Frequency")),
                "ForeignBuy": _number(item.get("ForeignBuy")),
                "ForeignSell": _number(item.get("ForeignSell")),
                "ListedShares": listed,
                "CalculatedMarketCap": close * listed if close > 0 and listed > 0 else 0.0,
            }
        )
    return pd.DataFrame(out)


def fetch_latest_idx_market(now: datetime | None = None, lookback_days: int = 12) -> pd.DataFrame:
    """Fetch the latest non-empty whole-IDX daily stock summary."""
    now = now or datetime.now(ZoneInfo("Asia/Jakarta"))
    start = now.date()
    errors: list[str] = []
    for offset in range(lookback_days + 1):
        day = start - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        try:
            d = _stock_summary_for_date(day)
            if not d.empty:
                return d
        except Exception as exc:
            errors.append(f"{day}: {str(exc)[:100]}")
    raise IDXProviderError("No recent IDX stock summary found. " + " | ".join(errors[-3:]))


def build_idx_heatmap_dataset(now: datetime | None = None) -> tuple[pd.DataFrame, str]:
    """Merge official daily stock summary with official sector/market-cap metadata."""
    summary = fetch_latest_idx_market(now=now)
    metadata_error = None
    try:
        meta = fetch_stock_screener_metadata()
    except Exception as exc:
        metadata_error = str(exc)
        meta = pd.DataFrame(columns=["Symbol", "Company", "Sector", "SubSector", "MarketCap"])

    d = summary.merge(meta, on="Symbol", how="left")
    d["Company"] = d.get("Company", pd.Series(index=d.index, dtype=object)).fillna(d["CompanySummary"])
    d["Sector"] = d.get("Sector", pd.Series(index=d.index, dtype=object)).fillna("Other IDX")
    if "MarketCap" not in d:
        d["MarketCap"] = 0.0
    d["MarketCap"] = pd.to_numeric(d["MarketCap"], errors="coerce").fillna(0.0)
    d.loc[d.MarketCap <= 0, "MarketCap"] = d.loc[d.MarketCap <= 0, "CalculatedMarketCap"]
    d = d[(d.Close > 0) & (d.MarketCap > 0)].copy()
    d["ColorChange"] = d.ChangePct.clip(-7, 7)
    if d.empty:
        raise IDXProviderError("IDX summary returned no stocks suitable for heatmap.")
    date_label = pd.to_datetime(summary.Date, errors="coerce").max()
    stamp = date_label.date().isoformat() if pd.notna(date_label) else "latest"
    note = f"Official IDX · {stamp}"
    if metadata_error:
        note += " · sector metadata unavailable; fallback grouping used"
    return d, note
