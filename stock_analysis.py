from __future__ import annotations

import html
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from idx_official import fetch_stock_screener_metadata, fetch_idx_market_history
from idx_price import idx_price_fraction, round_idx_price
from stock_pick import (
    _benchmark_returns,
    _fmt_pct,
    _fmt_price,
    _grade,
    _score_row,
    _setup_type,
    _technical_row,
    _why,
    cached_benchmark,
)
from yahoo_download import download_universe


def _normalize_symbol(text: str) -> str:
    value = (text or '').strip().upper()
    if value.endswith('.JK'):
        value = value[:-3]
    if not re.fullmatch(r'[A-Z0-9]{4}', value):
        raise ValueError('Use a 4-character IDX ticker, for example BBCA, ISAT, PADA, or BBCA.JK.')
    return value


@st.cache_data(ttl=1800, show_spinner=False)
def cached_analysis_history(symbol: str) -> pd.DataFrame:
    symbol = _normalize_symbol(symbol)
    frames, errors = download_universe((symbol,), period='2y', chunk_size=1)
    frame = frames.get(symbol + '.JK')
    if frame is None or frame.empty:
        raise ValueError(errors.get(symbol + '.JK', 'Yahoo returned no data.'))
    return frame.copy()


@st.cache_data(ttl=21600, show_spinner=False)
def _idx_company_metadata() -> pd.DataFrame:
    try:
        return fetch_stock_screener_metadata()
    except Exception:
        return pd.DataFrame(columns=['Symbol', 'Company', 'Sector', 'SubSector'])


@st.cache_data(ttl=1800, show_spinner=False)
def _idx_foreign_history_20d() -> pd.DataFrame:
    """Cache the latest 20 IDX trading sessions once for all manual stock searches."""
    try:
        return fetch_idx_market_history(sessions=20, max_calendar_days=45)
    except Exception:
        return pd.DataFrame()


def _foreign_20d_context(symbol: str) -> dict:
    """Return the same 20D foreign-intensity definition used by Smart Money Screener."""
    hist = _idx_foreign_history_20d()
    if hist.empty:
        return {
            'ForeignIntensity20': np.nan,
            'ForeignPositiveDays20': 0,
            'IDXDate': 'latest',
        }

    g = hist[hist.Symbol.astype(str).str.upper() == symbol].copy()
    if g.empty:
        return {
            'ForeignIntensity20': np.nan,
            'ForeignPositiveDays20': 0,
            'IDXDate': 'latest',
        }

    g = g.sort_values('SessionDate').tail(20)
    buy = pd.to_numeric(g['ForeignBuy'], errors='coerce').fillna(0.0)
    sell = pd.to_numeric(g['ForeignSell'], errors='coerce').fillna(0.0)
    net = buy - sell
    gross = buy.abs() + sell.abs()
    gross_sum = float(gross.sum())
    intensity = float(net.sum() / gross_sum * 100.0) if gross_sum > 0 else np.nan

    dates = pd.to_datetime(g['SessionDate'], errors='coerce').dropna()
    idx_date = dates.max().date().isoformat() if not dates.empty else 'latest'
    return {
        'ForeignIntensity20': intensity,
        'ForeignPositiveDays20': int((net > 0).sum()),
        'IDXDate': idx_date,
    }


def _company_context(symbol: str, prefill: dict | None = None) -> dict:
    # When opened from Stock Pick, reuse its already-computed IDX foreign context
    # if available. Manual searches always obtain the same metric from cached IDX
    # 20-session stock summaries.
    foreign_ctx = _foreign_20d_context(symbol)

    if prefill and str(prefill.get('Symbol', '')).upper() == symbol:
        foreign = pd.to_numeric(prefill.get('ForeignIntensity20'), errors='coerce')
        positive_days = pd.to_numeric(prefill.get('ForeignPositiveDays20'), errors='coerce')
        return {
            'Company': str(prefill.get('Company') or symbol),
            'Sector': str(prefill.get('Sector') or 'IDX'),
            'SubSector': str(prefill.get('SubSector') or ''),
            'ForeignIntensity20': (
                float(foreign) if pd.notna(foreign)
                else foreign_ctx['ForeignIntensity20']
            ),
            'ForeignPositiveDays20': (
                int(positive_days) if pd.notna(positive_days)
                else foreign_ctx['ForeignPositiveDays20']
            ),
            'IDXDate': str(
                prefill.get('IDXDate')
                or foreign_ctx.get('IDXDate')
                or 'latest'
            ),
        }

    meta = _idx_company_metadata()
    hit = meta[meta.Symbol.astype(str).str.upper() == symbol] if not meta.empty else pd.DataFrame()
    if not hit.empty:
        r = hit.iloc[-1]
        return {
            'Company': str(r.get('Company') or symbol),
            'Sector': str(r.get('Sector') or 'IDX'),
            'SubSector': str(r.get('SubSector') or ''),
            'ForeignIntensity20': foreign_ctx['ForeignIntensity20'],
            'ForeignPositiveDays20': foreign_ctx['ForeignPositiveDays20'],
            'IDXDate': foreign_ctx['IDXDate'],
        }

    return {
        'Company': symbol,
        'Sector': 'IDX',
        'SubSector': '',
        'ForeignIntensity20': foreign_ctx['ForeignIntensity20'],
        'ForeignPositiveDays20': foreign_ctx['ForeignPositiveDays20'],
        'IDXDate': foreign_ctx['IDXDate'],
    }


def _enrich_metrics(symbol: str, raw: pd.DataFrame, prefill: dict | None = None) -> tuple[pd.Series, dict]:
    benchmark = cached_benchmark()
    bench_ret = _benchmark_returns(benchmark)
    base = _technical_row(symbol, raw, bench_ret)
    if not base:
        raise ValueError('Not enough usable history to calculate the analysis.')

    ctx = _company_context(symbol, prefill=prefill)
    base.update(ctx)
    foreign_display = base.get('ForeignIntensity20', np.nan)
    if pd.isna(base.get('ForeignIntensity20', np.nan)):
        base['ForeignIntensity20'] = 0.0
    r = pd.Series(base)
    r['ForeignAvailable'] = pd.notna(foreign_display)
    score = _score_row(r)
    for key, value in score.items():
        r[key] = value
    r['Setup'] = _setup_type(r)
    r['Why'] = _why(r)
    return r, bench_ret


def _analysis_frame(raw: pd.DataFrame) -> pd.DataFrame:
    d = raw.copy()
    d.columns = [str(c).title() for c in d.columns]
    d = d[['Open', 'High', 'Low', 'Close', 'Volume']].dropna().copy()
    c = pd.to_numeric(d.Close, errors='coerce')
    d['MA20'] = c.rolling(20).mean()
    d['MA50'] = c.rolling(50).mean()
    d['MA200'] = c.rolling(200).mean()
    return d


def _key_levels(raw: pd.DataFrame, r: pd.Series) -> dict:
    d = _analysis_frame(raw)
    h = pd.to_numeric(d.High, errors='coerce')
    l = pd.to_numeric(d.Low, errors='coerce')
    close = float(r.Close)
    atr = float(r.ATR) if pd.notna(r.ATR) and r.ATR > 0 else close * 0.03

    def prior_high(n: int) -> float:
        x = h.shift(1).tail(n).max()
        return float(x) if pd.notna(x) else np.nan

    def prior_low(n: int) -> float:
        x = l.shift(1).tail(n).min()
        return float(x) if pd.notna(x) else np.nan

    high10, high20, high55 = prior_high(10), prior_high(20), prior_high(55)
    low10, low20, low55 = prior_low(10), prior_low(20), prior_low(55)

    support_candidates = [
        ('MA20', r.MA20), ('MA50', r.MA50), ('10D swing low', low10),
        ('20D swing low', low20), ('55D swing low', low55),
    ]
    supports = [(name, float(v)) for name, v in support_candidates if pd.notna(v) and float(v) < close]
    supports = sorted(supports, key=lambda x: x[1], reverse=True)
    support1 = supports[0] if supports else ('ATR support', close - 1.5 * atr)
    support2 = supports[1] if len(supports) > 1 else ('Deeper support', close - 2.5 * atr)

    resistance_candidates = [
        ('10D pivot', high10), ('20D pivot', high20), ('55D resistance', high55),
    ]
    resistances = [(name, float(v)) for name, v in resistance_candidates if pd.notna(v) and float(v) > close]
    resistances = sorted(resistances, key=lambda x: x[1])
    resistance1 = resistances[0] if resistances else ('Next ATR objective', close + 1.5 * atr)
    resistance2 = resistances[1] if len(resistances) > 1 else ('Upper objective', close + 3.0 * atr)

    pivot = high20 if pd.notna(high20) else resistance1[1]
    return {
        'Support1Name': support1[0], 'Support1': support1[1],
        'Support2Name': support2[0], 'Support2': support2[1],
        'Resistance1Name': resistance1[0], 'Resistance1': resistance1[1],
        'Resistance2Name': resistance2[0], 'Resistance2': resistance2[1],
        'Pivot': float(pivot),
        'High10': high10, 'High20': high20, 'High55': high55,
        'Low10': low10, 'Low20': low20, 'Low55': low55,
    }


def _rr_targets(entry_mid: float, stop: float, reference_close: float) -> dict:
    risk = max(entry_mid - stop, entry_mid * 0.005)
    return {
        'RiskPerShare': risk,
        'RiskPct': risk / entry_mid * 100 if entry_mid else np.nan,
        'T1': round_idx_price(entry_mid + 2.0 * risk, reference_close, 'ceil'),
        'T2': round_idx_price(entry_mid + 3.0 * risk, reference_close, 'ceil'),
        'T3': round_idx_price(entry_mid + 4.0 * risk, reference_close, 'ceil'),
    }


def _entry_plan(r: pd.Series, levels: dict) -> dict:
    close = float(r.Close)
    atr = float(r.ATR) if pd.notna(r.ATR) and r.ATR > 0 else close * 0.03
    ma20 = float(r.MA20)
    ma50 = float(r.MA50)
    extension = float(r.ExtensionMA20) if pd.notna(r.ExtensionMA20) else 0.0
    rsi = float(r.RSI) if pd.notna(r.RSI) else 50.0

    trend_ok = bool(close > ma20 > ma50 and r.MA20Slope > 0)
    breakout_active = bool(r.Breakout20 and r.RelVolume >= 1.2)
    pullback_ready = bool(trend_ok and abs(extension) <= 3.0 and 45 <= rsi <= 65)
    early_reversal = bool(r.ReclaimMA20 and r.MACDImproving and rsi >= 45)
    extended = bool(extension > 8 or rsi > 75)

    if extended:
        status, status_kind = "EXTENDED — DON'T CHASE", 'warn'
    elif breakout_active:
        status, status_kind = 'BREAKOUT ACTIVE', 'good'
    elif pullback_ready:
        status, status_kind = 'ENTRY ZONE', 'good'
    elif trend_ok:
        status, status_kind = 'WAIT FOR PULLBACK', 'neutral'
    elif early_reversal:
        status, status_kind = 'EARLY REVERSAL WATCH', 'neutral'
    else:
        status, status_kind = 'WAIT FOR CONFIRMATION', 'warn'

    if breakout_active:
        primary_name = 'Breakout Continuation'
        entry_low = max(close - 0.10 * atr, 0)
        entry_high = close + 0.30 * atr
        stop_candidates = [close - 1.8 * atr, levels['Pivot'] - 0.55 * atr, ma20 - 0.25 * atr]
        stop = max(x for x in stop_candidates if x < entry_low)
        plan_note = 'Use only while the breakout holds above the prior pivot and volume remains constructive.'
    elif trend_ok:
        primary_name = 'Buy on Pullback'
        entry_low = max(ma20 - 0.30 * atr, 0)
        entry_high = ma20 + 0.35 * atr
        stop_candidates = [entry_low - 1.35 * atr, ma50 - 0.30 * atr, levels['Support2'] - 0.20 * atr]
        valid = [x for x in stop_candidates if x < entry_low]
        stop = max(valid) if valid else entry_low - 1.5 * atr
        plan_note = 'Prefer a controlled pullback toward rising MA20/support rather than chasing far above the trend line.'
    else:
        primary_name = 'Confirmation Entry'
        trigger = max(close, levels['Resistance1'])
        entry_low = trigger
        entry_high = trigger + 0.30 * atr
        stop_candidates = [ma20 - 0.50 * atr, close - 1.5 * atr, levels['Support1'] - 0.25 * atr]
        valid = [x for x in stop_candidates if x < entry_low]
        stop = max(valid) if valid else entry_low - 1.5 * atr
        plan_note = 'Wait for price to prove strength above the nearest pivot before treating the setup as active.'

    # Align executable prices to the IDX fraction applicable to the next
    # session, using the latest close as the reference close.
    entry_low = round_idx_price(entry_low, close, 'floor')
    entry_high = round_idx_price(entry_high, close, 'ceil')
    stop = round_idx_price(stop, close, 'floor')
    entry_mid = (entry_low + entry_high) / 2
    primary_rr = _rr_targets(entry_mid, stop, close)

    # Alternative breakout scenario is always available as a conditional plan.
    breakout_trigger = levels['Resistance1']
    if breakout_trigger <= close:
        breakout_trigger = max(levels['High55'] if pd.notna(levels['High55']) else close, close + 0.50 * atr)
    breakout_trigger = round_idx_price(breakout_trigger, close, 'ceil')
    alt_low = breakout_trigger
    alt_high = round_idx_price(breakout_trigger + 0.30 * atr, close, 'ceil')
    alt_mid = (alt_low + alt_high) / 2
    alt_stop_candidates = [levels['Pivot'] - 0.50 * atr, ma20 - 0.35 * atr, alt_low - 1.7 * atr]
    valid_alt = [x for x in alt_stop_candidates if x < alt_low]
    alt_stop_raw = max(valid_alt) if valid_alt else alt_low - 1.7 * atr
    alt_stop = round_idx_price(alt_stop_raw, close, 'floor')
    alt_rr = _rr_targets(alt_mid, alt_stop, close)

    invalidations = []
    invalidations.append(f'Daily close below {_fmt_price(stop)} invalidates the primary risk structure.')
    if trend_ok:
        invalidations.append('A decisive loss of MA20/MA50 trend structure weakens the medium-term setup.')
    else:
        invalidations.append('Avoid treating the setup as confirmed while price remains below a clean rising MA20/MA50 structure.')
    if r.RS20 > 0:
        invalidations.append('A turn of RS20 below zero would remove the current relative-strength advantage vs IHSG.')
    else:
        invalidations.append('RS20 is not positive yet; relative strength needs improvement for a higher-quality swing setup.')
    if breakout_active:
        invalidations.append('A breakout that falls back below the pivot on weak volume is a failed-breakout warning.')

    return {
        'Status': status, 'StatusKind': status_kind,
        'PrimaryName': primary_name,
        'EntryLow': entry_low, 'EntryHigh': entry_high, 'EntryMid': entry_mid,
        'Stop': stop, **primary_rr,
        'PlanNote': plan_note,
        'AltName': 'Breakout Entry', 'AltTrigger': breakout_trigger,
        'AltEntryLow': alt_low, 'AltEntryHigh': alt_high, 'AltStop': alt_stop,
        'AltT1': alt_rr['T1'], 'AltT2': alt_rr['T2'], 'AltT3': alt_rr['T3'],
        'AltRiskPct': alt_rr['RiskPct'],
        'IDXFraction': idx_price_fraction(close),
        'FractionReferenceClose': close,
        'Invalidations': invalidations,
    }


def _summary(r: pd.Series, plan: dict, levels: dict) -> str:
    trend_text = 'a constructive medium-term uptrend' if r.Close > r.MA20 > r.MA50 and r.MA20Slope > 0 else 'a mixed medium-term structure'
    rs_text = (
        f'relative strength remains positive versus IHSG (RS20 {_fmt_pct(r.RS20)}, RS60 {_fmt_pct(r.RS60)})'
        if r.RS20 > 0 and r.RS60 > 0
        else f'relative strength is still mixed versus IHSG (RS20 {_fmt_pct(r.RS20)}, RS60 {_fmt_pct(r.RS60)})'
    )
    momentum = 'momentum is constructive' if r.MACDImproving and 45 <= r.RSI <= 70 else 'momentum still needs cleaner confirmation'
    flow = 'money flow is supportive' if r.CMF20 > 0 and r.OBVUp else 'money-flow confirmation is mixed'
    action = {
        'ENTRY ZONE': f'The cleaner research setup is the pullback zone around {_fmt_price(plan["EntryLow"])}–{_fmt_price(plan["EntryHigh"])}.',
        'WAIT FOR PULLBACK': f'Price is better monitored for a pullback toward MA20/support around {_fmt_price(plan["EntryLow"])}–{_fmt_price(plan["EntryHigh"])} rather than chased.',
        'BREAKOUT ACTIVE': f'The breakout is active; continuation quality depends on holding above the pivot near {_fmt_price(levels["Pivot"])} with volume support.',
        "EXTENDED — DON'T CHASE": f'Price is extended from MA20; a reset toward support is preferable to chasing at the current extension.',
        'EARLY REVERSAL WATCH': f'The setup is early; a stronger move through nearby resistance around {_fmt_price(levels["Resistance1"])} would improve confirmation.',
        'WAIT FOR CONFIRMATION': f'The structure is not clean enough yet; a move through nearby resistance around {_fmt_price(levels["Resistance1"])} would improve the setup.',
    }.get(plan['Status'], '')
    return f'{r.Symbol} currently shows {trend_text}; {rs_text}. {momentum}, while {flow}. {action}'


def _chart(raw: pd.DataFrame, symbol: str, levels: dict) -> go.Figure:
    d = _analysis_frame(raw).tail(170)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=d.index, open=d.Open, high=d.High, low=d.Low, close=d.Close,
        name=symbol,
        increasing_line_color='#2fb57c', increasing_fillcolor='#2fb57c',
        decreasing_line_color='#e5534b', decreasing_fillcolor='#e5534b',
    ))
    for label, col, color in [
        ('MA20', 'MA20', '#2f80ed'), ('MA50', 'MA50', '#f2994a'), ('MA200', 'MA200', '#9b51e0')
    ]:
        fig.add_trace(go.Scatter(x=d.index, y=d[col], mode='lines', name=label, line=dict(color=color, width=1.6)))
    for name, value, color in [
        ('Support', levels['Support1'], '#2a9d66'),
        ('Pivot / Resistance', levels['Resistance1'], '#d27a2c'),
    ]:
        fig.add_hline(y=value, line_dash='dot', line_width=1.2, line_color=color,
                      annotation_text=f'{name} {_fmt_price(value)}', annotation_position='top left')
    fig.update_layout(
        height=500, template='plotly_white', margin=dict(l=5, r=8, t=10, b=5),
        xaxis_rangeslider_visible=False, hovermode='x unified',
        paper_bgcolor='white', plot_bgcolor='white',
        legend=dict(orientation='h', yanchor='bottom', y=1.01, xanchor='left', x=0, font=dict(size=11)),
    )
    fig.update_xaxes(rangebreaks=[dict(bounds=['sat', 'mon'])], showgrid=False)
    fig.update_yaxes(side='right', gridcolor='#eef1ef', tickformat=',.0f')
    return fig


def _metric_chip(text: str, kind: str = '') -> str:
    suffix = f' sa-chip-{kind}' if kind else ''
    return f'<span class="sa-chip{suffix}">{html.escape(str(text))}</span>'


def render_stock_analysis(navigate=None) -> None:
    if 'analysis_symbol' not in st.session_state:
        st.session_state.analysis_symbol = st.session_state.get('dashboard_symbol', 'BBCA')
    if 'analysis_search' not in st.session_state:
        st.session_state.analysis_search = st.session_state.analysis_symbol

    title_col, search_col = st.columns([4.8, 1.2], vertical_alignment='bottom')
    with title_col:
        st.markdown(
            '<div class="sa-title">Stock Analysis</div>'
            '<div class="sa-subtitle">Single-stock swing analysis with technical structure, key levels and a conditional entry plan.</div>',
            unsafe_allow_html=True,
        )
    with search_col:
        st.markdown('<div class="sa-search-wrap">', unsafe_allow_html=True)
        with st.form('stock_analysis_search_form', border=False):
            search = st.text_input(
                'Ticker', value=st.session_state.analysis_search,
                placeholder='BBCA / ISAT / PADA', label_visibility='collapsed'
            )
            submitted = st.form_submit_button('Analyze', icon=':material/search:', width='stretch')
        st.markdown('</div>', unsafe_allow_html=True)
        if submitted:
            try:
                selected = _normalize_symbol(search)
                st.session_state.analysis_symbol = selected
                st.session_state.analysis_search = selected
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    symbol = _normalize_symbol(st.session_state.analysis_symbol)
    with st.spinner(f'Loading {symbol} analysis... please wait'):
        try:
            raw = cached_analysis_history(symbol)
            prefill = st.session_state.get('analysis_prefill')
            r, bench_ret = _enrich_metrics(symbol, raw, prefill=prefill)
            levels = _key_levels(raw, r)
            plan = _entry_plan(r, levels)
        except Exception as exc:
            st.error(f'{symbol} analysis could not be built: {exc}')
            return

    grade, grade_kind = _grade(r.StockPickScore)
    with st.container(border=True):
        left, middle, right = st.columns([2.4, 2.5, 1.3], vertical_alignment='center')
        left.markdown(
            f'<div class="sa-identity"><b>{html.escape(symbol)}</b>'
            f'<span>{html.escape(str(r.Company))}</span>'
            f'<small>{html.escape(str(r.Sector))}</small></div>',
            unsafe_allow_html=True,
        )
        middle.markdown(
            '<div class="sa-chip-row">'
            + _metric_chip(str(r.Setup), 'good' if r.StockPickScore >= 70 else 'neutral')
            + _metric_chip(f'RS20 {_fmt_pct(r.RS20)}', 'good' if r.RS20 > 0 else 'bad')
            + _metric_chip(f'RS60 {_fmt_pct(r.RS60)}', 'good' if r.RS60 > 0 else 'bad')
            + _metric_chip(f'ATR {r.ATRPct:.1f}%', 'neutral')
            + '</div>',
            unsafe_allow_html=True,
        )
        right.markdown(
            f'<div class="sa-score sa-score-{grade_kind}">{int(r.StockPickScore)}<span>{grade}</span></div>',
            unsafe_allow_html=True,
        )

        m = st.columns(6)
        m[0].metric('Price', _fmt_price(r.Close), f'20D Return {_fmt_pct(r.Return20)}')
        m[1].metric('RSI 14', f'{r.RSI:.0f}')
        m[2].metric('ADX 14', f'{r.ADX:.0f}')
        m[3].metric('Rel Volume', f'{r.RelVolume:.2f}×')
        m[4].metric('CMF20', f'{r.CMF20:+.2f}')
        m[5].metric('Foreign 20D', f'{r.ForeignIntensity20:+.1f}%' if bool(r.ForeignAvailable) else '—')

    st.markdown(
        f'<div class="sa-status sa-status-{plan["StatusKind"]}"><b>{html.escape(plan["Status"])}</b>'
        f'<span>{html.escape(str(r.Why))}</span></div>',
        unsafe_allow_html=True,
    )

    chart_col, structure_col = st.columns([2.15, 1], vertical_alignment='top')
    with chart_col:
        with st.container(border=True):
            st.markdown('<div class="sa-section-title">Price structure</div>', unsafe_allow_html=True)
            st.plotly_chart(_chart(raw, symbol, levels), width='stretch', config={'displayModeBar': False})

    with structure_col:
        with st.container(border=True):
            st.markdown('<div class="sa-section-title">Technical structure</div>', unsafe_allow_html=True)
            rows = [
                ('MA20', _fmt_price(r.MA20), '↑' if r.MA20Slope > 0 else '↓'),
                ('MA50', _fmt_price(r.MA50), '↑' if r.MA50Slope > 0 else '↓'),
                ('MA200', _fmt_price(r.MA200), 'Above' if r.Close > r.MA200 else 'Below'),
                ('RS20 vs IHSG', _fmt_pct(r.RS20), 'Strong' if r.RS20 > 0 else 'Weak'),
                ('RS60 vs IHSG', _fmt_pct(r.RS60), 'Strong' if r.RS60 > 0 else 'Weak'),
                ('MACD', 'Positive' if r.MACDPositive else 'Negative', 'Improving' if r.MACDImproving else 'Soft'),
                ('OBV', 'Rising' if r.OBVUp else 'Falling', ''),
                ('Golden Cross', 'Yes' if r.GoldenCross else 'No', ''),
            ]
            html_rows = ''.join(
                f'<div class="sa-kv"><span>{html.escape(a)}</span><b>{html.escape(str(b))}</b><small>{html.escape(str(c))}</small></div>'
                for a, b, c in rows
            )
            st.markdown('<div class="sa-kv-wrap">' + html_rows + '</div>', unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown('<div class="sa-section-title">Key levels</div>', unsafe_allow_html=True)
            level_rows = [
                ('Resistance 2', levels['Resistance2'], levels['Resistance2Name']),
                ('Resistance 1', levels['Resistance1'], levels['Resistance1Name']),
                ('20D Pivot', levels['Pivot'], 'breakout reference'),
                ('Support 1', levels['Support1'], levels['Support1Name']),
                ('Support 2', levels['Support2'], levels['Support2Name']),
            ]
            st.markdown(
                '<div class="sa-levels">' + ''.join(
                    f'<div><span>{html.escape(label)}</span><b>{_fmt_price(value)}</b><small>{html.escape(note)}</small></div>'
                    for label, value, note in level_rows
                ) + '</div>', unsafe_allow_html=True
            )

    st.markdown('<div class="sa-section-heading">Entry plan</div>', unsafe_allow_html=True)
    p1, p2 = st.columns(2, vertical_alignment='top')
    with p1:
        with st.container(border=True):
            st.markdown(f'<div class="sa-plan-title">PRIMARY — {html.escape(plan["PrimaryName"])}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="sa-plan-grid">'
                f'<div><span>Entry zone</span><b>{_fmt_price(plan["EntryLow"])}–{_fmt_price(plan["EntryHigh"])}</b></div>'
                f'<div><span>Stop</span><b>{_fmt_price(plan["Stop"])}</b></div>'
                f'<div><span>Target 1</span><b>{_fmt_price(plan["T1"])}</b><small>2R</small></div>'
                f'<div><span>Target 2</span><b>{_fmt_price(plan["T2"])}</b><small>3R</small></div>'
                f'<div><span>Target 3</span><b>{_fmt_price(plan["T3"])}</b><small>4R</small></div>'
                f'<div><span>Risk to stop</span><b>{plan["RiskPct"]:.1f}%</b></div>'
                f'</div>', unsafe_allow_html=True
            )
            st.caption(plan['PlanNote'])

    with p2:
        with st.container(border=True):
            st.markdown('<div class="sa-plan-title">ALTERNATIVE — Breakout Entry</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="sa-plan-grid">'
                f'<div><span>Trigger</span><b>&gt; {_fmt_price(plan["AltTrigger"])}</b></div>'
                f'<div><span>Entry zone</span><b>{_fmt_price(plan["AltEntryLow"])}–{_fmt_price(plan["AltEntryHigh"])}</b></div>'
                f'<div><span>Stop</span><b>{_fmt_price(plan["AltStop"])}</b></div>'
                f'<div><span>Target 1</span><b>{_fmt_price(plan["AltT1"])}</b><small>2R</small></div>'
                f'<div><span>Target 2</span><b>{_fmt_price(plan["AltT2"])}</b><small>3R</small></div>'
                f'<div><span>Target 3</span><b>{_fmt_price(plan["AltT3"])}</b><small>4R</small></div>'
                f'</div>', unsafe_allow_html=True
            )
            st.caption('Alternative plan only activates if price clears resistance/pivot with healthy participation; avoid treating a weak-volume poke as confirmation.')

    s1, s2 = st.columns([1.35, 1], vertical_alignment='top')
    with s1:
        with st.container(border=True):
            st.markdown('<div class="sa-section-title">Analysis summary</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="sa-summary">{html.escape(_summary(r, plan, levels))}</div>', unsafe_allow_html=True)
    with s2:
        with st.container(border=True):
            st.markdown('<div class="sa-section-title">Invalidation / avoid</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="sa-invalidation">' + ''.join(f'<div>• {html.escape(x)}</div>' for x in plan['Invalidations']) + '</div>',
                unsafe_allow_html=True,
            )

    a, b = st.columns([1, 4])
    if a.button('Open Dashboard', icon=':material/show_chart:', width='stretch', key='sa_dashboard'):
        st.session_state.dashboard_symbol = symbol
        st.session_state.dashboard_search = symbol
        if navigate:
            navigate('Dashboard')
        st.rerun()
    b.caption(
        f'Yahoo daily OHLCV + IHSG relative strength · IDX context as of {r.IDXDate}. '
        'Entry/stop/targets are mechanical swing-research scenarios, not guarantees or personalized financial advice.'
    )
