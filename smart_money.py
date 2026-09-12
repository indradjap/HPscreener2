from __future__ import annotations

import html
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from idx_official import fetch_idx_market_history, fetch_stock_screener_metadata
from yahoo_download import download_universe


PRESETS = {
    "Foreign Accumulation": {
        "description": "Find liquid stocks where IDX foreign-flow imbalance is persistently positive.",
        "accent": "green",
    },
    "Money Flow Accumulation": {
        "description": "Find stocks with improving price-volume money flow before a large price expansion.",
        "accent": "green",
    },
    "Technical Breakout": {
        "description": "Find liquid stocks breaking prior resistance or confirming an improving trend with volume.",
        "accent": "blue",
    },
    "Smart Money + Technical": {
        "description": "Require accumulation evidence together with constructive trend and momentum confirmation.",
        "accent": "green",
    },
}


def _fmt_compact(value: float) -> str:
    value = float(value or 0.0)
    av = abs(value)
    if av >= 1e12:
        return f"{value/1e12:.2f}T"
    if av >= 1e9:
        return f"{value/1e9:.2f}B"
    if av >= 1e6:
        return f"{value/1e6:.2f}M"
    if av >= 1e3:
        return f"{value/1e3:.1f}K"
    return f"{value:,.0f}"


def _quality_universe() -> tuple[str, ...]:
    d = pd.read_csv(Path(__file__).with_name("idx_quality_200.csv"))
    symbols = tuple(dict.fromkeys(d["Ticker"].astype(str).str.upper().str.strip()))
    if len(symbols) != 200:
        raise ValueError("Quality universe must contain 200 unique tickers.")
    return symbols


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out = out.mask((avg_loss == 0) & (avg_gain > 0), 100)
    out = out.mask((avg_loss == 0) & (avg_gain == 0), 50)
    return out


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def _technical_row(symbol: str, raw: pd.DataFrame) -> dict | None:
    d = raw.copy()
    d.columns = [str(c).title() for c in d.columns]
    needed = ["Open", "High", "Low", "Close", "Volume"]
    if not set(needed).issubset(d.columns):
        return None
    d = d[needed].dropna().copy()
    if len(d) < 60:
        return None

    c = pd.to_numeric(d.Close, errors="coerce")
    h = pd.to_numeric(d.High, errors="coerce")
    l = pd.to_numeric(d.Low, errors="coerce")
    v = pd.to_numeric(d.Volume, errors="coerce").fillna(0)
    if c.isna().all() or float(c.iloc[-1]) <= 0:
        return None

    ma20 = c.rolling(20).mean()
    ma50 = c.rolling(50).mean()
    ma200 = c.rolling(200).mean()
    rsi = _rsi(c, 14)
    rlow = rsi.rolling(14).min()
    rhigh = rsi.rolling(14).max()
    stoch = (rsi - rlow) / (rhigh - rlow).replace(0, np.nan) * 100
    stoch_k = stoch.rolling(3).mean()
    stoch_d = stoch_k.rolling(3).mean()

    typical = (h + l + c) / 3.0
    spread = (h - l).replace(0, np.nan)
    mfv = (((c - l) - (h - c)) / spread).fillna(0) * v
    direction = np.sign(c.diff()).fillna(0)
    obv = (direction * v).cumsum()

    ema12 = _ema(c, 12)
    ema26 = _ema(c, 26)
    macd = ema12 - ema26
    signal = _ema(macd, 9)
    hist = macd - signal

    close = float(c.iloc[-1])
    m20 = float(ma20.iloc[-1]) if pd.notna(ma20.iloc[-1]) else np.nan
    m50 = float(ma50.iloc[-1]) if pd.notna(ma50.iloc[-1]) else np.nan
    m200 = float(ma200.iloc[-1]) if pd.notna(ma200.iloc[-1]) else np.nan
    above200 = bool(pd.notna(m200) and close > m200)
    trend = bool(pd.notna(m20) and pd.notna(m50) and close > m20 > m50)
    macd_positive = bool(pd.notna(hist.iloc[-1]) and hist.iloc[-1] > 0)

    row = {
        "Symbol": symbol,
        "Close": close,
        "RSI": float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else np.nan,
        "StochK": float(stoch_k.iloc[-1]) if pd.notna(stoch_k.iloc[-1]) else np.nan,
        "StochD": float(stoch_d.iloc[-1]) if pd.notna(stoch_d.iloc[-1]) else np.nan,
        "MA20": m20,
        "MA50": m50,
        "MA200": m200,
        "AboveMA200": above200,
        "Trend": trend,
        "MACDPositive": macd_positive,
        "YahooDate": pd.Timestamp(d.index[-1]).date().isoformat() if isinstance(d.index, pd.DatetimeIndex) else "",
    }

    for n in (5, 10, 20, 60):
        ret = (c.iloc[-1] / c.iloc[-n-1] - 1) * 100 if len(c) >= n + 1 and c.iloc[-n-1] else np.nan
        value_b = float((c * v).tail(n).mean() / 1e9)

        vwap_n = (typical * v).rolling(n).sum() / v.rolling(n).sum().replace(0, np.nan)
        vw = float(vwap_n.iloc[-1]) if pd.notna(vwap_n.iloc[-1]) else np.nan
        vwap_pct = ((close / vw) - 1) * 100 if pd.notna(vw) and vw else np.nan

        cmf_n = mfv.rolling(n).sum() / v.rolling(n).sum().replace(0, np.nan)
        cmf = float(cmf_n.iloc[-1]) if pd.notna(cmf_n.iloc[-1]) else np.nan

        prev_vol = v.shift(1).rolling(n).mean()
        relvol = v.iloc[-1] / prev_vol.iloc[-1] if len(v) >= n + 1 and prev_vol.iloc[-1] > 0 else np.nan
        rv = float(relvol) if pd.notna(relvol) else np.nan

        prior_high = h.shift(1).rolling(n).max()
        breakout = bool(pd.notna(prior_high.iloc[-1]) and close > prior_high.iloc[-1])
        obv_up = bool(len(obv) >= n + 1 and obv.iloc[-1] > obv.iloc[-n-1])

        flow_checks = [
            cmf > 0 if pd.notna(cmf) else False,
            obv_up,
            rv >= 1.2 if pd.notna(rv) else False,
            vwap_pct >= 0 if pd.notna(vwap_pct) else False,
            close > m20 if pd.notna(m20) else False,
            macd_positive,
        ]
        money_flow_score = round(sum(flow_checks) / len(flow_checks) * 100)

        row[f"Return{n}"] = float(ret) if pd.notna(ret) else np.nan
        row[f"Value{n}B"] = value_b
        row[f"VWAPPct{n}"] = float(vwap_pct) if pd.notna(vwap_pct) else np.nan
        row[f"CMF{n}"] = cmf
        row[f"RelVolume{n}"] = rv
        row[f"Breakout{n}"] = breakout
        row[f"OBVUp{n}"] = obv_up
        row[f"MoneyFlowScore{n}"] = money_flow_score

    return row

def _foreign_metrics(history: pd.DataFrame) -> pd.DataFrame:
    base_cols = ["Symbol", "CompanyIDX", "IDXDate"]
    dyn_cols = []
    for n in (5, 10, 20, 60):
        dyn_cols += [f"ForeignNet{n}", f"ForeignIntensity{n}", f"ForeignPositiveDays{n}"]
    if history is None or history.empty:
        return pd.DataFrame(columns=base_cols + dyn_cols)

    d = history.copy()
    d["ForeignBuy"] = pd.to_numeric(d.ForeignBuy, errors="coerce").fillna(0.0)
    d["ForeignSell"] = pd.to_numeric(d.ForeignSell, errors="coerce").fillna(0.0)
    d["ForeignNet"] = d.ForeignBuy - d.ForeignSell
    d["ForeignGross"] = d.ForeignBuy.abs() + d.ForeignSell.abs()

    rows = []
    for symbol, g in d.groupby("Symbol"):
        g = g.sort_values("SessionDate").tail(60)
        if g.empty:
            continue

        latest_company = str(g.iloc[-1].get("CompanySummary") or symbol)
        row = {
            "Symbol": symbol,
            "CompanyIDX": latest_company,
            "IDXDate": pd.to_datetime(g.SessionDate).max().date().isoformat(),
        }
        for n in (5, 10, 20, 60):
            w = g.tail(n)
            net = float(w.ForeignNet.sum())
            gross = float(w.ForeignGross.sum())
            row[f"ForeignNet{n}"] = net
            row[f"ForeignIntensity{n}"] = net / gross * 100 if gross > 0 else 0.0
            row[f"ForeignPositiveDays{n}"] = int((w.ForeignNet > 0).sum())
        rows.append(row)

    return pd.DataFrame(rows)

def _idx_stage1_metrics(history: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """Build whole-IDX pre-screen metrics before any Yahoo history is requested."""
    if history is None or history.empty:
        return pd.DataFrame()

    d = history.copy()
    for col in ("Close", "Volume", "TradedValue", "Frequency", "ForeignBuy", "ForeignSell"):
        d[col] = pd.to_numeric(d.get(col), errors="coerce").fillna(0.0)
    d["ForeignNet"] = d["ForeignBuy"] - d["ForeignSell"]
    d["ForeignGross"] = d["ForeignBuy"].abs() + d["ForeignSell"].abs()

    rows = []
    for symbol, g in d.groupby("Symbol"):
        g = g.sort_values("SessionDate").tail(60).copy()
        if g.empty:
            continue
        latest = g.iloc[-1]
        row = {
            "Symbol": symbol,
            "CompanyIDX": str(latest.get("CompanySummary") or symbol),
            "IDXDate": pd.to_datetime(g.SessionDate).max().date().isoformat(),
            "IDXClose": float(latest.Close),
            "IDXFrequency": float(latest.Frequency),
        }

        for n in (5, 10, 20, 60):
            w = g.tail(n)
            avg_value_b = float(w.TradedValue.mean() / 1e9) if not w.empty else 0.0
            prior_vol = g.iloc[:-1].tail(n).Volume
            relvol = float(latest.Volume / prior_vol.mean()) if len(prior_vol) and prior_vol.mean() > 0 else np.nan

            first_close = float(w.Close.iloc[0]) if len(w) else 0.0
            ret = ((float(latest.Close) / first_close) - 1) * 100 if first_close > 0 else np.nan
            prior_close_high = g.iloc[:-1].tail(n).Close.max() if len(g) > 1 else np.nan
            close_breakout = bool(pd.notna(prior_close_high) and float(latest.Close) > float(prior_close_high))

            net = float(w.ForeignNet.sum())
            gross = float(w.ForeignGross.sum())
            row[f"IDXValue{n}B"] = avg_value_b
            row[f"IDXRelVolume{n}"] = relvol
            row[f"IDXReturn{n}"] = float(ret) if pd.notna(ret) else np.nan
            row[f"IDXCloseBreakout{n}"] = close_breakout
            row[f"ForeignNet{n}"] = net
            row[f"ForeignIntensity{n}"] = net / gross * 100 if gross > 0 else 0.0
            row[f"ForeignPositiveDays{n}"] = int((w.ForeignNet > 0).sum())

        rows.append(row)

    stage = pd.DataFrame(rows)
    if stage.empty:
        return stage

    if meta is not None and not meta.empty:
        stage = stage.merge(meta, on="Symbol", how="left")
    if "Company" not in stage:
        stage["Company"] = np.nan
    if "Sector" not in stage:
        stage["Sector"] = np.nan
    if "SubSector" not in stage:
        stage["SubSector"] = np.nan
    stage["Company"] = stage["Company"].fillna(stage["CompanyIDX"]).fillna(stage.Symbol)
    stage["Sector"] = stage["Sector"].fillna("IDX")
    stage["SubSector"] = stage["SubSector"].fillna("")
    return stage.reset_index(drop=True)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_idx_smart_base() -> tuple[pd.DataFrame, dict]:
    """Fetch the whole IDX universe once and build stage-1 metrics."""
    idx_hist = fetch_idx_market_history(sessions=60, max_calendar_days=100)
    try:
        meta = fetch_stock_screener_metadata()[["Symbol", "Company", "Sector", "SubSector"]].copy()
        meta_error = None
    except Exception as exc:
        meta = pd.DataFrame(columns=["Symbol", "Company", "Sector", "SubSector"])
        meta_error = str(exc)

    stage = _idx_stage1_metrics(idx_hist, meta)
    if stage.empty:
        raise ValueError("IDX returned no usable whole-market stage-1 data.")

    dates = [x for x in stage.IDXDate.dropna().astype(str) if x]
    status = {
        "idx_as_of": max(dates) if dates else "latest",
        "idx_total": int(stage.Symbol.nunique()),
        "meta_error": meta_error,
    }
    return stage, status


def _stage1_candidates(
    stage: pd.DataFrame,
    *,
    universe: str,
    lookback: int,
    min_value_b: float,
    setup: str,
    custom_cfg: dict | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Screen every requested IDX stock using cheap official-IDX metrics first."""
    x = stage.copy()
    if universe == "Quality 200":
        quality = set(_quality_universe())
        x = x[x.Symbol.isin(quality)].copy()

    universe_count = int(x.Symbol.nunique())
    value_col = f"IDXValue{lookback}B"
    relvol_col = f"IDXRelVolume{lookback}"
    breakout_col = f"IDXCloseBreakout{lookback}"
    foreign_col = f"ForeignNet{lookback}"
    intensity_col = f"ForeignIntensity{lookback}"

    x = x[pd.to_numeric(x[value_col], errors="coerce").fillna(0) >= float(min_value_b)].copy()
    liquid_count = int(x.Symbol.nunique())

    # Keep stage 1 as a broad/safe superset of the final Yahoo-based screen.
    if setup == "Foreign Accumulation":
        x = x[
            (x[intensity_col].fillna(0) > 0)
            & (x[foreign_col].fillna(0) > 0)
            & (x["ForeignNet5"].fillna(0) > 0)
        ]
    elif setup == "Technical Breakout":
        x = x[
            x[breakout_col].fillna(False)
            | (x[relvol_col].fillna(0) >= 1.0)
            | (x[f"IDXReturn{lookback}"].fillna(0) > 0)
        ]
    elif setup == "Smart Money + Technical":
        x = x[
            (x[intensity_col].fillna(0) > 0)
            & (
                (x[relvol_col].fillna(0) >= 0.8)
                | (x[f"IDXReturn{lookback}"].fillna(0) >= 0)
            )
        ]
    elif setup == "Custom Screen":
        cfg = custom_cfg or {}
        if cfg.get("foreign"):
            x = x[x[foreign_col].fillna(0) > 0]
        if cfg.get("breakout"):
            x = x[x[breakout_col].fillna(False)]
        if float(cfg.get("relvol", 0) or 0) > 0:
            x = x[x[relvol_col].fillna(0) >= float(cfg["relvol"])]
    # Money Flow Accumulation intentionally has no extra IDX pre-filter:
    # CMF/OBV require historical OHLCV, so all liquid stocks proceed to Yahoo.

    # More active names first makes Yahoo partial failures less damaging.
    x = x.sort_values(
        [value_col, relvol_col, intensity_col],
        ascending=[False, False, False],
        na_position="last",
    )
    status = {
        "universe_count": universe_count,
        "liquid_count": liquid_count,
        "candidate_count": int(x.Symbol.nunique()),
    }
    return x.reset_index(drop=True), status


@st.cache_data(ttl=1800, show_spinner=False)
def cached_yahoo_technical_dataset(symbols: tuple[str, ...]) -> tuple[pd.DataFrame, dict]:
    if not symbols:
        return pd.DataFrame(), {}
    frames, errors = download_universe(symbols, period="2y", chunk_size=60)
    rows = []
    for symbol in symbols:
        raw = frames.get(symbol + ".JK")
        if raw is None:
            continue
        row = _technical_row(symbol, raw)
        if row:
            rows.append(row)
    return pd.DataFrame(rows), errors


def build_smart_money_dataset(
    *,
    universe: str,
    lookback: int,
    min_value_b: float,
    setup: str,
    custom_cfg: dict | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Two-stage whole-market screen: IDX pre-filter -> Yahoo technical confirmation."""
    stage, idx_status = cached_idx_smart_base()
    candidates, stage_status = _stage1_candidates(
        stage,
        universe=universe,
        lookback=lookback,
        min_value_b=min_value_b,
        setup=setup,
        custom_cfg=custom_cfg,
    )
    symbols = tuple(candidates.Symbol.astype(str).tolist())

    tech, yahoo_errors = cached_yahoo_technical_dataset(symbols)
    if tech.empty:
        d = tech.copy()
    else:
        foreign_cols = ["Symbol", "Company", "Sector", "SubSector", "IDXDate"]
        for n in (5, 10, 20, 60):
            foreign_cols += [
                f"ForeignNet{n}",
                f"ForeignIntensity{n}",
                f"ForeignPositiveDays{n}",
            ]
        foreign_cols = [c for c in foreign_cols if c in candidates.columns]
        d = tech.merge(candidates[foreign_cols], on="Symbol", how="left")

        d["Company"] = d.get("Company", pd.Series(index=d.index, dtype=object)).fillna(d.Symbol)
        d["Sector"] = d.get("Sector", pd.Series(index=d.index, dtype=object)).fillna("IDX")

        for n in (5, 10, 20, 60):
            for col in (f"ForeignNet{n}", f"ForeignIntensity{n}", f"ForeignPositiveDays{n}"):
                if col not in d:
                    d[col] = np.nan

            foreign_score = np.clip(
                (d[f"ForeignIntensity{n}"].fillna(0) + 10) / 20 * 100,
                0,
                100,
            )
            tech_score = (
                d.Trend.astype(int) * 30
                + d.AboveMA200.astype(int) * 15
                + d[f"Breakout{n}"].astype(int) * 20
                + d.MACDPositive.astype(int) * 15
                + (d[f"RelVolume{n}"].fillna(0) >= 1.2).astype(int) * 20
            )
            d[f"SmartScore{n}"] = (
                0.35 * d[f"MoneyFlowScore{n}"]
                + 0.30 * foreign_score
                + 0.35 * tech_score
            ).round().clip(0, 100)

    yahoo_dates = []
    idx_dates = []
    if not d.empty:
        yahoo_dates = [x for x in d.YahooDate.dropna().astype(str) if x]
        if "IDXDate" in d:
            idx_dates = [x for x in d.IDXDate.dropna().astype(str) if x]

    status = {
        "as_of": max(yahoo_dates + idx_dates) if (yahoo_dates or idx_dates) else idx_status.get("idx_as_of", "latest"),
        "universe": universe,
        "idx_total": idx_status.get("idx_total", 0),
        "stage1_universe": stage_status["universe_count"],
        "stage1_liquid": stage_status["liquid_count"],
        "stage1_candidates": stage_status["candidate_count"],
        "yahoo_ok": int(d.Symbol.nunique()) if not d.empty else 0,
        "yahoo_failed": len(yahoo_errors),
        "idx_foreign_available": True,
        "meta_error": idx_status.get("meta_error"),
    }
    return d.reset_index(drop=True), status

def _lookback_view(d: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Expose selected 5D/10D/20D/60D metrics through the existing screen columns."""
    if lookback not in (5, 10, 20, 60):
        raise ValueError("Unsupported Smart Money lookback.")

    x = d.copy()
    mapping = {
        "Return20": f"Return{lookback}",
        "Value20B": f"Value{lookback}B",
        "VWAPPct": f"VWAPPct{lookback}",
        "CMF20": f"CMF{lookback}",
        "RelVolume": f"RelVolume{lookback}",
        "Breakout20": f"Breakout{lookback}",
        "OBVUp": f"OBVUp{lookback}",
        "MoneyFlowScore": f"MoneyFlowScore{lookback}",
        "ForeignNet20": f"ForeignNet{lookback}",
        "ForeignIntensity20": f"ForeignIntensity{lookback}",
        "ForeignPositiveDays": f"ForeignPositiveDays{lookback}",
        "SmartScore": f"SmartScore{lookback}",
    }
    for target, source in mapping.items():
        x[target] = x[source] if source in x.columns else np.nan

    # Short-term confirmation remains the latest 5 sessions for all horizons.
    x["ForeignNet5"] = x["ForeignNet5"] if "ForeignNet5" in x.columns else np.nan
    return x


def _preset_filter(d: pd.DataFrame, preset: str, min_value_b: float) -> pd.DataFrame:
    x = d[d.Value20B >= min_value_b].copy()
    if preset == "Foreign Accumulation":
        x = x[(x.ForeignIntensity20 >= 2.0) & (x.ForeignNet20 > 0) & (x.ForeignNet5 > 0)]
        return x.sort_values(["ForeignIntensity20", "SmartScore"], ascending=False)
    if preset == "Money Flow Accumulation":
        x = x[(x.MoneyFlowScore >= 60) & (x.CMF20 > 0) & x.OBVUp]
        return x.sort_values(["MoneyFlowScore", "SmartScore"], ascending=False)
    if preset == "Technical Breakout":
        x = x[(x.Breakout20 | (x.Trend & (x.RelVolume >= 1.2))) & x.MACDPositive]
        return x.sort_values(["Breakout20", "RelVolume", "SmartScore"], ascending=False)
    x = x[(x.ForeignIntensity20 > 0) & (x.CMF20 > 0) & x.Trend & x.MACDPositive]
    return x.sort_values(["SmartScore", "ForeignIntensity20"], ascending=False)


def _custom_filter(d: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    x = d[d.Value20B >= cfg["min_value"]].copy()
    x = x[x.RSI.between(cfg["rsi_min"], cfg["rsi_max"], inclusive="both")]
    x = x[x.RelVolume.fillna(0) >= cfg["relvol"]]
    if cfg["trend"]:
        x = x[x.Trend]
    if cfg["foreign"]:
        x = x[x.ForeignNet20.fillna(0) > 0]
    if cfg["moneyflow"]:
        x = x[x.CMF20.fillna(-999) > 0]
    if cfg["breakout"]:
        x = x[x.Breakout20]
    return x.sort_values("SmartScore", ascending=False)


def _chip(text: str, kind: str = "neutral") -> str:
    return f'<span class="sm-chip sm-{kind}">{html.escape(text)}</span>'


def _technical_chips(r: pd.Series) -> str:
    parts = []
    if pd.notna(r.RSI):
        parts.append(_chip(f"RSI {r.RSI:.1f}"))
    if pd.notna(r.StochK):
        parts.append(_chip(f"Stoch {r.StochK:.1f}"))
    parts.append(_chip("MA20 +" if r.Close > r.MA20 else "MA20 −", "good" if r.Close > r.MA20 else "bad"))
    parts.append(_chip("MA50 +" if r.Close > r.MA50 else "MA50 −", "good" if r.Close > r.MA50 else "bad"))
    if pd.notna(r.MA200):
        parts.append(_chip("MA200 +" if r.AboveMA200 else "MA200 −", "good" if r.AboveMA200 else "bad"))
    if pd.notna(r.VWAPPct):
        parts.append(_chip(f"VWAP {r.VWAPPct:+.1f}%", "good" if r.VWAPPct >= 0 else "bad"))
    return '<div class="sm-chip-wrap">' + ''.join(parts) + '</div>'


def _signal_chips(r: pd.Series) -> str:
    parts = []
    if pd.notna(r.ForeignIntensity20):
        parts.append(_chip(f"Foreign {r.ForeignIntensity20:+.1f}%", "good" if r.ForeignIntensity20 > 0 else "bad"))
    if pd.notna(r.CMF20):
        parts.append(_chip(f"CMF {r.CMF20:+.2f}", "good" if r.CMF20 > 0 else "bad"))
    if pd.notna(r.RelVolume):
        parts.append(_chip(f"RelVol {r.RelVolume:.2f}×", "good" if r.RelVolume >= 1.2 else "neutral"))
    if r.Breakout20:
        parts.append(_chip("Lookback breakout", "good"))
    if r.OBVUp:
        parts.append(_chip("OBV ↑", "good"))
    return '<div class="sm-chip-wrap">' + ''.join(parts) + '</div>'


def _action_meaning(r: pd.Series, setup: str) -> tuple[str, str, str]:
    """Short descriptive interpretation; deliberately not a buy/sell recommendation."""
    score = float(r.get("SmartScore", 0) or 0)
    if score >= 75:
        level, kind = "STRONG", "strong"
    elif score >= 55:
        level, kind = "DEVELOPING", "developing"
    else:
        level, kind = "EARLY", "early"

    if setup == "Foreign Accumulation":
        if float(r.get("ForeignIntensity20", 0) or 0) >= 5 and float(r.get("ForeignNet5", 0) or 0) > 0:
            text = "Foreign accumulation is persistent; watch for price and volume confirmation."
        else:
            text = "Foreign flow is positive, but accumulation strength is still developing."
    elif setup == "Money Flow Accumulation":
        if bool(r.get("OBVUp", False)) and float(r.get("CMF20", 0) or 0) > 0:
            text = "CMF and OBV point to accumulation pressure before a larger price move."
        else:
            text = "Money flow is improving, but confirmation across volume signals is mixed."
    elif setup == "Technical Breakout":
        if bool(r.get("Breakout20", False)) and float(r.get("RelVolume", 0) or 0) >= 1.2:
            text = "Breakout is volume-confirmed; watch whether price holds above prior resistance."
        elif bool(r.get("Trend", False)):
            text = "Trend is strengthening, but this is not yet a fully confirmed fresh breakout."
        else:
            text = "Breakout evidence is early; confirmation from trend and volume is still limited."
    elif setup == "Smart Money + Technical":
        if float(r.get("ForeignIntensity20", 0) or 0) > 0 and bool(r.get("Trend", False)) and bool(r.get("MACDPositive", False)):
            text = "Flow, trend and momentum are aligned; this is a higher-quality confirmation setup."
        else:
            text = "Some smart-money and technical evidence aligns, but confirmation is incomplete."
    else:
        pieces = []
        if float(r.get("ForeignIntensity20", 0) or 0) > 0:
            pieces.append("foreign flow positive")
        if float(r.get("CMF20", 0) or 0) > 0:
            pieces.append("money flow positive")
        if bool(r.get("Trend", False)):
            pieces.append("trend constructive")
        if bool(r.get("Breakout20", False)):
            pieces.append("breakout active")
        text = ("Custom screen: " + ", ".join(pieces) + ".") if pieces else "Custom conditions match, but conviction is still limited."
    return level, text, kind


def _save_current(name: str, setup: dict) -> None:
    if "smart_saved" not in st.session_state:
        st.session_state.smart_saved = {}
    st.session_state.smart_saved[name.strip()] = setup


def render_smart_money(navigate=None) -> None:
    if "smart_preset" not in st.session_state:
        st.session_state.smart_preset = "Foreign Accumulation"
    if "smart_saved" not in st.session_state:
        st.session_state.smart_saved = {}

    head1, head2 = st.columns([5, 1], vertical_alignment="center")
    with head1:
        st.markdown('<div class="sm-page-title">Smart Money Screener</div>', unsafe_allow_html=True)
    with head2:
        if st.button('', icon=':material/refresh:', help='Refresh Smart Money data', key='smart_refresh', width='stretch'):
            cached_idx_smart_base.clear()
            cached_yahoo_technical_dataset.clear()
            st.rerun()

    with st.container(border=True):
        st.markdown(
            '<div class="sm-setup-title">◉ &nbsp; Screening setup</div>'
            '<div class="sm-setup-sub">Choose a signal model, then refine its universe below.</div>',
            unsafe_allow_html=True,
        )
        mode = st.segmented_control(
            'Setup mode', ['Presets', 'Custom', 'Saved'],
            default='Presets', key='smart_mode', label_visibility='collapsed'
        ) or 'Presets'

        custom_cfg = {
            "min_value": 0.5,
            "rsi_min": 0,
            "rsi_max": 100,
            "relvol": 0.0,
            "trend": False,
            "foreign": False,
            "moneyflow": False,
            "breakout": False,
        }
        active_label = st.session_state.smart_preset
        saved_has_preset = False

        if mode == 'Presets':
            names = list(PRESETS)
            r1 = st.columns(2)
            r2 = st.columns(2)
            for col, name in zip(r1 + r2, names):
                active = st.session_state.smart_preset == name
                if col.button(
                    ('● ' if active else '○ ') + name,
                    key='smart_preset_' + name,
                    width='stretch',
                    type='primary' if active else 'secondary',
                ):
                    st.session_state.smart_preset = name
                    st.rerun()
            active_label = st.session_state.smart_preset

        elif mode == 'Custom':
            c1, c2, c3 = st.columns(3)
            custom_cfg["min_value"] = c1.number_input(
                'Min avg traded value (Rp B/day)', 0.0, 10000.0, 0.5, 0.5,
                key='sm_min_value_custom'
            )
            custom_cfg["rsi_min"], custom_cfg["rsi_max"] = c2.slider(
                'RSI range', 0, 100, (0, 100), key='sm_rsi'
            )
            custom_cfg["relvol"] = c3.number_input(
                'Min relative volume', 0.0, 20.0, 0.0, 0.1, key='sm_relvol'
            )
            f1, f2, f3, f4 = st.columns(4)
            custom_cfg["trend"] = f1.checkbox('Trend', key='sm_trend')
            custom_cfg["foreign"] = f2.checkbox('Foreign +', key='sm_foreign')
            custom_cfg["moneyflow"] = f3.checkbox('CMF +', key='sm_moneyflow')
            custom_cfg["breakout"] = f4.checkbox('Lookback breakout', key='sm_breakout')
            active_label = 'Custom Screen'

        else:
            if st.session_state.smart_saved:
                saved_name = st.selectbox(
                    'Saved setup', list(st.session_state.smart_saved), key='sm_saved_select'
                )
                saved = st.session_state.smart_saved[saved_name]
                active_label = saved.get('label', saved_name)
                custom_cfg.update(saved.get('custom', {}))
                if saved.get('preset'):
                    st.session_state.smart_preset = saved['preset']
                    saved_has_preset = True
            else:
                st.info('No saved screens yet. Save a preset or custom setup first.')

        save1, save2 = st.columns([4, 1])
        save_name = save1.text_input(
            'Save current setup as', placeholder='e.g. Foreign + Trend',
            label_visibility='collapsed', key='sm_save_name'
        )
        if save2.button(
            'Save', icon=':material/save:', width='stretch',
            disabled=not save_name.strip(), key='sm_save'
        ):
            _save_current(save_name, {
                'label': active_label,
                'preset': st.session_state.smart_preset if mode == 'Presets' else None,
                'custom': custom_cfg if mode == 'Custom' else {},
            })
            st.success('Screen saved for this session.')

    with st.container(border=True):
        title = active_label
        desc = PRESETS.get(title, {}).get(
            'description',
            'Custom smart-money and technical conditions.'
        )
        st.markdown(
            f'<div class="sm-results-title">{html.escape(title)}</div>'
            f'<div class="sm-results-sub">{html.escape(desc)}</div>',
            unsafe_allow_html=True,
        )

        f1, f2, f3 = st.columns([1, 1.25, 1.45])
        lookback = f1.selectbox(
            'Lookback', ['5D', '10D', '20D', '60D'],
            index=2, key='sm_lookback'
        )
        min_default = 0.5 if mode != 'Custom' else float(custom_cfg['min_value'])
        min_value = f2.number_input(
            'Min value (Rp B/day)', 0.0, 10000.0, min_default, 0.5,
            key='sm_result_min_value'
        )
        universe = f3.selectbox(
            'Universe', ['Quality 200', 'All IDX'],
            index=0, key='sm_universe'
        )

        lookback_n = int(str(lookback).replace('D', ''))
        if mode == 'Custom':
            build_setup = 'Custom Screen'
        elif mode == 'Saved' and not saved_has_preset:
            build_setup = 'Custom Screen'
        else:
            build_setup = st.session_state.smart_preset

        with st.spinner('Loading data... please wait'):
            try:
                data, status = build_smart_money_dataset(
                    universe=universe,
                    lookback=lookback_n,
                    min_value_b=min_value,
                    setup=build_setup,
                    custom_cfg=custom_cfg,
                )
            except Exception as exc:
                st.error(f'Smart Money data could not be built: {exc}')
                return

        asof = status.get('as_of', 'latest')
        st.markdown(
            '<div class="sm-asof">'
            f'As of {html.escape(str(asof))} · '
            f'{html.escape(universe)}: {status.get("stage1_universe",0)} stocks checked · '
            f'{status.get("stage1_candidates",0)} Stage-1 candidates · '
            f'{status.get("yahoo_ok",0)} Yahoo technicals usable'
            '</div>',
            unsafe_allow_html=True,
        )

        if universe == 'All IDX':
            st.caption(
                f'All IDX uses a two-stage scan: every available IDX stock is evaluated first; '
                f'{status.get("stage1_liquid",0)} passed the Rp{min_value:g}B/day liquidity gate '
                'before Yahoo technical confirmation.'
            )

        active_data = _lookback_view(data, lookback_n) if not data.empty else data

        is_custom_screen = mode == 'Custom' or (mode == 'Saved' and not saved_has_preset)
        if is_custom_screen:
            custom_cfg['min_value'] = min_value
            result = _custom_filter(active_data, custom_cfg) if not active_data.empty else active_data
            interpretation_setup = 'Custom Screen'
        else:
            preset = st.session_state.smart_preset
            result = _preset_filter(active_data, preset, min_value) if not active_data.empty else active_data
            interpretation_setup = preset

        st.markdown(
            f'<div class="sm-match-count"><b>{len(result)}</b> matches / '
            f'{len(active_data)} technical candidates</div>',
            unsafe_allow_html=True,
        )

        result = result.head(20)
        if result.empty:
            st.info(
                'No stocks currently match this setup. Lower the minimum value, '
                'try another preset, or switch universe.'
            )
            return

        h = st.columns([1.65, .55, .65, .75, 1.95, 1.75, 2.2])
        for col, label in zip(
            h,
            ['Stock', 'Price', f'{lookback_n}D %', f'Value {lookback_n}D',
             'Technical', 'Signals', 'What it means']
        ):
            col.markdown(
                f'<div class="sm-table-head">{label}</div>',
                unsafe_allow_html=True
            )
        st.markdown('<div class="sm-divider"></div>', unsafe_allow_html=True)

        for _, r in result.iterrows():
            cols = st.columns(
                [1.65, .55, .65, .75, 1.95, 1.75, 2.2],
                vertical_alignment='center'
            )
            company = html.escape(str(r.Company))
            sector = html.escape(str(r.Sector))
            cols[0].markdown(
                f'<div class="sm-stock"><b>{html.escape(r.Symbol)}</b>'
                f'<span>{company}</span><small>{sector}</small></div>',
                unsafe_allow_html=True,
            )
            cols[1].markdown(
                f'<div class="sm-number">{r.Close:,.0f}</div>',
                unsafe_allow_html=True
            )
            ret_class = 'positive' if r.Return20 >= 0 else 'negative'
            cols[2].markdown(
                f'<div class="sm-number {ret_class}">{r.Return20:+.2f}%</div>',
                unsafe_allow_html=True
            )
            cols[3].markdown(
                f'<div class="sm-number">{r.Value20B:.2f}B</div>',
                unsafe_allow_html=True
            )
            cols[4].markdown(_technical_chips(r), unsafe_allow_html=True)
            cols[5].markdown(_signal_chips(r), unsafe_allow_html=True)

            level, meaning, meaning_kind = _action_meaning(r, interpretation_setup)
            cols[6].markdown(
                f'<div class="sm-meaning sm-meaning-{meaning_kind}">'
                f'<b>{html.escape(level)}</b><span>{html.escape(meaning)}</span></div>',
                unsafe_allow_html=True,
            )
            if cols[6].button(
                'Chart', icon=':material/show_chart:',
                key='sm_chart_' + r.Symbol, width='stretch'
            ):
                st.session_state.dashboard_symbol = r.Symbol
                st.session_state.dashboard_search = r.Symbol
                if navigate:
                    navigate('Dashboard')
                st.rerun()
            st.markdown('<div class="sm-row-divider"></div>', unsafe_allow_html=True)

    st.caption(
        'HP Smart Money · Quality 200 or All IDX · two-stage IDX→Yahoo scan · '
        '5D / 10D / 20D / 60D lookbacks. Scores are screening signals, not recommendations.'
    )

