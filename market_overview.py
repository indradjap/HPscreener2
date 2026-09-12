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
        margin=dict(l=5, r=5, t=38, b=15),
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


def _heatmap_figure(d: pd.DataFrame) -> go.Figure:
    d = d.copy()
    d["Sector"] = d["Sector"].fillna("Other IDX").astype(str)
    d["Company"] = d["Company"].fillna(d["Symbol"]).astype(str)
    d = d[d.MarketCap > 0].copy()

    ids = ["IDX"]
    labels = ["IDX"]
    parents = [""]
    values = [float(d.MarketCap.sum())]
    colors = [0.0]
    texts = [f"{len(d)} stocks"]
    custom = [["IDX", "", 0.0, 0.0, 0.0]]

    for sector, g in d.groupby("Sector", sort=True):
        sec_id = "sector:" + sector
        sec_value = float(g.MarketCap.sum())
        weighted = float((g.ColorChange * g.MarketCap).sum() / sec_value) if sec_value else 0.0
        ids.append(sec_id)
        labels.append(sector)
        parents.append("IDX")
        values.append(sec_value)
        colors.append(weighted)
        texts.append(f"{len(g)} stocks")
        custom.append(["Sector", sector, weighted, 0.0, sec_value])
        for _, r in g.iterrows():
            pct = float(r.ChangePct)
            ids.append("stock:" + str(r.Symbol))
            labels.append(str(r.Symbol))
            parents.append(sec_id)
            values.append(float(r.MarketCap))
            colors.append(float(r.ColorChange))
            texts.append(f"{pct:+.2f}%")
            custom.append([str(r.Company), sector, pct, float(r.Close), float(r.MarketCap)])

    colorscale = [
        [0.00, "#8f1d1d"],
        [0.22, "#d93f43"],
        [0.42, "#ed8a8b"],
        [0.50, "#c8cdca"],
        [0.58, "#7cc796"],
        [0.78, "#3f9e5d"],
        [1.00, "#1f6336"],
    ]
    fig = go.Figure(
        go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            marker=dict(
                colors=colors,
                colorscale=colorscale,
                cmin=-7,
                cmid=0,
                cmax=7,
                line=dict(color="white", width=1.1),
                colorbar=dict(title="1D %", thickness=12, len=.65, x=1.01),
            ),
            text=texts,
            texttemplate="<b>%{label}</b><br>%{text}",
            customdata=custom,
            hovertemplate=(
                "<b>%{label}</b><br>%{customdata[0]}<br>"
                "Sector: %{customdata[1]}<br>Change 1D: %{customdata[2]:+.2f}%<br>"
                "Close: %{customdata[3]:,.0f}<br>Market cap: Rp%{customdata[4]:,.0f}<extra></extra>"
            ),
            tiling=dict(packing="squarify", pad=1),
            pathbar=dict(visible=True, thickness=22),
            root_color="#f4f6f5",
            maxdepth=2,
        )
    )
    fig.update_layout(
        height=680,
        margin=dict(l=0, r=15, t=5, b=0),
        paper_bgcolor="white",
        font=dict(family="Arial, sans-serif", size=12, color="#17281f"),
    )
    return fig


def _render_heatmap_card(heatmap: pd.DataFrame | None, note: str | None, error: str | None, clear_market_cache) -> None:
    h1, h2 = st.columns([3.3, .7], vertical_alignment="center")
    with h1:
        st.markdown('<div class="market-card-title">IDX Sectoral Heatmap</div>', unsafe_allow_html=True)
        st.caption('All available IDX stocks · size by market cap · color by 1D change · grouped by IDX sector')
    with h2:
        if st.button("Refresh", icon=":material/refresh:", key="refresh_idx_heatmap", width="stretch"):
            clear_market_cache()
            st.rerun()

    if heatmap is None or heatmap.empty:
        detail = html.escape(error or "Waiting for IDX stock summary.")
        st.markdown(
            '<div class="market-empty-large"><b>IDX heatmap unavailable.</b><br>' + detail + '</div>',
            unsafe_allow_html=True,
        )
        return

    a, b, c = st.columns(3)
    a.markdown('<div class="heat-control"><span>UNIVERSE</span><b>All IDX stocks</b></div>', unsafe_allow_html=True)
    b.markdown('<div class="heat-control"><span>SIZE BY</span><b>Market cap</b></div>', unsafe_allow_html=True)
    c.markdown('<div class="heat-control"><span>COLOR BY</span><b>Change 1D %</b></div>', unsafe_allow_html=True)
    st.plotly_chart(_heatmap_figure(heatmap), width="stretch", config={"displayModeBar": False})
    st.caption((note or "Official IDX") + f" · {heatmap.Symbol.nunique()} stocks displayed")


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
