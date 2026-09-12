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
    """Two stacked columns (Foreign/Domestic) with buy on top and sell at the base."""
    f_buy, f_sell = float(metric["foreign_buy"]), float(metric["foreign_sell"])
    d_buy, d_sell = float(metric["domestic_buy"]), float(metric["domestic_sell"])
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=["Foreign", "Domestic"],
            y=[f_sell, d_sell],
            name="Sell",
            marker_color=["#4b9a92", "#463cc6"],
            hovertemplate="%{x} Sell<br>%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=["Foreign", "Domestic"],
            y=[f_buy, d_buy],
            name="Buy",
            marker_color=["#68c6ba", "#7a81e8"],
            hovertemplate="%{x} Buy<br>%{y:,.0f}<extra></extra>",
        )
    )

    ymax = max(f_buy + f_sell, d_buy + d_sell) if max(f_buy + f_sell, d_buy + d_sell) > 0 else 1.0
    pad = ymax * 0.16
    fig.update_layout(
        barmode="stack",
        height=500,
        margin=dict(l=8, r=8, t=18, b=28),
        bargap=.52,
        template="plotly_white",
        showlegend=False,
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=12, color="#1e2521"),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, tickfont=dict(size=12), fixedrange=True)
    fig.update_yaxes(showticklabels=False, gridcolor="#edf0ee", griddash="dot", zeroline=False, title=None, range=[0, ymax + pad], fixedrange=True)

    # Labels stay inside each segment, with automatic high-contrast font choices:
    # light bars -> dark text, dark bars -> light text.
    ann = [
        dict(
            x="Foreign", y=f_sell + f_buy * 0.52,
            text=f"<b>F Buy</b><br><b>{_flow_format(f_buy, mode)}</b>",
            showarrow=False, xanchor="center", yanchor="middle",
            font=dict(size=12, color="#173a35"),
        ),
        dict(
            x="Foreign", y=max(f_sell * 0.50, ymax * 0.025),
            text=f"<b>F Sell</b><br><b>{_flow_format(f_sell, mode)}</b>",
            showarrow=False, xanchor="center", yanchor="middle",
            font=dict(size=12, color="#f4fffc"),
        ),
        dict(
            x="Domestic", y=d_sell + d_buy * 0.52,
            text=f"<b>D Buy</b><br><b>{_flow_format(d_buy, mode)}</b>",
            showarrow=False, xanchor="center", yanchor="middle",
            font=dict(size=12, color="#25205f"),
        ),
        dict(
            x="Domestic", y=max(d_sell * 0.50, ymax * 0.025),
            text=f"<b>D Sell</b><br><b>{_flow_format(d_sell, mode)}</b>",
            showarrow=False, xanchor="center", yanchor="middle",
            font=dict(size=12, color="#f7f6ff"),
        ),
    ]
    fig.update_layout(annotations=ann)
    return fig


def _render_flow_card(flow: dict | None, error: str | None, clear_flow_cache) -> None:
    top1, top2, top3 = st.columns([3.5, 1.15, 1.3], vertical_alignment="center")
    with top1:
        st.markdown('<div class="market-card-title">Foreign vs Domestic<br>Net Flow</div>', unsafe_allow_html=True)
    with top2:
        st.selectbox('Investor filter', ['All'], key='idx_flow_filter', label_visibility='collapsed')
    with top3:
        st.markdown('<div class="open-detail-link">Open detail <span>→</span></div>', unsafe_allow_html=True)

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
            # Do not cap depth here. Tree structure is IDXROOT -> Sector/SubSector -> Stock.
            # A depth cap here would hide stock leaves and show only sector containers.
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
    top1, top2 = st.columns([5.1, .4], vertical_alignment='center')
    with top1:
        st.markdown('<div class="market-card-title heat-title">Sectoral Heatmap</div>', unsafe_allow_html=True)
    with top2:
        if st.button('', icon=':material/refresh:', help='Refresh', key='refresh_idx_heatmap', width='stretch'):
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



def _mover_metric_label(mode: str) -> str:
    return {
        'Top Gainer': '% Chg',
        'Top Loser': '% Chg',
        'Top Value': 'Value',
        'Top Volume': 'Volume',
        'Top Frequency': 'Frequency',
    }[mode]


def _mover_metric_value(row: pd.Series, mode: str) -> tuple[str, str]:
    if mode in ('Top Gainer', 'Top Loser'):
        v = float(row.get('ChangePct', 0.0) or 0.0)
        cls = 'positive' if v > 0 else ('negative' if v < 0 else '')
        return f'{v:+.2f}%', cls
    if mode == 'Top Value':
        return _fmt_large(float(row.get('TradedValue', 0.0) or 0.0), currency=True), ''
    if mode == 'Top Volume':
        return _fmt_large(float(row.get('Volume', 0.0) or 0.0)), ''
    return f"{float(row.get('Frequency', 0.0) or 0.0):,.0f}", ''


def _render_top_movers(market: pd.DataFrame | None, error: str | None = None) -> None:
    st.markdown('<div class="movers-title">Top Movers</div>', unsafe_allow_html=True)
    if market is None or market.empty:
        detail = html.escape(error or 'Waiting for latest IDX market summary.')
        st.markdown(
            '<div class="market-empty-small"><b>Top Movers unavailable.</b><br>' + detail + '</div>',
            unsafe_allow_html=True,
        )
        return

    mode = st.segmented_control(
        'Mover ranking',
        ['Top Gainer', 'Top Loser', 'Top Value', 'Top Volume', 'Top Frequency'],
        default='Top Gainer', key='top_movers_mode', label_visibility='collapsed'
    ) or 'Top Gainer'

    d = market.copy()
    numeric_cols = ['Close','ChangePct','TradedValue','Volume','Frequency']
    for c in numeric_cols:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d[d.Close.fillna(0) > 0].copy()

    if mode == 'Top Gainer':
        d = d.sort_values(['ChangePct','TradedValue'], ascending=[False, False])
    elif mode == 'Top Loser':
        d = d.sort_values(['ChangePct','TradedValue'], ascending=[True, False])
    elif mode == 'Top Value':
        d = d.sort_values(['TradedValue','ChangePct'], ascending=[False, False])
    elif mode == 'Top Volume':
        d = d.sort_values(['Volume','ChangePct'], ascending=[False, False])
    else:
        d = d.sort_values(['Frequency','ChangePct'], ascending=[False, False])
    d = d.head(5)

    metric_label = _mover_metric_label(mode)
    rows=[]
    for _, row in d.iterrows():
        symbol = html.escape(str(row.get('Symbol','')))
        close = float(row.get('Close',0.0) or 0.0)
        value, cls = _mover_metric_value(row, mode)
        change = float(row.get('ChangePct',0.0) or 0.0)
        secondary = '' if mode in ('Top Gainer','Top Loser') else f'<span class="mover-subchg {"positive" if change>0 else "negative" if change<0 else ""}">{change:+.2f}%</span>'
        rows.append(
            '<div class="mover-row">'
            f'<div class="mover-symbol"><span>{symbol}</span></div>'
            f'<div class="mover-close">{close:,.0f}</div>'
            f'<div class="mover-metric {cls}">{html.escape(value)}{secondary}</div>'
            '</div>'
        )
    st.markdown(
        '<div class="mover-table">'
        '<div class="mover-header"><div>Ticker</div><div>Close</div>'
        f'<div>{html.escape(metric_label)}</div></div>'
        + ''.join(rows) + '</div>', unsafe_allow_html=True
    )

    date_val = pd.to_datetime(market.get('Date'), errors='coerce').max() if 'Date' in market else pd.NaT
    date_label = date_val.date().isoformat() if pd.notna(date_val) else 'latest'
    st.markdown(f'<div class="mover-source">Official IDX · trading date {html.escape(date_label)}</div>', unsafe_allow_html=True)


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

    with st.container(border=True):
        _render_top_movers(heatmap, heatmap_error)

