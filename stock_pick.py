from __future__ import annotations

import html
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from smart_money import _quality_universe, cached_idx_smart_base
from yahoo_download import download_universe


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out = out.mask((avg_loss == 0) & (avg_gain > 0), 100)
    out = out.mask((avg_loss == 0) & (avg_gain == 0), 50)
    return out


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    tr = pd.concat([
        (high - low).abs(),
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr.replace(0, np.nan)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def _fmt_price(v: float) -> str:
    if pd.isna(v):
        return '—'
    return f'{float(v):,.0f}'


def _fmt_pct(v: float) -> str:
    if pd.isna(v):
        return '—'
    return f'{float(v):+.1f}%'


def _quality_symbols() -> tuple[str, ...]:
    return _quality_universe()


@st.cache_data(ttl=1800, show_spinner=False)
def cached_benchmark() -> pd.DataFrame:
    frames, errors = download_universe(('^JKSE',), period='1y', chunk_size=1)
    frame = frames.get('^JKSE')
    if frame is None or frame.empty:
        raise ValueError(errors.get('^JKSE', 'IHSG history unavailable.'))
    return frame.copy()


@st.cache_data(ttl=1800, show_spinner=False)
def cached_stock_histories(symbols: tuple[str, ...]) -> tuple[dict, dict]:
    return download_universe(symbols, period='1y', chunk_size=60)


def _benchmark_returns(benchmark: pd.DataFrame) -> dict:
    c = pd.to_numeric(benchmark['Close'], errors='coerce').dropna()
    def ret(n: int) -> float:
        if len(c) < n + 1 or c.iloc[-n - 1] == 0:
            return np.nan
        return float((c.iloc[-1] / c.iloc[-n - 1] - 1) * 100)
    return {'20': ret(20), '60': ret(60)}


def _technical_row(symbol: str, raw: pd.DataFrame, benchmark_ret: dict) -> dict | None:
    d = raw.copy()
    d.columns = [str(c).title() for c in d.columns]
    if not {'Open', 'High', 'Low', 'Close', 'Volume'}.issubset(d.columns):
        return None
    d = d[['Open', 'High', 'Low', 'Close', 'Volume']].dropna().copy()
    if len(d) < 205:
        return None

    o = pd.to_numeric(d.Open, errors='coerce')
    h = pd.to_numeric(d.High, errors='coerce')
    l = pd.to_numeric(d.Low, errors='coerce')
    c = pd.to_numeric(d.Close, errors='coerce')
    v = pd.to_numeric(d.Volume, errors='coerce').fillna(0)
    if c.empty or c.iloc[-1] <= 0:
        return None

    ma20 = c.rolling(20).mean()
    ma50 = c.rolling(50).mean()
    ma200 = c.rolling(200).mean()
    rsi = _rsi(c, 14)
    adx = _adx(h, l, c, 14)
    atr = _atr(h, l, c, 14)

    ema12 = _ema(c, 12)
    ema26 = _ema(c, 26)
    macd = ema12 - ema26
    macd_sig = _ema(macd, 9)
    macd_hist = macd - macd_sig

    typical = (h + l + c) / 3.0
    spread = (h - l).replace(0, np.nan)
    mfv = ((((c - l) - (h - c)) / spread).fillna(0) * v)
    cmf20 = mfv.rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()

    close = float(c.iloc[-1])
    m20 = float(ma20.iloc[-1])
    m50 = float(ma50.iloc[-1])
    m200 = float(ma200.iloc[-1]) if pd.notna(ma200.iloc[-1]) else np.nan
    atr14 = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else np.nan
    atr_pct = atr14 / close * 100 if close and pd.notna(atr14) else np.nan

    ret20 = float((close / c.iloc[-21] - 1) * 100) if len(c) >= 21 else np.nan
    ret60 = float((close / c.iloc[-61] - 1) * 100) if len(c) >= 61 else np.nan
    rs20 = ret20 - benchmark_ret.get('20', np.nan)
    rs60 = ret60 - benchmark_ret.get('60', np.nan)

    # Relative-strength momentum: compare today's 20D RS with the value 5 sessions ago.
    if len(c) >= 26:
        stock20_5ago = (c.iloc[-6] / c.iloc[-26] - 1) * 100
        bench20 = benchmark_ret.get('20', np.nan)
        rs20_improving = bool(pd.notna(bench20) and rs20 > (stock20_5ago - bench20))
    else:
        rs20_improving = False

    prior_high20 = h.shift(1).rolling(20).max().iloc[-1]
    prior_high55 = h.shift(1).rolling(55).max().iloc[-1]
    breakout20 = bool(pd.notna(prior_high20) and close > prior_high20)
    breakout55 = bool(pd.notna(prior_high55) and close > prior_high55)

    avgvol20_prior = v.shift(1).rolling(20).mean().iloc[-1]
    relvol = float(v.iloc[-1] / avgvol20_prior) if pd.notna(avgvol20_prior) and avgvol20_prior > 0 else np.nan
    value = c * v
    avg_value20_b = float(value.tail(20).mean() / 1e9)
    avg_value5_b = float(value.tail(5).mean() / 1e9)
    value_accel = avg_value5_b / avg_value20_b if avg_value20_b > 0 else np.nan

    close_loc = float((close - l.iloc[-1]) / (h.iloc[-1] - l.iloc[-1])) if h.iloc[-1] > l.iloc[-1] else 0.5
    obv_up = bool(len(obv) >= 21 and obv.iloc[-1] > obv.iloc[-21])
    cmf = float(cmf20.iloc[-1]) if pd.notna(cmf20.iloc[-1]) else np.nan

    ma20_slope = float((ma20.iloc[-1] / ma20.iloc[-6] - 1) * 100) if pd.notna(ma20.iloc[-6]) else np.nan
    ma50_slope = float((ma50.iloc[-1] / ma50.iloc[-11] - 1) * 100) if pd.notna(ma50.iloc[-11]) else np.nan
    hist_now = float(macd_hist.iloc[-1]) if pd.notna(macd_hist.iloc[-1]) else np.nan
    hist_prev = float(macd_hist.iloc[-4]) if pd.notna(macd_hist.iloc[-4]) else np.nan
    macd_positive = bool(pd.notna(hist_now) and hist_now > 0)
    macd_improving = bool(pd.notna(hist_now) and pd.notna(hist_prev) and hist_now > hist_prev)

    rsi_now = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else np.nan
    adx_now = float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else np.nan
    extension = (close / m20 - 1) * 100 if m20 > 0 else np.nan

    # Base compression is measured before today's bar so a breakout bar itself does not inflate the base.
    base_h = h.shift(1).rolling(20).max().iloc[-1]
    base_l = l.shift(1).rolling(20).min().iloc[-1]
    base_width = (base_h / base_l - 1) * 100 if pd.notna(base_h) and pd.notna(base_l) and base_l > 0 else np.nan
    base_compressed = bool(pd.notna(base_width) and base_width <= 15)

    prev_ma20 = ma20.iloc[-2]
    reclaim_ma20 = bool(pd.notna(prev_ma20) and c.iloc[-2] <= prev_ma20 and close > m20)

    # Risk plan: below MA20/ATR support, capped near 2 ATR. Targets use R multiples.
    if pd.notna(atr14) and atr14 > 0:
        atr_stop = close - 2.0 * atr14
        ma_stop = m20 - 0.5 * atr14 if pd.notna(m20) and m20 < close else atr_stop
        stop = max(atr_stop, ma_stop)
        if stop >= close:
            stop = close - 1.5 * atr14
        risk = max(close - stop, atr14 * 0.5)
        entry_low = close if breakout20 else max(close - 0.25 * atr14, 0)
        entry_high = close + 0.35 * atr14
        t1 = close + 2.0 * risk
        t2 = close + 3.0 * risk
        stop_pct = (close - stop) / close * 100
    else:
        entry_low = entry_high = stop = t1 = t2 = stop_pct = np.nan

    return {
        'Symbol': symbol,
        'Close': close,
        'Return20': ret20,
        'Return60': ret60,
        'RS20': rs20,
        'RS60': rs60,
        'RSImproving': rs20_improving,
        'MA20': m20,
        'MA50': m50,
        'MA200': m200,
        'MA20Slope': ma20_slope,
        'MA50Slope': ma50_slope,
        'GoldenCross': bool(pd.notna(m200) and m50 > m200),
        'RSI': rsi_now,
        'ADX': adx_now,
        'MACDPositive': macd_positive,
        'MACDImproving': macd_improving,
        'Breakout20': breakout20,
        'Breakout55': breakout55,
        'RelVolume': relvol,
        'CloseLocation': close_loc,
        'BaseCompressed': base_compressed,
        'CMF20': cmf,
        'OBVUp': obv_up,
        'ValueAccel': value_accel,
        'AvgValue20B': avg_value20_b,
        'ATR': atr14,
        'ATRPct': atr_pct,
        'ExtensionMA20': extension,
        'ReclaimMA20': reclaim_ma20,
        'EntryLow': entry_low,
        'EntryHigh': entry_high,
        'Stop': stop,
        'StopPct': stop_pct,
        'Target1': t1,
        'Target2': t2,
        'YahooDate': pd.Timestamp(d.index[-1]).date().isoformat() if isinstance(d.index, pd.DatetimeIndex) else '',
    }


def _score_row(r: pd.Series) -> dict:
    # Trend 20
    trend = 0
    trend += 5 if r.Close > r.MA20 else 0
    trend += 5 if r.MA20 > r.MA50 else 0
    trend += 3 if r.MA20Slope > 0 else 0
    trend += 2 if r.MA50Slope > 0 else 0
    trend += 3 if pd.notna(r.MA200) and r.Close > r.MA200 else 0
    trend += 2 if bool(r.GoldenCross) else 0

    # Relative strength 15
    rs = 0
    if r.RS20 > 5: rs += 8
    elif r.RS20 > 0: rs += 5
    elif r.RS20 > -3: rs += 2
    if r.RS60 > 10: rs += 6
    elif r.RS60 > 0: rs += 4
    if bool(r.RSImproving): rs += 1
    rs = min(rs, 15)

    # Momentum 15
    momentum = 0
    if 50 <= r.RSI <= 70: momentum += 5
    elif 45 <= r.RSI <= 75: momentum += 3
    if bool(r.MACDPositive): momentum += 3
    if bool(r.MACDImproving): momentum += 3
    if r.ADX >= 25: momentum += 4
    elif r.ADX >= 20: momentum += 2

    # Breakout 20
    breakout = 0
    breakout += 6 if bool(r.Breakout20) else 0
    breakout += 5 if bool(r.Breakout55) else 0
    if r.RelVolume >= 1.5: breakout += 4
    elif r.RelVolume >= 1.2: breakout += 2
    breakout += 2 if r.CloseLocation >= 0.70 else 0
    breakout += 3 if bool(r.BaseCompressed) and bool(r.Breakout20) else 0
    breakout = min(breakout, 20)

    # Accumulation 15
    accum = 0
    if r.CMF20 >= 0.10: accum += 5
    elif r.CMF20 > 0: accum += 3
    accum += 4 if bool(r.OBVUp) else 0
    if r.ValueAccel >= 1.30: accum += 3
    elif r.ValueAccel >= 1.10: accum += 2
    if r.ForeignIntensity20 > 2: accum += 3
    elif r.ForeignIntensity20 > 0: accum += 2
    accum = min(accum, 15)

    # Risk / quality 15
    risk = 0
    if r.AvgValue20B >= 5: risk += 5
    elif r.AvgValue20B >= 1: risk += 4
    elif r.AvgValue20B >= 0.5: risk += 2
    if 1 <= r.ATRPct <= 5: risk += 4
    elif 0.5 <= r.ATRPct <= 7: risk += 2
    if 0 <= r.ExtensionMA20 <= 8: risk += 3
    elif -3 <= r.ExtensionMA20 <= 12: risk += 1
    if r.StopPct <= 8: risk += 3
    elif r.StopPct <= 10: risk += 2
    risk = min(risk, 15)

    total = int(round(trend + rs + momentum + breakout + accum + risk))
    return {
        'TrendScore': trend,
        'RSScore': rs,
        'MomentumScore': momentum,
        'BreakoutScore': breakout,
        'AccumScore': accum,
        'RiskScore': risk,
        'StockPickScore': total,
    }


def _setup_type(r: pd.Series) -> str:
    trend_ok = r.Close > r.MA20 > r.MA50 and r.MA20Slope > 0
    if bool(r.BaseCompressed) and bool(r.Breakout20) and r.RelVolume >= 1.2:
        return 'BASE BREAKOUT'
    if bool(r.Breakout20) and r.RelVolume >= 1.2:
        return 'BREAKOUT'
    if trend_ok and abs(r.ExtensionMA20) <= 3 and 45 <= r.RSI <= 60 and r.RelVolume <= 1.15:
        return 'PULLBACK MA20'
    if trend_ok and r.RS20 > 0 and bool(r.MACDPositive):
        return 'TREND CONTINUATION'
    if bool(r.ReclaimMA20) and bool(r.MACDImproving) and r.RSI >= 45:
        return 'EARLY REVERSAL'
    return 'MOMENTUM WATCH'


def _why(r: pd.Series) -> str:
    reasons = []
    if r.RS20 > 5 and r.RS60 > 0:
        reasons.append('outperforming IHSG')
    elif r.RS20 > 0:
        reasons.append('RS improving')
    if r.Close > r.MA20 > r.MA50:
        reasons.append('clean MA20/50 uptrend')
    if r.Breakout20:
        reasons.append('20D breakout')
    if r.RelVolume >= 1.3:
        reasons.append(f'volume {r.RelVolume:.1f}×')
    if r.CMF20 > 0 and r.OBVUp:
        reasons.append('money flow positive')
    if r.ADX >= 25:
        reasons.append('trend strength confirmed')
    if not reasons:
        reasons.append('mixed setup; needs confirmation')
    return ' · '.join(reasons[:3])


def _grade(score: float) -> tuple[str, str]:
    if score >= 80:
        return 'STRONG', 'good'
    if score >= 70:
        return 'GOOD', 'good'
    if score >= 60:
        return 'WATCH', 'warn'
    return 'WEAK', 'bad'


def _chip(text: str, kind: str = '') -> str:
    cls = f' sp-chip-{kind}' if kind else ''
    return f'<span class="sp-chip{cls}">{html.escape(str(text))}</span>'


def _indicator_chips(r: pd.Series) -> str:
    chips = [
        _chip(f'RS20 {_fmt_pct(r.RS20)}', 'good' if r.RS20 > 0 else 'bad'),
        _chip(f'RS60 {_fmt_pct(r.RS60)}', 'good' if r.RS60 > 0 else 'bad'),
        _chip(f'RSI {r.RSI:.0f}', 'good' if 50 <= r.RSI <= 70 else ''),
        _chip(f'ADX {r.ADX:.0f}', 'good' if r.ADX >= 25 else ''),
        _chip('MACD ↑' if r.MACDImproving else 'MACD flat', 'good' if r.MACDImproving else ''),
        _chip(f'Vol {r.RelVolume:.1f}×', 'good' if r.RelVolume >= 1.2 else ''),
    ]
    if r.GoldenCross:
        chips.append(_chip('Golden Cross', 'good'))
    return '<div class="sp-chip-wrap">' + ''.join(chips) + '</div>'


def _score_chips(r: pd.Series) -> str:
    return (
        '<div class="sp-chip-wrap">'
        + _chip(f'Trend {int(r.TrendScore)}/20')
        + _chip(f'RS {int(r.RSScore)}/15')
        + _chip(f'Mom {int(r.MomentumScore)}/15')
        + _chip(f'Break {int(r.BreakoutScore)}/20')
        + _chip(f'Accum {int(r.AccumScore)}/15')
        + _chip(f'Risk {int(r.RiskScore)}/15')
        + '</div>'
    )


def _build_dataset(universe: str, min_value_b: float) -> tuple[pd.DataFrame, dict]:
    stage, idx_status = cached_idx_smart_base()
    stage = stage.copy()
    if universe == 'Quality 200':
        symbols = list(_quality_symbols())
        pre = stage[stage.Symbol.isin(symbols)].copy()
    else:
        pre = stage[pd.to_numeric(stage.IDXValue20B, errors='coerce').fillna(0) >= float(min_value_b)].copy()
        # Fast All-IDX stage: prioritize liquid/active names before expensive technical history.
        pre['_stage_rank'] = (
            pd.to_numeric(pre.IDXValue20B, errors='coerce').fillna(0).rank(pct=True) * 0.55
            + pd.to_numeric(pre.IDXRelVolume20, errors='coerce').fillna(0).rank(pct=True) * 0.20
            + pd.to_numeric(pre.IDXReturn20, errors='coerce').fillna(0).rank(pct=True) * 0.15
            + pd.to_numeric(pre.ForeignIntensity20, errors='coerce').fillna(0).rank(pct=True) * 0.10
        )
        pre = pre.sort_values('_stage_rank', ascending=False).head(320)
        symbols = pre.Symbol.astype(str).tolist()

    if not symbols:
        raise ValueError('No tickers passed the selected universe/liquidity filters.')

    benchmark = cached_benchmark()
    bench_ret = _benchmark_returns(benchmark)
    frames, errors = cached_stock_histories(tuple(symbols))

    rows = []
    for symbol in symbols:
        raw = frames.get(symbol + '.JK')
        if raw is None:
            continue
        row = _technical_row(symbol, raw, bench_ret)
        if row:
            rows.append(row)
    tech = pd.DataFrame(rows)
    if tech.empty:
        return tech, {'requested': len(symbols), 'usable': 0, 'failed': len(errors), 'idx_total': idx_status.get('idx_total', 0)}

    meta_cols = ['Symbol', 'Company', 'Sector', 'SubSector', 'ForeignIntensity20', 'ForeignPositiveDays20', 'IDXDate']
    meta_cols = [c for c in meta_cols if c in pre.columns]
    out = tech.merge(pre[meta_cols].drop_duplicates('Symbol'), on='Symbol', how='left')
    out['Company'] = out.get('Company', pd.Series(index=out.index, dtype=object)).fillna(out.Symbol)
    out['Sector'] = out.get('Sector', pd.Series(index=out.index, dtype=object)).fillna('IDX')
    if 'ForeignIntensity20' not in out:
        out['ForeignIntensity20'] = 0.0
    if 'ForeignPositiveDays20' not in out:
        out['ForeignPositiveDays20'] = 0

    scores = out.apply(_score_row, axis=1, result_type='expand')
    out = pd.concat([out, scores], axis=1)
    out['Setup'] = out.apply(_setup_type, axis=1)
    out['Why'] = out.apply(_why, axis=1)
    out = out.sort_values(['StockPickScore', 'RS20', 'AvgValue20B'], ascending=[False, False, False])

    status = {
        'requested': len(symbols),
        'usable': int(out.Symbol.nunique()),
        'failed': len(errors),
        'idx_total': idx_status.get('idx_total', 0),
        'idx_as_of': idx_status.get('idx_as_of', 'latest'),
        'bench20': bench_ret.get('20'),
        'bench60': bench_ret.get('60'),
    }
    return out.reset_index(drop=True), status


@st.cache_data(ttl=1800, show_spinner=False)
def cached_stock_pick_dataset(universe: str, min_value_b: float) -> tuple[pd.DataFrame, dict]:
    return _build_dataset(universe, min_value_b)


def render_stock_pick(navigate=None) -> None:
    head, refresh = st.columns([5, 1], vertical_alignment='center')
    with head:
        st.markdown(
            '<div class="sp-title">Stock Pick</div>'
            '<div class="sp-subtitle">Medium-term swing candidates ranked by trend, relative strength, momentum, breakout quality, accumulation and risk.</div>',
            unsafe_allow_html=True,
        )
    with refresh:
        if st.button('', icon=':material/refresh:', help='Refresh Stock Pick data', key='sp_refresh', width='stretch'):
            cached_stock_pick_dataset.clear()
            cached_stock_histories.clear()
            cached_benchmark.clear()
            st.rerun()

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.25, 1, 1.35, 1])
        universe = c1.selectbox('Universe', ['Quality 200', 'All IDX (fast)'], key='sp_universe')
        min_value = c2.number_input('Min value (Rp B/day)', 0.0, 10000.0, 0.5, 0.5, key='sp_min_value')
        setup_filter = c3.selectbox(
            'Setup',
            ['Top Ranked', 'Breakout', 'Trend Continuation', 'Pullback MA20', 'Early Reversal'],
            key='sp_setup',
        )
        min_score = c4.slider('Min score', 40, 90, 60, 5, key='sp_min_score')

        if universe.startswith('All IDX'):
            st.caption('All IDX (fast) screens the whole IDX with official market data first, then sends the 320 highest-ranked liquid/active candidates to Yahoo for full technical scoring.')

    with st.spinner('Loading stock picks... please wait'):
        try:
            data, status = cached_stock_pick_dataset(universe, float(min_value))
        except Exception as exc:
            st.error(f'Stock Pick data could not be built: {exc}')
            return

    if data.empty:
        st.warning('No technical data is currently available for this universe.')
        return

    result = data[data.StockPickScore >= int(min_score)].copy()
    if setup_filter == 'Breakout':
        result = result[result.Setup.isin(['BREAKOUT', 'BASE BREAKOUT'])]
    elif setup_filter == 'Trend Continuation':
        result = result[result.Setup == 'TREND CONTINUATION']
    elif setup_filter == 'Pullback MA20':
        result = result[result.Setup == 'PULLBACK MA20']
    elif setup_filter == 'Early Reversal':
        result = result[result.Setup == 'EARLY REVERSAL']

    st.markdown(
        f'<div class="sp-status">As of {html.escape(str(status.get("idx_as_of", "latest")))} · '
        f'{status.get("requested",0)} requested · {status.get("usable",0)} technical histories usable · '
        f'{status.get("failed",0)} failed · IHSG 20D {_fmt_pct(status.get("bench20"))} · IHSG 60D {_fmt_pct(status.get("bench60"))}</div>',
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric('Candidates', f'{len(result):,}')
    m2.metric('Strong ≥80', f'{int((result.StockPickScore >= 80).sum()):,}')
    m3.metric('Breakout setups', f'{int(result.Setup.isin(["BREAKOUT","BASE BREAKOUT"]).sum()):,}')
    m4.metric('Median score', '—' if result.empty else f'{result.StockPickScore.median():.0f}/100')

    if result.empty:
        st.info('No stocks match this score/setup combination. Lower the minimum score or select Top Ranked.')
        return

    st.markdown('<div class="sp-section-title">Ranked swing candidates</div>', unsafe_allow_html=True)
    st.caption('Stock Pick Score is a heuristic ranking model for 2–8 week swing research. It is not a guarantee or buy recommendation.')

    headers = st.columns([1.45, .55, .85, 1.9, 1.65, 1.45, 2.05])
    for col, label in zip(headers, ['Stock', 'Score', 'Setup', 'Indicators', 'Score breakdown', 'Risk plan', 'Why it ranks']):
        col.markdown(f'<div class="sp-table-head">{label}</div>', unsafe_allow_html=True)
    st.markdown('<div class="sp-divider"></div>', unsafe_allow_html=True)

    for _, r in result.head(20).iterrows():
        cols = st.columns([1.45, .55, .85, 1.9, 1.65, 1.45, 2.05], vertical_alignment='center')
        cols[0].markdown(
            f'<div class="sp-stock"><b>{html.escape(str(r.Symbol))}</b>'
            f'<span>{html.escape(str(r.Company))}</span><small>{html.escape(str(r.Sector))}</small></div>',
            unsafe_allow_html=True,
        )
        grade, kind = _grade(r.StockPickScore)
        cols[1].markdown(
            f'<div class="sp-score sp-score-{kind}">{int(r.StockPickScore)}<span>{grade}</span></div>',
            unsafe_allow_html=True,
        )
        cols[2].markdown(f'<div class="sp-setup">{html.escape(str(r.Setup))}</div>', unsafe_allow_html=True)
        cols[3].markdown(_indicator_chips(r), unsafe_allow_html=True)
        cols[4].markdown(_score_chips(r), unsafe_allow_html=True)
        cols[5].markdown(
            f'<div class="sp-risk"><b>Entry</b> {_fmt_price(r.EntryLow)}–{_fmt_price(r.EntryHigh)}<br>'
            f'<b>Stop</b> {_fmt_price(r.Stop)} ({_fmt_pct(-r.StopPct)})<br>'
            f'<b>T1/T2</b> {_fmt_price(r.Target1)} / {_fmt_price(r.Target2)}</div>',
            unsafe_allow_html=True,
        )
        cols[6].markdown(
            f'<div class="sp-why">{html.escape(str(r.Why))}</div>',
            unsafe_allow_html=True,
        )
        if cols[6].button('Analyze', icon=':material/analytics:', key='sp_analyze_' + str(r.Symbol), width='stretch'):
            st.session_state.analysis_symbol = str(r.Symbol)
            st.session_state.analysis_search = str(r.Symbol)
            st.session_state.analysis_prefill = r.to_dict()
            if navigate:
                navigate('Stock Analysis')
            st.rerun()
        st.markdown('<div class="sp-row-divider"></div>', unsafe_allow_html=True)

    st.caption(
        'Score weights: Trend 20 · Relative Strength vs IHSG 15 · Momentum 15 · Breakout/Volume 20 · Accumulation 15 · Risk/Liquidity 15. '
        'Golden Cross is a small trend bonus, not a requirement. Entry/stop/targets are mechanical ATR-based research levels.'
    )
