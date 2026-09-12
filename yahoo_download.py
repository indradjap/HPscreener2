import yfinance as yf
import pandas as pd


def normalize_ticker(ticker: str) -> str:
    ticker = ticker.strip().upper()
    if ticker.startswith("^") or ticker.endswith(".JK") or "=" in ticker:
        return ticker
    return ticker + ".JK"


def load_symbol(symbol: str, period: str = "2y", add_jk_suffix: bool = True):
    symbol = symbol.strip().upper()
    if add_jk_suffix:
        symbol = normalize_ticker(symbol)

    df = yf.download(
        symbol,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
    )

    if df.empty:
        raise ValueError(f"Data {symbol} tidak ditemukan.")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if len(df) < 220:
        raise ValueError(f"{symbol}: minimal sekitar 220 bar data diperlukan.")

    return symbol, df


def load_stock(ticker: str, period: str = "2y"):
    return load_symbol(ticker, period=period, add_jk_suffix=True)


def load_benchmark(symbol: str = "^JKSE", period: str = "2y"):
    return load_symbol(symbol, period=period, add_jk_suffix=False)


def _clean_downloaded_frame(raw: pd.DataFrame, symbol: str | None = None, single: bool = False) -> pd.DataFrame:
    """Normalize one yf.download response without changing the V5.9 fetch method."""
    required = ["Open", "High", "Low", "Close", "Volume"]
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        if symbol is not None:
            lvl0 = set(map(str, df.columns.get_level_values(0)))
            lvl1 = set(map(str, df.columns.get_level_values(1)))
            if symbol in lvl1:
                df = df.xs(symbol, axis=1, level=1).copy()
            elif symbol in lvl0:
                df = df.xs(symbol, axis=1, level=0).copy()
            elif single:
                df.columns = df.columns.get_level_values(0)
            else:
                raise KeyError("symbol not present in batch response")
        elif single:
            df.columns = df.columns.get_level_values(0)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns {missing}")
    df = df[required].dropna(how="any")
    df = df[df["Close"] > 0]
    return df


def download_universe(tickers, period: str = "2y", chunk_size: int = 60):
    """V5.9 Yahoo fetch + recovery for partial batch responses.

    Primary path remains exactly the V5.9 yf.download batch call. Yahoo can occasionally
    return only part of a large batch on Streamlit Cloud. Any missing symbol is therefore
    retried individually using the same yf.download method used by V5.9 Single Stock.
    """
    symbols = []
    seen = set()
    for t in tickers:
        s = normalize_ticker(str(t))
        if s not in seen:
            symbols.append(s)
            seen.add(s)

    frames = {}
    errors = {}
    scanner_min_bars = 60

    for start in range(0, len(symbols), max(int(chunk_size), 1)):
        chunk = symbols[start:start + max(int(chunk_size), 1)]
        try:
            raw = yf.download(
                tickers=chunk,
                period=period,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=True,
                group_by="column",
            )
        except Exception as e:
            for s in chunk:
                errors[s] = f"batch download error: {e}"
            continue

        if raw is None or raw.empty:
            for s in chunk:
                errors[s] = "empty batch download"
            continue

        for s in chunk:
            try:
                df = _clean_downloaded_frame(raw, symbol=s, single=(len(chunk) == 1))
                if len(df) < scanner_min_bars:
                    raise ValueError(f"only {len(df)} bars")
                frames[s] = df
                errors.pop(s, None)
            except Exception as e:
                errors[s] = str(e)

    # Streamlit/Yahoo occasionally returns a partial MultiIndex batch. Recover only the
    # missing symbols, still with the original V5.9 yf.download path (no alternate API).
    missing_symbols = [s for s in symbols if s not in frames]
    for s in missing_symbols:
        try:
            raw = yf.download(
                s,
                period=period,
                interval="1d",
                auto_adjust=False,
                progress=False,
            )
            if raw is None or raw.empty:
                raise ValueError("empty individual retry")
            df = _clean_downloaded_frame(raw, symbol=s, single=True)
            if len(df) < scanner_min_bars:
                raise ValueError(f"only {len(df)} bars")
            frames[s] = df
            errors.pop(s, None)
        except Exception as e:
            errors[s] = f"individual retry: {e}"

    return frames, errors


def data_health(df: pd.DataFrame | None) -> dict:
    """Compatibility shim for the V6 UI; data fetching above is unchanged from V5.9."""
    if df is None:
        return {"provider": "N/A", "bars": 0, "history_quality": "UNAVAILABLE"}
    return {
        "provider": "Yahoo Finance / yf.download (V5.9 fetch)",
        "bars": int(len(df)),
        "history_quality": "FULL" if len(df) >= 220 else "LIMITED",
        "attempt": 1,
    }
