from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components


def _fmt_large(value: float, currency: bool = False) -> str:
    value = float(value or 0)
    prefix = 'Rp' if currency else ''
    abs_value = abs(value)
    if abs_value >= 1e12:
        return f'{prefix}{value/1e12:,.2f}T'
    if abs_value >= 1e9:
        return f'{prefix}{value/1e9:,.2f}B'
    if abs_value >= 1e6:
        return f'{prefix}{value/1e6:,.2f}M'
    if abs_value >= 1e3:
        return f'{prefix}{value/1e3:,.1f}K'
    return f'{prefix}{value:,.0f}'


def _latest_activity(prices: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    if prices is None or prices.empty or results is None or results.empty:
        return pd.DataFrame()
    latest = (
        prices.sort_values(['symbol', 'date'])
        .groupby('symbol', as_index=False)
        .tail(1)[['symbol', 'close', 'volume', 'date']]
        .rename(columns={'symbol': 'Symbol', 'close': 'BarClose', 'volume': 'BarVolume', 'date': 'BarDate'})
    )
    d = results.merge(latest, on='Symbol', how='inner')
    d['TradedValue'] = d['BarClose'] * d['BarVolume']
    d['Direction'] = d['ChangePct'].apply(lambda x: 'Up' if x > 0 else ('Down' if x < 0 else 'Flat'))
    return d


def _activity_figure(activity: pd.DataFrame, mode: str) -> go.Figure:
    if mode == 'VALUE':
        up = activity.loc[activity.Direction == 'Up', 'TradedValue'].sum()
        down = activity.loc[activity.Direction == 'Down', 'TradedValue'].sum()
        flat = activity.loc[activity.Direction == 'Flat', 'TradedValue'].sum()
        values = [up, down, flat]
        names = ['Advancing', 'Declining', 'Unchanged']
        text = [_fmt_large(v, True) for v in values]
        y_title = 'Estimated traded value'
    elif mode == 'VOLUME':
        up = activity.loc[activity.Direction == 'Up', 'BarVolume'].sum()
        down = activity.loc[activity.Direction == 'Down', 'BarVolume'].sum()
        flat = activity.loc[activity.Direction == 'Flat', 'BarVolume'].sum()
        values = [up, down, flat]
        names = ['Advancing', 'Declining', 'Unchanged']
        text = [_fmt_large(v) for v in values]
        y_title = 'Shares traded'
    else:
        up = int((activity.Direction == 'Up').sum())
        down = int((activity.Direction == 'Down').sum())
        flat = int((activity.Direction == 'Flat').sum())
        values = [up, down, flat]
        names = ['Advancing', 'Declining', 'Unchanged']
        text = [f'{v:,}' for v in values]
        y_title = 'Stocks'

    colors = ['#42b883', '#e65a55', '#aab2ad']
    fig = go.Figure(
        go.Bar(
            x=names,
            y=values,
            marker_color=colors,
            text=text,
            textposition='outside',
            cliponaxis=False,
            hovertemplate='%{x}<br>%{text}<extra></extra>',
        )
    )
    fig.update_layout(
        height=345,
        margin=dict(l=8, r=8, t=25, b=10),
        template='plotly_white',
        showlegend=False,
        yaxis_title=y_title,
        paper_bgcolor='white',
        plot_bgcolor='white',
        bargap=.36,
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor='#eef1ef', zeroline=False, showticklabels=False)
    return fig


def _render_activity_card(activity: pd.DataFrame, report: pd.DataFrame | None, fetched_at: str | None) -> None:
    header_left, header_right = st.columns([3, 1], vertical_alignment='center')
    with header_left:
        st.markdown('<div class="market-card-title">Yahoo Market Activity</div>', unsafe_allow_html=True)
        st.caption('Price/volume breadth from the loaded IDX universe — not foreign-flow data.')
    with header_right:
        if st.button('Refresh', icon=':material/refresh:', width='stretch', key='market_overview_refresh'):
            st.session_state.pop('market_overview_bundle', None)
            st.session_state['market_overview_refresh_requested'] = True
            st.rerun()

    mode = st.segmented_control(
        'Activity mode', ['VALUE', 'VOLUME', 'BREADTH'], default='VALUE',
        label_visibility='collapsed', key='market_activity_mode'
    ) or 'VALUE'

    if activity.empty:
        st.markdown(
            '<div class="market-empty-small"><b>No Yahoo breadth data loaded yet.</b><br>'
            'Load the Quality 200 once to calculate market breadth, estimated traded value and volume activity.</div>',
            unsafe_allow_html=True,
        )
        return

    advances = int((activity.Direction == 'Up').sum())
    declines = int((activity.Direction == 'Down').sum())
    flats = int((activity.Direction == 'Flat').sum())
    total = len(activity)
    net_breadth = advances - declines
    total_value = float(activity.TradedValue.sum())
    up_value = float(activity.loc[activity.Direction == 'Up', 'TradedValue'].sum())
    down_value = float(activity.loc[activity.Direction == 'Down', 'TradedValue'].sum())

    k1, k2, k3 = st.columns(3)
    k1.markdown(f'<div class="market-mini"><span>ADVANCING</span><b class="positive">{advances}</b></div>', unsafe_allow_html=True)
    k2.markdown(f'<div class="market-mini"><span>DECLINING</span><b class="negative">{declines}</b></div>', unsafe_allow_html=True)
    k3.markdown(f'<div class="market-mini"><span>NET BREADTH</span><b>{net_breadth:+d}</b></div>', unsafe_allow_html=True)

    st.plotly_chart(_activity_figure(activity, mode), width='stretch', config={'displayModeBar': False})

    if mode == 'VALUE':
        st.markdown(
            f'<div class="market-summary-line"><span>Total value <b>{_fmt_large(total_value, True)}</b></span>'
            f'<span class="positive">Up {_fmt_large(up_value, True)}</span>'
            f'<span class="negative">Down {_fmt_large(down_value, True)}</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="market-summary-line"><span>Universe <b>{total}</b></span>'
            f'<span>Unchanged <b>{flats}</b></span></div>',
            unsafe_allow_html=True,
        )

    good = int(report.Status.eq('OK').sum()) if report is not None and not report.empty and 'Status' in report else total
    requested = len(report) if report is not None and not report.empty else total
    stamp = fetched_at or ''
    st.caption(f'Yahoo Finance · {good}/{requested} usable tickers' + (f' · retrieved {stamp}' if stamp else ''))


def _tradingview_heatmap_html() -> str:
    # TradingView documents IDX as an available EOD market. The widget keeps its own
    # toolbar/data-source selector enabled so the user can switch datasets if needed.
    config = r'''{
      "exchanges": ["IDX"],
      "dataSource": "Indonesia",
      "grouping": "sector",
      "blockSize": "market_cap_basic",
      "blockColor": "change",
      "locale": "en",
      "symbolUrl": "https://www.tradingview.com/symbols/IDX-{symbol}/",
      "colorTheme": "light",
      "hasTopBar": true,
      "isDataSetEnabled": true,
      "isZoomEnabled": true,
      "hasSymbolTooltip": true,
      "isMonoSize": false,
      "width": "100%",
      "height": "100%"
    }'''
    return f'''
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
html,body{{margin:0;padding:0;background:#fff;font-family:Arial,sans-serif;overflow:hidden}}
.wrap{{height:650px;border:0;background:#fff}}
.tradingview-widget-container,.tradingview-widget-container__widget{{height:100%;width:100%}}
.tradingview-widget-copyright{{font-size:11px;text-align:center;color:#7b817d;padding-top:3px}}
a{{color:#4a6154;text-decoration:none}}
</style>
</head>
<body>
<div class="wrap">
  <div class="tradingview-widget-container">
    <div class="tradingview-widget-container__widget"></div>
    <div class="tradingview-widget-copyright">
      <a href="https://www.tradingview.com/heatmap/stock/" rel="noopener nofollow" target="_blank">Stock Heatmap</a> by TradingView
    </div>
    <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js" async>
    {config}
    </script>
  </div>
</div>
</body>
</html>
'''


def render_market_overview(cached_yahoo, cached_scan, quality_universe) -> None:
    st.markdown(
        '<div class="market-title">Market Overview</div>'
        '<div class="market-subtitle">IDX breadth from Yahoo Finance with an embedded TradingView sector heatmap.</div>',
        unsafe_allow_html=True,
    )

    bundle = st.session_state.get('market_overview_bundle')
    if bundle is None:
        # Reuse a previously fetched full/large universe when possible.
        candidate = st.session_state.get('yahoo_bundle')
        if candidate is not None:
            try:
                cp, cr, ct = candidate
                if cr is not None and len(cr) >= 100 and cp is not None and not cp.empty:
                    bundle = candidate
            except Exception:
                pass

    requested_refresh = st.session_state.pop('market_overview_refresh_requested', False)
    load_col, status_col = st.columns([1.25, 3.75], vertical_alignment='center')
    with load_col:
        load = st.button(
            'Load Quality 200' if bundle is None else 'Reload Quality 200',
            icon=':material/download:', type='primary' if bundle is None else 'secondary',
            width='stretch', key='load_market_overview_200'
        )
    with status_col:
        st.caption('Yahoo is used only for breadth/activity. TradingView supplies the sector heatmap independently.')

    if load or requested_refresh:
        try:
            symbols = quality_universe()
            with st.spinner(f'Loading {len(symbols)} IDX stocks from Yahoo in batches…'):
                bundle = cached_yahoo(symbols, '1y', False, 60)
            st.session_state['market_overview_bundle'] = bundle
            st.rerun()
        except Exception as exc:
            st.error(f'Yahoo market breadth could not be loaded: {exc}')

    activity = pd.DataFrame()
    report = None
    fetched_at = None
    if bundle is not None:
        try:
            prices, report, fetched_at = bundle
            if prices is not None and not prices.empty:
                results = cached_scan(prices)
                activity = _latest_activity(prices, results)
        except Exception as exc:
            st.warning(f'Yahoo breadth data is unavailable: {exc}')

    left, right = st.columns([1.05, 2.25], gap='large')
    with left:
        with st.container(border=True):
            _render_activity_card(activity, report, fetched_at)

    with right:
        with st.container(border=True):
            h1, h2 = st.columns([3, 1], vertical_alignment='center')
            with h1:
                st.markdown('<div class="market-card-title">Sectoral Heatmap</div>', unsafe_allow_html=True)
                st.caption('TradingView · Indonesia/IDX · size by market cap · color by 1D change · grouped by sector')
            with h2:
                st.markdown('<div class="market-eod-pill">IDX · EOD</div>', unsafe_allow_html=True)
            components.html(_tradingview_heatmap_html(), height=675, scrolling=False)
            st.caption('TradingView lists IDX stock/widget data as end-of-day (EOD). Use the widget toolbar if you want another dataset or color metric.')

    st.markdown(
        '<div class="market-footnote"><b>Data boundary:</b> Yahoo OHLCV cannot identify foreign vs domestic investors. '
        'This page therefore shows Yahoo-derived market activity instead of inventing foreign-flow numbers. '
        'A true foreign-flow module can be connected later without changing this layout.</div>',
        unsafe_allow_html=True,
    )
