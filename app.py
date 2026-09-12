import streamlit as st

from dashboard import render_dashboard
from idx_official import build_idx_heatmap_dataset, fetch_latest_investor_flow
from market_overview import render_market_overview
from ui import apply_style, navigate, sidebar_menu

st.set_page_config(page_title='HP Screener', page_icon='📈', layout='wide')
apply_style()


@st.cache_data(ttl=900, show_spinner=False)
def cached_idx_flow():
    return fetch_latest_investor_flow()


@st.cache_data(ttl=900, show_spinner=False)
def cached_idx_heatmap():
    return build_idx_heatmap_dataset()


with st.sidebar:
    section = sidebar_menu()

if section == 'Dashboard':
    render_dashboard(navigate=navigate)
elif section == 'Market Overview':
    render_market_overview(cached_idx_flow, cached_idx_heatmap)
