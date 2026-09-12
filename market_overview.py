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
        err = st.session_state.get('market_overview_error')
        detail = html.escape(str(err)) if err else 'IDX data is still loading or no usable Yahoo rows were returned.'
        st.markdown(
            '<div class="market-empty-small"><b>IDX breadth is not available yet.</b><br>' + detail + '</div>',
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
    """Return an eager-loading TradingView Indonesia stock heatmap embed."""
    import json

    config = {
        'exchanges': [],
        'dataSource': 'Indonesia',
        'grouping': 'sector',
        'blockSize': 'market_cap_basic',
        'blockColor': 'change',
        'locale': 'en',
        'symbolUrl': '',
        'colorTheme': 'light',
        'hasTopBar': True,
        'isDataSetEnabled': True,
        'isZoomEnabled': True,
        'hasSymbolTooltip': True,
        'isMonoSize': False,
        'width': '100%',
        'height': '100%',
    }
    cfg = json.dumps(config)
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
html,body{{margin:0;padding:0;background:#fff;font-family:Arial,sans-serif;overflow:hidden;height:100%}}
#tv-wrap{{height:650px;position:relative;background:#fff}}
.tradingview-widget-container,.tradingview-widget-container__widget{{height:100%;width:100%}}
#tv-status{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#718078;font-size:13px;background:#fff;z-index:0}}
#tv-host{{position:relative;z-index:1;height:100%;width:100%}}
#tv-fallback{{display:none;position:absolute;left:16px;right:16px;bottom:14px;padding:10px 12px;border:1px solid #e1e8e3;border-radius:9px;background:#f7faf8;color:#56655c;font-size:12px;z-index:3}}
#tv-fallback a{{color:#17784a;text-decoration:none;font-weight:600}}
</style>
</head>
<body>
<div id="tv-wrap">
  <div id="tv-status">Loading Indonesia sector heatmap...</div>
  <div id="tv-host" class="tradingview-widget-container">
    <div class="tradingview-widget-container__widget"></div>
  </div>
  <div id="tv-fallback">TradingView did not initialize automatically. <a href="https://www.tradingview.com/heatmap/stock/" target="_blank" rel="noopener">Open TradingView heatmap</a></div>
</div>
<script>
(function() {{
  const host = document.getElementById('tv-host');
  const status = document.getElementById('tv-status');
  const fallback = document.getElementById('tv-fallback');
  const config = {cfg};
  let attempts = 0;

  function inject() {{
    attempts += 1;
    host.querySelectorAll('script').forEach(el => el.remove());
    const script = document.createElement('script');
    script.type = 'text/javascript';
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js';
    script.async = true;
    script.textContent = JSON.stringify(config);
    script.onerror = function() {{
      if (attempts < 2) setTimeout(inject, 1200);
      else fallback.style.display = 'block';
    }};
    host.appendChild(script);
  }}

  function check() {{
    const frame = host.querySelector('iframe');
    if (frame) {{
      status.style.display = 'none';
      fallback.style.display = 'none';
      return;
    }}
    if (attempts < 2) {{
      inject();
      setTimeout(check, 6500);
    }} else {{
      status.textContent = 'Waiting for TradingView...';
      fallback.style.display = 'block';
    }}
  }}

  inject();
  setTimeout(check, 6500);
}})();
</script>
</body>
</html>"""

def render_market_overview(cached_yahoo, cached_scan, quality_universe) -> None:
    st.markdown(
        '<div class="market-title">Market Overview</div>'
        '<div class="market-subtitle">IDX breadth from Yahoo Finance with an embedded TradingView sector heatmap.</div>',
        unsafe_allow_html=True,
    )

    # Render TradingView first. This is intentionally before any blocking Yahoo
    # Quality-200 request so the browser starts the heatmap immediately.
    left, right = st.columns([1.05, 2.25], gap='large')
    with right:
        with st.container(border=True):
            h1, h2 = st.columns([3, 1], vertical_alignment='center')
            with h1:
                st.markdown('<div class="market-card-title">Sectoral Heatmap</div>', unsafe_allow_html=True)
                st.caption('TradingView · Indonesia · size by market cap · color by 1D change · grouped by sector')
            with h2:
                st.markdown('<div class="market-eod-pill">IDX · EOD</div>', unsafe_allow_html=True)
            components.html(_tradingview_heatmap_html(), height=675, scrolling=False)
            st.caption('Heatmap starts independently before Yahoo Quality-200. TradingView lists IDX widget data as EOD.')

    bundle = st.session_state.get('market_overview_bundle')
    if bundle is None:
        candidate = st.session_state.get('yahoo_bundle')
        if candidate is not None:
            try:
                cp, cr, ct = candidate
                if cr is not None and len(cr) >= 100 and cp is not None and not cp.empty:
                    bundle = candidate
            except Exception:
                pass

    requested_refresh = st.session_state.pop('market_overview_refresh_requested', False)
    if requested_refresh:
        st.session_state.pop('market_overview_bundle', None)
        st.session_state.pop('market_overview_error', None)
        try:
            cached_yahoo.clear()
        except Exception:
            pass
        bundle = None

    if bundle is None and 'market_overview_error' not in st.session_state:
        try:
            symbols = quality_universe()
            with left:
                with st.spinner(f'Loading IDX market automatically · {len(symbols)} Quality 200 stocks from Yahoo...'):
                    bundle = cached_yahoo(symbols, '1y', False, 60)
            st.session_state['market_overview_bundle'] = bundle
        except Exception as exc:
            st.session_state['market_overview_error'] = str(exc)

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
            st.session_state['market_overview_error'] = str(exc)

    with left:
        with st.container(border=True):
            _render_activity_card(activity, report, fetched_at)
        if st.session_state.get('market_overview_error') and activity.empty:
            if st.button('Retry IDX data', icon=':material/refresh:', width='stretch', key='retry_market_overview_200'):
                st.session_state.pop('market_overview_error', None)
                st.session_state.pop('market_overview_bundle', None)
                try:
                    cached_yahoo.clear()
                except Exception:
                    pass
                st.rerun()

    st.markdown(
        '<div class="market-footnote"><b>Data boundary:</b> Yahoo OHLCV cannot identify foreign vs domestic investors. '
        'Yahoo supplies the breadth/activity panel; TradingView supplies the independent sector heatmap.</div>',
        unsafe_allow_html=True,
    )

