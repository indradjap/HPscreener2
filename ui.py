from pathlib import Path
import streamlit as st

MENUS = {
    'WORKSPACE': [
        ('Dashboard', 'space_dashboard'),
        ('Market Overview', 'public'),
        ('Watchlist', 'star'),
        ('HP Desk', 'edit_note'),
    ],
    'INFORMATION': [('Stock Universe', 'list_alt')],
    'MARKET ANALYSIS': [
        ('Stock Charts', 'candlestick_chart'),
        ('Top Movers', 'trending_up'),
        ('Leaders & Laggards', 'leaderboard'),
        ('Volume Activity', 'bar_chart'),
        ('HP Metrics', 'analytics'),
    ],
    'SCREENER': [
        ('Technical Screener', 'filter_alt'),
        ('Saved Screens', 'bookmark'),
    ],
    'PORTFOLIO': [
        ('Trading Journal', 'menu_book'),
        ('Risk Calculator', 'calculate'),
        ('Average Price', 'balance'),
    ],
}

ALL_PAGES = tuple(page for items in MENUS.values() for page, _ in items)
DATA_PAGES = {
    'Dashboard', 'Market Overview', 'Watchlist', 'Stock Charts', 'Top Movers',
    'Leaders & Laggards', 'Volume Activity', 'HP Metrics', 'Technical Screener',
}


def navigate(page: str) -> None:
    """Set a valid destination. The caller decides whether a rerun is needed."""
    if page not in ALL_PAGES:
        page = 'Dashboard'
    st.session_state['page'] = page


def sidebar_menu() -> str:
    """Grouped deterministic sidebar router.

    Navigation uses explicit button return values + st.rerun instead of widget callbacks.
    That keeps the selected route stable even when the main page has validation errors,
    missing market data, or other widgets that rerun the script.
    """
    st.markdown(
        '<div class="brand"><span>HP</span> screener<span class="dot">.</span></div>'
        '<div class="brand-sub">YOUR MARKET. YOUR EDGE.</div>',
        unsafe_allow_html=True,
    )
    if st.session_state.get('page') not in ALL_PAGES:
        st.session_state['page'] = 'Dashboard'

    q = st.text_input(
        'Find a tool', placeholder='Search menu…', label_visibility='collapsed', key='menu_search'
    ).strip().lower()

    for group, items in MENUS.items():
        visible = [(page, icon) for page, icon in items if not q or q in page.lower()]
        if not visible:
            continue
        st.markdown(f'<div class="nav-label">{group}</div>', unsafe_allow_html=True)
        for page, icon in visible:
            active = st.session_state['page'] == page
            if st.button(
                page,
                key=f'nav_{page}',
                icon=f':material/{icon}:',
                width='stretch',
                type='primary' if active else 'tertiary',
            ):
                if not active:
                    st.session_state['page'] = page
                    st.rerun()

    return st.session_state['page']


def apply_style() -> None:
    css_path = Path(__file__).with_name('style.css')
    if css_path.exists():
        st.markdown('<style>' + css_path.read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)
    else:
        st.warning('style.css is missing. The app will continue with default Streamlit styling.')


def open_stock(symbol: str) -> None:
    st.session_state['chart_stock'] = symbol
    st.session_state['page'] = 'Stock Charts'


def open_saved_screen(name: str) -> None:
    st.session_state['requested_preset'] = 'Saved: ' + name
    st.session_state['page'] = 'Technical Screener'
