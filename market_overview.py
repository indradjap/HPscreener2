from __future__ import annotations

import html
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _fmt_large(value: float, *, currency: bool = False, decimals: int = 2) -> str:
    value = float(value or 0)
    prefix = "Rp" if currency else ""
    av = abs(value)
    if av >= 1e12:
        return f"{prefix}{value/1e12:,.{decimals}f}T"
    if av >= 1e9:
        return f"{prefix}{value/1e9:,.{decimals}f}B"
    if av >= 1e6:
        return f"{prefix}{value/1e6:,.{decimals}f}M"
    if av >= 1e3:
        return f"{prefix}{value/1e3:,.1f}K"
    return f"{prefix}{value:,.0f}"


def _flow_format(value: float, mode: str) -> str:
    if mode == "VALUE":
        return _fmt_large(value, currency=False)
    if mode == "VOLUME":
        return _fmt_large(value)
    return f"{float(value):,.0f}"


def _flow_figure(metric: dict[str, float], mode: str) -> go.Figure:
    """Two columns (Foreign/Domestic), with Sell base + Buy overlay feel."""
    f_buy, f_sell = metric["foreign_buy"], metric["foreign_sell"]
    d_buy, d_sell = metric["domestic_buy"], metric["domestic_sell"]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=["Foreign", "Domestic"],
            y=[f_sell, d_sell],
            name="Sell",
            marker_color=["#3f968c", "#453cc9"],
            text=[f"F Sell<br><b>{_flow_format(f_sell, mode)}</b>", f"D Sell<br><b>{_flow_format(d_sell, mode)}</b>"],
            textposition="inside",
            insidetextanchor="start",
            hovertemplate="%{x} Sell<br>%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=["Foreign", "Domestic"],
            y=[f_buy, d_buy],
            name="Buy",
            marker_color=["#5bc8bc", "#7c83e8"],
            text=[f"F Buy<br><b>{_flow_format(f_buy, mode)}</b>", f"D Buy<br><b>{_flow_format(d_buy, mode)}</b>"],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x} Buy<br>%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="overlay",
        height=420,
        margin=dict(l=5, r=5, t=52, b=15),
        bargap=.48,
        template="plotly_white",
        showlegend=False,
        paper_bgcolor="white",
        plot_bgcolor="white",
    )
    fig.update_xaxes(showgrid=False, zeroline=False, tickfont=dict(size=12))
    fig.update_yaxes(showticklabels=False, gridcolor="#edf0ee", zeroline=False, title=None)
    return fig


def _render_flow_card(flow: dict | None, error: str | None, clear_flow_cache) -> None:
    h1, h2 = st.columns([3.1, .9], vertical_alignment="center")
    with h1:
        st.markdown('<div class="market-card-title">Foreign vs Domestic<br>Net Flow</div>', unsafe_allow_html=True)
    with h2:
        if st.button("Refresh", icon=":material/refresh:", key="refresh_idx_flow", width="stretch"):
            clear_flow_cache()
            st.rerun()

    mode = st.segmented_control(
        "Flow metric", ["VALUE", "VOLUME", "FREQUENCY"], default="VALUE",
        key="idx_flow_mode", label_visibility="collapsed"
    ) or "VALUE"

    if not flow:
        detail = html.escape(error or "Waiting for IDX investor data.")
        st.markdown(
            '<div class="market-empty-small"><b>IDX investor flow unavailable.</b><br>' + detail + '</div>',
            unsafe_allow_html=True,
        )
        return

    key = {"VALUE": "value", "VOLUME": "volume", "FREQUENCY": "frequency"}[mode]
    m = flow["metrics"][key]
    fnet = m["foreign_net"]
    net_label = "Net Foreign Buy" if fnet >= 0 else "Net Foreign Sell"
    net_class = "positive" if fnet >= 0 else "negative"
    st.markdown(
        '<div class="flow-headline">'
        f'<span>F Buy <b class="positive">{_flow_format(m["foreign_buy"], mode)}</b></span>'
        f'<span>F Sell <b class="negative">{_flow_format(m["foreign_sell"], mode)}</b></span>'
        f'<span class="flow-net">{net_label} <b class="{net_class}">{_flow_format(fnet, mode)}</b></span>'
        '</div>',
        unsafe_allow_html=True,
    )
    unit = "VALUE (IDR)" if mode == "VALUE" else ("VOLUME (SHARES)" if mode == "VOLUME" else "FREQUENCY (X)")
    st.markdown(f'<div class="flow-unit">{unit}</div>', unsafe_allow_html=True)
    st.plotly_chart(_flow_figure(m, mode), width="stretch", config={"displayModeBar": False})
    st.caption(f'IDX Digital Statistics · trading date {flow["date"]}')


def _mix_hex(a: str, b: str, t: float) -> str:
    """Linear RGB interpolation used for the TradingView-like heat colors."""
    t = max(0.0, min(1.0, float(t)))
    av = tuple(int(a[i:i+2], 16) for i in (1, 3, 5))
    bv = tuple(int(b[i:i+2], 16) for i in (1, 3, 5))
    rgb = tuple(round(x + (y - x) * t) for x, y in zip(av, bv))
    return '#%02x%02x%02x' % rgb


def _heat_color(value: float) -> str:
    """Map daily % change to a restrained red/neutral/green heat scale."""
    v = max(-7.0, min(7.0, float(value or 0.0)))
    stops = [
        (-7.0, '#8f2525'),
        (-5.5, '#a72b2b'),
        (-3.5, '#df474a'),
        (-1.5, '#e98284'),
        (0.0, '#c9cdcb'),
        (1.5, '#73bd8c'),
        (3.5, '#45a767'),
        (7.0, '#255f39'),
    ]
    for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
        if x0 <= v <= x1:
            return _mix_hex(c0, c1, (v - x0) / (x1 - x0))
    return stops[-1][1]


def _load_quality200() -> set[str]:
    from pathlib import Path
    try:
        d = pd.read_csv(Path(__file__).with_name('idx_quality_200.csv'))
        return set(d['Ticker'].astype(str).str.upper().str.strip())
    except Exception:
        return set()


def _heatmap_figure(d: pd.DataFrame, *, size_col: str, group_col: str) -> go.Figure:
    d = d.copy()
    d[group_col] = d[group_col].fillna('Other IDX').replace('', 'Other IDX').astype(str)
    d['Company'] = d['Company'].fillna(d['Symbol']).astype(str)
    d = d[pd.to_numeric(d[size_col], errors='coerce').fillna(0) > 0].copy()
    d[size_col] = pd.to_numeric(d[size_col], errors='coerce').fillna(0.0)

    # Root + group parent nodes + stock leaf nodes. Parent nodes are deliberately
    # white so their header band reads more like the supplied TradingView reference.
    ids = ['IDXROOT']
    labels = ['']
    parents = ['']
    values = [float(d[size_col].sum())]
    colors = ['#ffffff']
    display = ['']
    custom = [['', '', 0.0, 0.0, 0.0, 0.0]]

    for group, g in d.groupby(group_col, sort=False):
        gid = 'group:' + str(group)
        gvalue = float(g[size_col].sum())
        ids.append(gid)
        labels.append(str(group))
        parents.append('IDXROOT')
        values.append(gvalue)
        colors.append('#ffffff')
        display.append(f'<span style="color:#161616"><b>{html.escape(str(group))} ›</b></span>')
        custom.append(['', str(group), 0.0, 0.0, gvalue, 0.0])

        # Largest stocks first creates a more stable visual hierarchy.
        for _, r in g.sort_values(size_col, ascending=False).iterrows():
            pct = float(r.ChangePct)
            sym = str(r.Symbol)
            ids.append('stock:' + sym)
            labels.append(sym)
            parents.append(gid)
            values.append(float(r[size_col]))
            colors.append(_heat_color(pct))
            # Ticker + % only; company and metrics stay in hover to keep tiles clean.
            display.append(f'<span style="color:#ffffff"><b>{html.escape(sym)}</b><br>{pct:+.2f}%</span>')
            custom.append([
                str(r.Company), str(group), pct, float(r.Close),
                float(r.MarketCap), float(r.get('TradedValue', 0.0))
            ])

    fig = go.Figure(
        go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues='total',
            marker=dict(colors=colors, line=dict(color='#ffffff', width=1.15)),
            text=display,
            texttemplate='%{text}',
            textfont=dict(size=14, color='#ffffff'),
            customdata=custom,
            hovertemplate=(
                '<b>%{label}</b><br>%{customdata[0]}<br>'
                f'{html.escape(group_col)}: %{{customdata[1]}}<br>'
                'Change 1D: %{customdata[2]:+.2f}%<br>'
                'Close: %{customdata[3]:,.0f}<br>'
                'Market cap: Rp%{customdata[4]:,.0f}<br>'
                'Traded value: Rp%{customdata[5]:,.0f}<extra></extra>'
            ),
            tiling=dict(packing='squarify', pad=1.4),
            pathbar=dict(visible=False),
            root_color='#ffffff',
            maxdepth=2,
            sort=False,
        )
    )
    fig.update_layout(
        height=655,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor='white',
        plot_bgcolor='white',
        font=dict(family='Arial, sans-serif', size=13, color='#111111'),
        uniformtext=dict(minsize=8, mode='hide'),
    )
    return fig


def _legend_html() -> str:
    blocks = [
        ('#8f2525', '−5.5%'), ('#df474a', '−3.5%'), ('#e98284', '−1.5%'),
        ('#c9cdcb', '0%'), ('#73bd8c', '1.5%'), ('#45a767', '3.5%'), ('#255f39', '5.5%')
    ]
    labels = ''.join(f'<div class="heat-legend-label">{t}</div>' for _, t in blocks)
    bars = ''.join(f'<div class="heat-legend-block" style="background:{c}"></div>' for c, _ in blocks)
    return f'<div class="heat-legend"><div class="heat-legend-labels">{labels}</div><div class="heat-legend-bars">{bars}</div></div>'


def _render_heatmap_card(heatmap: pd.DataFrame | None, note: str | None, error: str | None, clear_market_cache) -> None:
    top1, top2 = st.columns([4.3, .7], vertical_alignment='center')
    with top1:
        st.markdown('<div class="market-card-title heat-title">Sectoral Heatmap</div>', unsafe_allow_html=True)
    with top2:
        if st.button('Refresh', icon=':material/refresh:', key='refresh_idx_heatmap', width='stretch'):
            clear_market_cache()
            st.rerun()

    if heatmap is None or heatmap.empty:
        detail = html.escape(error or 'Waiting for IDX stock summary.')
        st.markdown(
            '<div class="market-empty-large"><b>IDX heatmap unavailable.</b><br>' + detail + '</div>',
            unsafe_allow_html=True,
        )
        return

    # TradingView-like toolbar, but every control is native and functional.
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([2.05, 1.35, 1.45, 1.25], gap='small')
        with c1:
            universe = st.selectbox(
                'Universe', ['All Indonesian companies', 'Quality 200'],
                key='heat_universe', label_visibility='collapsed'
            )
        with c2:
            size_by = st.selectbox(
                'Size by', ['Market cap', 'Traded value'],
                key='heat_size_by', label_visibility='collapsed'
            )
        with c3:
            color_by = st.selectbox(
                'Color by', ['Change 1D, %'],
                key='heat_color_by', label_visibility='collapsed'
            )
        with c4:
            group_by = st.selectbox(
                'Group by', ['Sector', 'SubSector'],
                key='heat_group_by', label_visibility='collapsed'
            )

    d = heatmap.copy()
    if universe == 'Quality 200':
        q = _load_quality200()
        if q:
            d = d[d.Symbol.isin(q)].copy()
    size_col = 'MarketCap' if size_by == 'Market cap' else 'TradedValue'
    group_col = 'Sector' if group_by == 'Sector' else 'SubSector'
    if group_col not in d.columns:
        group_col = 'Sector'
    if size_col not in d.columns or pd.to_numeric(d[size_col], errors='coerce').fillna(0).sum() <= 0:
        size_col = 'MarketCap'

    st.plotly_chart(
        _heatmap_figure(d, size_col=size_col, group_col=group_col),
        width='stretch',
        config={'displayModeBar': False, 'responsive': True},
        key='idx_sector_heatmap_plot',
    )
    st.markdown(_legend_html(), unsafe_allow_html=True)
    source = note or 'Official IDX'
    st.markdown(
        f'<div class="heat-source"><b>{html.escape(universe)}</b> · {d.Symbol.nunique()} stocks · '
        f'{html.escape(source)}</div>', unsafe_allow_html=True
    )

def render_market_overview(cached_idx_flow, cached_idx_heatmap) -> None:
    st.markdown(
        '<div class="market-title">Market Overview</div>'
        '<div class="market-subtitle">Official IDX investor flow and whole-market sector heatmap.</div>',
        unsafe_allow_html=True,
    )

    flow = None
    flow_error = None
    try:
        with st.spinner("Loading IDX foreign/domestic flow…"):
            flow = cached_idx_flow()
    except Exception as exc:
        flow_error = str(exc)

    heatmap = None
    heatmap_note = None
    heatmap_error = None
    try:
        with st.spinner("Loading latest IDX market and sector map…"):
            heatmap, heatmap_note = cached_idx_heatmap()
    except Exception as exc:
        heatmap_error = str(exc)

    def clear_flow():
        try:
            cached_idx_flow.clear()
        except Exception:
            pass

    def clear_market():
        try:
            cached_idx_heatmap.clear()
        except Exception:
            pass

    left, right = st.columns([1.02, 2.25], gap="large")
    with left:
        with st.container(border=True):
            _render_flow_card(flow, flow_error, clear_flow)
    with right:
        with st.container(border=True):
            _render_heatmap_card(heatmap, heatmap_note, heatmap_error, clear_market)

    st.markdown(
        '<div class="market-footnote"><b>Source boundary:</b> Market Overview now uses IDX data for investor-flow '
        'and IDX market/sector metadata. TradingView has been removed from this page, so it cannot fall back to '
        'S&amp;P 500. Dashboard remains Yahoo-based for single-stock charting.</div>',
        unsafe_allow_html=True,
    )
