from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from idx_official import fetch_idx_market_history, fetch_stock_screener_metadata
from yahoo_download import download_universe


FACTOR_LABELS = {
    "CMF": "CMF pressure",
    "OBVSlope": "OBV slope",
    "ValueAccel": "Value acceleration",
    "RelVolume": "Relative volume",
    "CloseLocation": "Close location",
}


def _quality_universe() -> tuple[str, ...]:
    d = pd.read_csv(Path(__file__).with_name("idx_quality_200.csv"))
    symbols = tuple(dict.fromkeys(d["Ticker"].astype(str).str.upper().str.strip()))
    if len(symbols) != 200:
        raise ValueError("Quality universe must contain 200 unique tickers.")
    return symbols


@st.cache_data(ttl=21600, show_spinner=False)
def _all_idx_current_liquid(min_value_b: float) -> tuple[tuple[str, ...], pd.DataFrame, dict]:
    """Current-listed All-IDX universe, prefiltered using recent official IDX value.

    This keeps the lab usable on Streamlit Cloud, but it introduces current-listing/
    survivorship bias. The UI states that limitation explicitly.
    """
    meta = fetch_stock_screener_metadata().copy()
    hist = fetch_idx_market_history(sessions=20, max_calendar_days=45).copy()
    hist["TradedValue"] = pd.to_numeric(hist["TradedValue"], errors="coerce").fillna(0.0)
    avg = (
        hist.groupby("Symbol", as_index=False)["TradedValue"]
        .mean()
        .rename(columns={"TradedValue": "RecentAvgValue"})
    )
    avg["RecentAvgValueB"] = avg["RecentAvgValue"] / 1e9
    d = meta.merge(avg[["Symbol", "RecentAvgValueB"]], on="Symbol", how="left")
    d["RecentAvgValueB"] = d["RecentAvgValueB"].fillna(0.0)
    eligible = d[d.RecentAvgValueB >= float(min_value_b)].copy()
    symbols = tuple(eligible.Symbol.astype(str).drop_duplicates().tolist())
    status = {
        "all_idx": int(meta.Symbol.nunique()),
        "recent_liquid": len(symbols),
    }
    return symbols, eligible, status


@st.cache_data(ttl=21600, show_spinner=False)
def _cached_history(symbols: tuple[str, ...], period: str) -> tuple[dict, dict]:
    if not symbols:
        return {}, {}
    return download_universe(symbols, period=period, chunk_size=50)


def _ticker_features(symbol: str, raw: pd.DataFrame) -> pd.DataFrame:
    d = raw.copy()
    d.columns = [str(c).title() for c in d.columns]
    need = ["Open", "High", "Low", "Close", "Volume"]
    if not set(need).issubset(d.columns):
        return pd.DataFrame()
    d = d[need].dropna().copy()
    if len(d) < 90:
        return pd.DataFrame()

    for c in need:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna()
    d = d[(d.Close > 0) & (d.Volume >= 0)].copy()
    if len(d) < 90:
        return pd.DataFrame()

    d.index = pd.to_datetime(d.index)
    c = d.Close
    h = d.High
    l = d.Low
    v = d.Volume.astype(float)
    value = c * v

    typical_spread = (h - l).replace(0, np.nan)
    mfv = ((((c - l) - (h - c)) / typical_spread).fillna(0.0)) * v
    d["CMF"] = mfv.rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)

    direction = np.sign(c.diff()).fillna(0.0)
    obv = (direction * v).cumsum()
    volume_base = v.rolling(20).mean().replace(0, np.nan)
    d["OBVSlope"] = (obv - obv.shift(10)) / (volume_base * 10.0)

    avg5_value = value.rolling(5).mean()
    avg20_value = value.rolling(20).mean().replace(0, np.nan)
    d["ValueAccel"] = avg5_value / avg20_value - 1.0

    prior_avg_vol20 = v.shift(1).rolling(20).mean().replace(0, np.nan)
    d["RelVolume"] = v / prior_avg_vol20

    lo20 = l.rolling(20).min()
    hi20 = h.rolling(20).max()
    d["CloseLocation"] = (c - lo20) / (hi20 - lo20).replace(0, np.nan)

    d["AvgValueB"] = avg20_value / 1e9
    d["Return20"] = (c / c.shift(20) - 1.0) * 100.0
    d["Symbol"] = symbol
    d["Date"] = d.index.normalize()
    d["BarIndex"] = np.arange(len(d), dtype=int)
    return d.reset_index(drop=True)


def _cross_section_score(long_df: pd.DataFrame, weights: dict[str, float]) -> pd.DataFrame:
    d = long_df.copy()
    factors = list(FACTOR_LABELS)
    for factor in factors:
        d[factor + "Pct"] = (
            d.groupby("Date")[factor]
            .rank(method="average", pct=True, na_option="keep")
            .mul(100.0)
        )

    total_weight = sum(float(weights.get(f, 0.0)) for f in factors)
    if total_weight <= 0:
        raise ValueError("HPLP Core weights must be greater than zero.")

    numerator = 0.0
    denominator = 0.0
    for f in factors:
        w = float(weights.get(f, 0.0))
        if w <= 0:
            continue
        pct = d[f + "Pct"]
        numerator = numerator + pct.fillna(0.0) * w
        denominator = denominator + pct.notna().astype(float) * w
    d["HPLP"] = numerator / denominator.replace(0, np.nan)
    d = d.sort_values(["Symbol", "Date"])
    d["HPLPDelta5"] = d.groupby("Symbol")["HPLP"].diff(5)
    return d


def _forward_metrics(group: pd.DataFrame, horizon: int) -> pd.DataFrame:
    g = group.sort_values("Date").copy()
    close = g.Close.to_numpy(dtype=float)
    high = g.High.to_numpy(dtype=float)
    low = g.Low.to_numpy(dtype=float)
    n = len(g)

    fwd = np.full(n, np.nan)
    mfe = np.full(n, np.nan)
    mae = np.full(n, np.nan)
    hit = np.full(n, np.nan)

    for i in range(n):
        end = i + horizon
        if end >= n:
            continue
        base = close[i]
        if not np.isfinite(base) or base <= 0:
            continue
        future_close = close[end]
        future_high = high[i + 1:end + 1]
        future_low = low[i + 1:end + 1]
        if len(future_high) != horizon:
            continue

        fwd[i] = (future_close / base - 1.0) * 100.0
        mfe[i] = (np.nanmax(future_high) / base - 1.0) * 100.0
        mae[i] = (np.nanmin(future_low) / base - 1.0) * 100.0

        up_hits = np.flatnonzero(future_high >= base * 1.05)
        dn_hits = np.flatnonzero(future_low <= base * 0.97)
        if len(up_hits) == 0:
            hit[i] = 0.0
        elif len(dn_hits) == 0:
            hit[i] = 1.0
        elif up_hits[0] < dn_hits[0]:
            hit[i] = 1.0
        elif up_hits[0] > dn_hits[0]:
            hit[i] = 0.0
        else:
            # Same daily bar touched both thresholds; intraday order is unknowable.
            hit[i] = np.nan

    g["ForwardReturn"] = fwd
    g["MFE"] = mfe
    g["MAE"] = mae
    g["Hit5Before3"] = hit
    return g


def _dedupe_signals(signals: pd.DataFrame, horizon: int) -> pd.DataFrame:
    kept = []
    for _, g in signals.sort_values(["Symbol", "Date"]).groupby("Symbol"):
        last_bar = -10**9
        for idx, row in g.iterrows():
            bar = int(row.BarIndex)
            if bar - last_bar > horizon:
                kept.append(idx)
                last_bar = bar
    return signals.loc[kept].sort_values("Date") if kept else signals.iloc[0:0].copy()


def _build_backtest(
    frames: dict,
    *,
    weights: dict[str, float],
    min_value_b: float,
    horizon: int,
    signal_type: str,
    threshold: float,
    max_price_return: float,
    min_hplp_rise: float,
    dedupe: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    parts = []
    for yahoo_symbol, raw in frames.items():
        symbol = str(yahoo_symbol).replace(".JK", "")
        feat = _ticker_features(symbol, raw)
        if not feat.empty:
            parts.append(feat)
    if not parts:
        raise ValueError("Yahoo returned no usable historical feature data.")

    d = pd.concat(parts, ignore_index=True)
    d = d[d.AvgValueB >= float(min_value_b)].copy()
    factor_cols = list(FACTOR_LABELS)
    d = d.dropna(subset=factor_cols + ["Return20", "AvgValueB"])
    if d.empty:
        raise ValueError("No historical rows remain after liquidity/feature filters.")

    d = _cross_section_score(d, weights)
    forward_parts = []
    for _, g in d.groupby("Symbol", sort=False):
        forward_parts.append(_forward_metrics(g, horizon))
    d = pd.concat(forward_parts, ignore_index=True)

    if signal_type == "Bullish HPLP Divergence":
        mask = (
            (d.HPLP >= float(threshold))
            & (d.Return20 <= float(max_price_return))
            & (d.HPLPDelta5 >= float(min_hplp_rise))
        )
    else:
        mask = d.HPLP >= float(threshold)

    signals = d[mask & d.ForwardReturn.notna()].copy()
    if dedupe and not signals.empty:
        signals = _dedupe_signals(signals, horizon)

    bins = [-0.001, 20, 40, 60, 80, 100.001]
    labels = ["0–20", "20–40", "40–60", "60–80", "80–100"]
    d["ScoreBucket"] = pd.cut(d.HPLP, bins=bins, labels=labels, include_lowest=True)
    eligible = d[d.ForwardReturn.notna()].copy()
    bucket = (
        eligible.groupby("ScoreBucket", observed=True)
        .agg(
            Observations=("ForwardReturn", "size"),
            MedianReturn=("ForwardReturn", "median"),
            WinRate=("ForwardReturn", lambda x: (x > 0).mean() * 100),
            MedianMFE=("MFE", "median"),
            MedianMAE=("MAE", "median"),
        )
        .reset_index()
    )

    if signals.empty:
        yearly = pd.DataFrame(columns=["Year", "Signals", "MedianReturn", "WinRate", "Hit5Before3", "MedianMFE", "MedianMAE"])
    else:
        signals["Year"] = pd.to_datetime(signals.Date).dt.year
        yearly = (
            signals.groupby("Year")
            .agg(
                Signals=("ForwardReturn", "size"),
                MedianReturn=("ForwardReturn", "median"),
                WinRate=("ForwardReturn", lambda x: (x > 0).mean() * 100),
                Hit5Before3=("Hit5Before3", lambda x: x.dropna().mean() * 100 if x.notna().any() else np.nan),
                MedianMFE=("MFE", "median"),
                MedianMAE=("MAE", "median"),
            )
            .reset_index()
        )
    return d, signals, bucket, yearly


def _bucket_chart(bucket: pd.DataFrame, horizon: int) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=bucket.ScoreBucket.astype(str),
            y=bucket.MedianReturn,
            text=[f"{x:+.2f}%" for x in bucket.MedianReturn],
            textposition="outside",
            hovertemplate="HPLP %{x}<br>Median return %{y:.2f}%<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_width=1, line_color="#c8cfcb")
    fig.update_layout(
        height=360,
        margin=dict(l=15, r=15, t=25, b=15),
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=False,
        xaxis_title="HPLP score bucket",
        yaxis_title=f"Median {horizon}D forward return (%)",
    )
    fig.update_yaxes(gridcolor="#edf1ee", zeroline=False)
    fig.update_xaxes(showgrid=False)
    return fig


def _pct(v: float) -> str:
    return "—" if pd.isna(v) else f"{v:.1f}%"


def _num(v: float) -> str:
    return "—" if pd.isna(v) else f"{v:+.2f}%"


def render_hplp_lab() -> None:
    st.markdown(
        '<div class="hplp-title">HPLP Lab</div>'
        '<div class="hplp-subtitle">Develop, stress-test and validate HP Liquidity Pressure formulas before promoting them to the live screener.</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="hplp-note"><b>HPLP v0.1 Core</b> uses historical Yahoo OHLCV only. '
        'Foreign Intensity is intentionally disabled for long-history backtests until a reliable historical IDX foreign archive is available.</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown('<div class="hplp-section-title">Backtest setup</div>', unsafe_allow_html=True)
        a, b, c, d = st.columns(4)
        version = a.selectbox("Formula", ["HPLP v0.1 Core"], key="hplp_version")
        universe = b.selectbox("Universe", ["Quality 200", "All IDX (current liquid)"], key="hplp_universe")
        period = c.selectbox("History", ["2Y", "5Y"], index=0, key="hplp_period")
        horizon_label = d.selectbox("Forward horizon", ["5D", "10D", "20D", "60D"], index=2, key="hplp_horizon")

        e, f, g, h = st.columns(4)
        min_value = e.number_input("Min avg value (Rp B/day)", min_value=0.0, max_value=10000.0, value=0.5, step=0.5, key="hplp_min_value")
        signal_type = f.selectbox("Signal", ["HPLP High Score", "Bullish HPLP Divergence"], index=1, key="hplp_signal")
        threshold = g.slider("HPLP threshold", min_value=50, max_value=95, value=70, step=5, key="hplp_threshold")
        dedupe = h.checkbox("De-duplicate signals", value=True, help="Count a ticker again only after the selected forward horizon has passed.", key="hplp_dedupe")

        if signal_type == "Bullish HPLP Divergence":
            i, j = st.columns(2)
            max_price_return = i.slider("Max 20D price return", min_value=-20, max_value=15, value=3, step=1, key="hplp_max_return")
            min_hplp_rise = j.slider("Min HPLP rise vs 5 bars ago", min_value=0, max_value=40, value=10, step=5, key="hplp_min_rise")
        else:
            max_price_return = 100.0
            min_hplp_rise = -100.0

    with st.container(border=True):
        st.markdown('<div class="hplp-section-title">Formula weights</div>', unsafe_allow_html=True)
        st.caption("Each factor is percentile-ranked against the eligible universe on the same trading date. Weights must total 100%.")
        w1, w2, w3 = st.columns(3)
        cmf_w = w1.number_input("CMF pressure %", 0, 100, 30, 5, key="hplp_w_cmf")
        obv_w = w2.number_input("OBV slope %", 0, 100, 25, 5, key="hplp_w_obv")
        value_w = w3.number_input("Value acceleration %", 0, 100, 20, 5, key="hplp_w_value")
        w4, w5, w6 = st.columns(3)
        relvol_w = w4.number_input("Relative volume %", 0, 100, 15, 5, key="hplp_w_relvol")
        close_w = w5.number_input("Close location %", 0, 100, 10, 5, key="hplp_w_close")
        w6.number_input("Foreign intensity %", 0, 100, 0, 5, disabled=True, help="Reserved for HPLP+ when long historical foreign data is available.", key="hplp_w_foreign")

        weights = {
            "CMF": float(cmf_w),
            "OBVSlope": float(obv_w),
            "ValueAccel": float(value_w),
            "RelVolume": float(relvol_w),
            "CloseLocation": float(close_w),
        }
        total = int(sum(weights.values()))
        total_class = "ok" if total == 100 else "bad"
        st.markdown(f'<div class="hplp-weight-total {total_class}">Total core weight: <b>{total}%</b></div>', unsafe_allow_html=True)

        run = st.button(
            "Run backtest",
            icon=":material/science:",
            type="primary",
            width="stretch",
            disabled=(total != 100),
            key="hplp_run",
        )

    if universe.startswith("All IDX"):
        st.warning(
            "All IDX v0.1 uses today’s listed/liquid universe as the historical sample. This is useful for research but has survivorship/current-listing bias. Quality 200 is the cleaner first calibration universe."
        )

    if run:
        period_code = period.lower()
        horizon = int(horizon_label.replace("D", ""))

        with st.spinner("Loading historical data... please wait"):
            if universe == "Quality 200":
                symbols = _quality_universe()
                universe_status = {"all_idx": 200, "recent_liquid": 200}
            else:
                symbols, _, universe_status = _all_idx_current_liquid(float(min_value))
                if not symbols:
                    st.error("No All-IDX stocks passed the current liquidity pre-filter.")
                    return

            frames, errors = _cached_history(symbols, period_code)
            try:
                _, signals, bucket, yearly = _build_backtest(
                    frames,
                    weights=weights,
                    min_value_b=float(min_value),
                    horizon=horizon,
                    signal_type=signal_type,
                    threshold=float(threshold),
                    max_price_return=float(max_price_return),
                    min_hplp_rise=float(min_hplp_rise),
                    dedupe=bool(dedupe),
                )
            except Exception as exc:
                st.error(f"Backtest could not be completed: {exc}")
                return

        st.session_state["hplp_lab_result"] = {
            "signals": signals,
            "bucket": bucket,
            "yearly": yearly,
            "horizon": horizon,
            "universe": universe,
            "requested": len(symbols),
            "usable": len(frames),
            "failed": len(errors),
            "history": period,
            "signal_type": signal_type,
            "threshold": threshold,
            "min_value": min_value,
            "weights": weights.copy(),
            "universe_status": universe_status,
        }

    bundle = st.session_state.get("hplp_lab_result")
    if bundle is None:
        st.markdown(
            '<div class="hplp-empty"><b>Ready to test HPLP v0.1.</b><span>Adjust the formula, choose a horizon, then run the backtest. The lab does not change the live Smart Money Screener.</span></div>',
            unsafe_allow_html=True,
        )
        return

    signals = bundle["signals"]
    bucket = bundle["bucket"]
    yearly = bundle["yearly"]
    horizon = int(bundle["horizon"])
    result_universe = bundle["universe"]

    st.markdown(
        f'<div class="hplp-status">Last run · {result_universe} · {bundle["history"]} history · '
        f'HPLP ≥ {bundle["threshold"]} · <b>{bundle["requested"]}</b> requested · '
        f'<b>{bundle["usable"]}</b> Yahoo histories usable · <b>{bundle["failed"]}</b> failed</div>',
        unsafe_allow_html=True,
    )

    if signals.empty:
        st.warning("No historical signals matched this rule. Lower the HPLP threshold or relax the divergence conditions.")
    else:
        hit_series = signals.Hit5Before3.dropna()
        metrics = {
            "Signals": f"{len(signals):,}",
            f"Median {horizon}D Return": _num(signals.ForwardReturn.median()),
            "Win Rate": _pct((signals.ForwardReturn > 0).mean() * 100),
            "Median MFE": _num(signals.MFE.median()),
            "Median MAE": _num(signals.MAE.median()),
            "+5% before -3%": _pct(hit_series.mean() * 100 if len(hit_series) else np.nan),
        }
        cols = st.columns(6)
        for col, (label, value) in zip(cols, metrics.items()):
            col.metric(label, value)

    with st.container(border=True):
        st.markdown('<div class="hplp-section-title">Does a higher HPLP score lead to better forward returns?</div>', unsafe_allow_html=True)
        st.plotly_chart(_bucket_chart(bucket, horizon), width="stretch", config={"displayModeBar": False})
        display_bucket = bucket.copy()
        display_bucket.columns = ["HPLP", "Observations", f"Median {horizon}D Return %", "Win Rate %", "Median MFE %", "Median MAE %"]
        for col in [f"Median {horizon}D Return %", "Win Rate %", "Median MFE %", "Median MAE %"]:
            display_bucket[col] = display_bucket[col].round(2)
        st.dataframe(display_bucket, hide_index=True, width="stretch")

    with st.container(border=True):
        st.markdown('<div class="hplp-section-title">Year-by-year stability</div>', unsafe_allow_html=True)
        if yearly.empty:
            st.info("No yearly signal statistics are available for the current rule.")
        else:
            yd = yearly.copy()
            yd.columns = ["Year", "Signals", f"Median {horizon}D Return %", "Win Rate %", "+5% before -3%", "Median MFE %", "Median MAE %"]
            for col in [f"Median {horizon}D Return %", "Win Rate %", "+5% before -3%", "Median MFE %", "Median MAE %"]:
                yd[col] = yd[col].round(2)
            st.dataframe(yd, hide_index=True, width="stretch")

    with st.container(border=True):
        st.markdown('<div class="hplp-section-title">Historical signal sample</div>', unsafe_allow_html=True)
        if signals.empty:
            st.info("No signals to display.")
        else:
            sample = signals.sort_values(["Date", "HPLP"], ascending=[False, False]).head(100).copy()
            sample = sample[["Date", "Symbol", "HPLP", "HPLPDelta5", "Return20", "AvgValueB", "ForwardReturn", "MFE", "MAE", "Hit5Before3"]]
            sample.columns = ["Date", "Ticker", "HPLP", "HPLP Δ5", "Price 20D %", "Avg Value RpB", f"Forward {horizon}D %", "MFE %", "MAE %", "+5 before -3"]
            for col in ["HPLP", "HPLP Δ5", "Price 20D %", "Avg Value RpB", f"Forward {horizon}D %", "MFE %", "MAE %"]:
                sample[col] = pd.to_numeric(sample[col], errors="coerce").round(2)
            st.dataframe(sample, hide_index=True, width="stretch", height=420)

    st.caption(
        "Research notes: features use information available up to each signal date; forward metrics use later bars. Same-day +5% and -3% touches are excluded because daily OHLC cannot reveal intraday order. All-IDX mode is current-listing biased in v0.1."
    )
