from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf

from market import parse_csv
from yahoo_download import download_universe


COMPANY_NAME_OVERRIDES = {
    'BBCA': 'Bank Central Asia',
    'BBRI': 'Bank Rakyat Indonesia',
    'BMRI': 'Bank Mandiri',
    'BBNI': 'Bank Negara Indonesia',
    'TLKM': 'Telkom Indonesia',
    'ISAT': 'Indosat Ooredoo Hutchison',
    'ASII': 'Astra International',
    'ANTM': 'Aneka Tambang',
    'AMMN': 'Amman Mineral Internasional',
    'ADRO': 'Alamtri Resources Indonesia',
    'UNTR': 'United Tractors',
    'ICBP': 'Indofood CBP Sukses Makmur',
    'INDF': 'Indofood Sukses Makmur',
    'AMRT': 'Sumber Alfaria Trijaya',
    'MEDC': 'Medco Energi Internasional',
    'PTBA': 'Bukit Asam',
    'PADA': 'Personel Alih Daya',
}

PERIOD_BARS = {'1M': 22, '3M': 66, '6M': 132, '1Y': 260}


def normalize_dashboard_symbol(text: str) -> str:
    value = (text or '').strip().upper()
    if value.endswith('.JK'):
        value = value[:-3]
    if not re.fullmatch(r'[A-Z0-9]{4}', value):
        raise ValueError('Use a 4-character IDX ticker, for example BBCA, ISAT, TLKM, or BBCA.JK.')
    return value


def fetch_dashboard_stock(symbol: str, period: str = '2y') -> pd.DataFrame:
    """Fetch one IDX stock for the Dashboard only.

    This deliberately does not depend on the 200-stock universe session. It uses the
    same Yahoo/yfinance downloader as the screener, but requests only one symbol.
    """
    symbol = normalize_dashboard_symbol(symbol)
    raw_frames, errors = download_universe((symbol,), period=period, chunk_size=1)
    yahoo_symbol = symbol + '.JK'
    if yahoo_symbol not in raw_frames:
        raise ValueError(errors.get(yahoo_symbol, 'Yahoo returned no data.'))

    raw = raw_frames[yahoo_symbol].copy().reset_index()
    raw = raw.rename(columns={raw.columns[0]: 'date', **{c: str(c).lower() for c in raw.columns[1:]}})
    raw['date'] = pd.to_datetime(raw['date'])
    if raw.date.dt.tz is not None:
        raw['date'] = raw.date.dt.tz_convert('Asia/Jakarta').dt.tz_localize(None)
    raw['date'] = raw.date.dt.strftime('%Y-%m-%d')
    raw['symbol'] = symbol
    clean = parse_csv(raw.to_csv(index=False).encode())
    if clean.empty:
        raise ValueError('Yahoo returned no usable daily bars.')
    return clean


@st.cache_data(ttl=900, show_spinner=False)
def cached_dashboard_stock(symbol: str) -> pd.DataFrame:
    return fetch_dashboard_stock(symbol, '2y')


@st.cache_data(ttl=86400, show_spinner=False)
def cached_company_name(symbol: str) -> str:
    symbol = normalize_dashboard_symbol(symbol)
    if symbol in COMPANY_NAME_OVERRIDES:
        return COMPANY_NAME_OVERRIDES[symbol]
    try:
        t = yf.Ticker(symbol + '.JK')
        info = {}
        try:
            info = t.get_info() or {}
        except Exception:
            info = getattr(t, 'info', {}) or {}
        for key in ('longName', 'shortName', 'displayName', 'name'):
            val = info.get(key)
            if isinstance(val, str) and val.strip():
                clean = val.strip()
                if clean.upper().endswith('.JK'):
                    clean = clean[:-3].strip()
                return clean
    except Exception:
        pass
    return symbol


def _fmt_volume(value: float) -> str:
    value = float(value)
    if abs(value) >= 1_000_000_000:
        return f'{value / 1_000_000_000:.2f}B'
    if abs(value) >= 1_000_000:
        return f'{value / 1_000_000:.3f}M'
    if abs(value) >= 1_000:
        return f'{value / 1_000:.1f}K'
    return f'{value:,.0f}'


def _stock_chart(frame: pd.DataFrame, symbol: str, indicators: list[str] | tuple[str, ...] | None = None) -> go.Figure:
    frame = frame.copy()
    frame['ma20'] = frame['close'].rolling(20, min_periods=1).mean()
    frame['ma50'] = frame['close'].rolling(50, min_periods=1).mean()
    frame['ma200'] = frame['close'].rolling(200, min_periods=1).mean()
    typical_price = (frame['high'] + frame['low'] + frame['close']) / 3.0
    vol_cum = frame['volume'].cumsum().replace(0, pd.NA)
    frame['vwap'] = (typical_price * frame['volume']).cumsum() / vol_cum
    indicators = list(indicators or [])

    last_close = float(frame.close.iloc[-1])
    volume_colors = [
        'rgba(43,177,116,.20)' if c >= o else 'rgba(231,76,72,.20)'
        for o, c in zip(frame.open, frame.close)
    ]
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.015,
        row_heights=[0.80, 0.20],
    )
    fig.add_trace(
        go.Candlestick(
            x=frame.date,
            open=frame.open,
            high=frame.high,
            low=frame.low,
            close=frame.close,
            name=symbol,
            increasing_line_color='#2fb57c',
            increasing_fillcolor='#2fb57c',
            decreasing_line_color='#e5534b',
            decreasing_fillcolor='#e5534b',
        ),
        row=1,
        col=1,
    )
    overlays = [
        ('MA20', 'ma20', '#2f80ed'),
        ('MA50', 'ma50', '#f2994a'),
        ('MA200', 'ma200', '#9b51e0'),
        ('VWAP', 'vwap', '#c039a1'),
    ]
    for label, col_name, color in overlays:
        if label in indicators:
            fig.add_trace(
                go.Scatter(
                    x=frame.date,
                    y=frame[col_name],
                    mode='lines',
                    name=label,
                    line=dict(color=color, width=1.9),
                    hovertemplate=f'{label}: %{{y:,.2f}}<extra></extra>',
                ),
                row=1,
                col=1,
            )
    fig.add_trace(
        go.Bar(x=frame.date, y=frame.volume, name='Volume', marker_color=volume_colors, showlegend=False),
        row=2,
        col=1,
    )
    fig.add_hline(
        y=last_close,
        line_dash='dot',
        line_width=1,
        line_color='#e5534b',
        row=1,
        col=1,
    )
    fig.add_annotation(
        x=1,
        xref='paper',
        y=last_close,
        yref='y',
        text=f'{last_close:,.0f}',
        showarrow=False,
        xanchor='right',
        bgcolor='#e5534b',
        bordercolor='#e5534b',
        font=dict(color='white', size=12),
        borderpad=4,
    )
    fig.update_layout(
        height=530,
        template='plotly_white',
        margin=dict(l=5, r=8, t=8, b=5),
        showlegend=bool(indicators),
        legend=dict(
            orientation='h', yanchor='bottom', y=1.01, xanchor='left', x=0,
            bgcolor='rgba(255,255,255,0.85)', bordercolor='#e6ece8', borderwidth=1,
            font=dict(size=11)
        ),
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
        paper_bgcolor='white',
        plot_bgcolor='white',
    )
    fig.update_xaxes(
        rangebreaks=[dict(bounds=['sat', 'mon'])],
        showgrid=False,
        zeroline=False,
    )
    fig.update_yaxes(
        side='right',
        gridcolor='#eef1ef',
        zeroline=False,
        tickformat=',.0f',
        row=1,
        col=1,
    )
    fig.update_yaxes(showticklabels=False, showgrid=False, zeroline=False, row=2, col=1)
    return fig


def render_dashboard(navigate=None) -> None:
    if 'dashboard_symbol' not in st.session_state:
        st.session_state.dashboard_symbol = 'BBCA'
    if 'dashboard_search' not in st.session_state:
        st.session_state.dashboard_search = 'BBCA'

    title_col, search_col = st.columns([5.0, 1.2], vertical_alignment='bottom')
    with title_col:
        st.markdown(
            '<div class="dashboard-title">Dashboard</div>'
            '<div class="dashboard-subtitle">Monitor one IDX stock instantly, then jump into deeper HP Screener analysis.</div>',
            unsafe_allow_html=True,
        )
    with search_col:
        st.markdown('<div class="dashboard-search-wrap">', unsafe_allow_html=True)
        with st.form('dashboard_search_form', border=False):
            search = st.text_input(
                'Search stock',
                value=st.session_state.dashboard_search,
                placeholder='BBCA / ISAT / TLKM',
                label_visibility='collapsed',
            )
            submitted = st.form_submit_button('Search', icon=':material/search:', width='stretch')
        st.markdown('</div>', unsafe_allow_html=True)
        if submitted:
            try:
                selected = normalize_dashboard_symbol(search)
                st.session_state.dashboard_symbol = selected
                st.session_state.dashboard_search = selected
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    symbol = st.session_state.dashboard_symbol
    try:
        with st.spinner(f'Loading {symbol}.JK…'):
            full = cached_dashboard_stock(symbol)
    except Exception as exc:
        st.markdown(
            f'<div class="dashboard-error"><b>{symbol}.JK could not be loaded.</b><br>{str(exc)}</div>',
            unsafe_allow_html=True,
        )
        a, b = st.columns([1, 4])
        if a.button('Retry', type='primary', key='dashboard_retry'):
            cached_dashboard_stock.clear()
            st.rerun()
        b.caption('Market Overview remains available from the left menu.')
        return

    with st.container(border=True):
        header_left, header_right = st.columns([4.7, 1.3], vertical_alignment='center')
        with header_left:
            st.markdown(
                f'<div class="stock-identity">'
                f'<div><div class="stock-symbol">{symbol}</div>'
                f'<div class="stock-name">{cached_company_name(symbol)}</div></div></div>',
                unsafe_allow_html=True,
            )
        with header_right:
            c1, c2 = st.columns(2)
            if c1.button('Details', icon=':material/visibility:', width='stretch', key='dashboard_details'):
                st.session_state.dashboard_show_details = not st.session_state.get('dashboard_show_details', False)
                st.rerun()
            if c2.button('Market', icon=':material/public:', width='stretch', key='dashboard_market'):
                if navigate:
                    navigate('Market Overview')
                st.rerun()

        period = st.segmented_control(
            'Chart period',
            options=list(PERIOD_BARS),
            default='6M',
            selection_mode='single',
            label_visibility='collapsed',
            key='dashboard_period',
        ) or '6M'
        frame = full.tail(PERIOD_BARS[period]).copy()
        last = frame.iloc[-1]
        first_close = float(frame.close.iloc[0])
        change = float(last.close - first_close)
        change_pct = change / first_close * 100 if first_close else 0.0
        avg_volume = float(frame.volume.mean())

        top1, top2, top3 = st.columns([1.15, .75, .75])
        top1.markdown(
            f'<div class="stock-price">{last.close:,.0f} '
            f'<span class="stock-change {"up" if change >= 0 else "down"}">{change:+,.0f} ({change_pct:+.2f}%)</span></div>'
            f'<div class="stock-period-label">Past {period}</div>',
            unsafe_allow_html=True,
        )
        top2.markdown(f'<div class="mini-number">{_fmt_volume(last.volume)}</div><div class="mini-label">Volume</div>', unsafe_allow_html=True)
        top3.markdown(f'<div class="mini-number">{_fmt_volume(avg_volume)}</div><div class="mini-label">Avg Volume</div>', unsafe_allow_html=True)

        metric_cols = st.columns(5)
        metric_values = [
            ('CLOSE', f'{last.close:,.0f}'),
            (f'{period} HIGH', f'{frame.high.max():,.0f}'),
            (f'{period} LOW', f'{frame.low.min():,.0f}'),
            ('AVG VOLUME', _fmt_volume(avg_volume)),
            ('BARS', f'{len(frame):,}'),
        ]
        for col, (label, value) in zip(metric_cols, metric_values):
            col.markdown(
                f'<div class="dashboard-metric"><div class="dashboard-metric-label">{label}</div>'
                f'<div class="dashboard-metric-value">{value}</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown('<div class="dashboard-indicator-gap"></div>', unsafe_allow_html=True)
        indicator_options = ['MA20', 'MA50', 'MA200', 'VWAP']
        indicators = st.segmented_control(
            'Indicators',
            options=indicator_options,
            default=['MA20', 'MA50', 'MA200', 'VWAP'],
            selection_mode='multi',
            label_visibility='collapsed',
            key='dashboard_indicators',
        ) or []

        st.plotly_chart(_stock_chart(frame, symbol, indicators), width='stretch', config={'displayModeBar': False})

        if st.session_state.get('dashboard_show_details', False):
            with st.expander('Latest daily bars', expanded=True):
                detail = frame.tail(15)[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
                detail.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
                st.dataframe(detail.sort_values('Date', ascending=False), hide_index=True, width='stretch')
