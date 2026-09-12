import streamlit as st

from dashboard import render_dashboard
from market import scan
from market_overview import render_market_overview
from ui import apply_style, navigate, sidebar_menu
from yahoo import fetch_universe, quality_universe

st.set_page_config(page_title='HP Screener', page_icon='📈', layout='wide')
apply_style()


@st.cache_data(ttl=1800, show_spinner=False)
def cached_yahoo(symbols, period='1y', include_today=False, chunk_size=60):
    return fetch_universe(symbols, period, include_today, chunk_size)


@st.cache_data(show_spinner=False)
def cached_scan(prices):
    return scan(prices)


with st.sidebar:
    section = sidebar_menu()

if section == 'Dashboard':
    render_dashboard(navigate=navigate)
elif section == 'Market Overview':
    render_market_overview(cached_yahoo, cached_scan, quality_universe)
