from pathlib import Path
import streamlit as st

MENUS = (
    ('Dashboard', 'space_dashboard'),
    ('Market Overview', 'public'),
)


def navigate(page: str) -> None:
    st.session_state['page'] = page


def sidebar_menu() -> str:
    if st.session_state.get('page') not in {p for p, _ in MENUS}:
        st.session_state['page'] = 'Dashboard'

    st.markdown(
        '<div class="brand"><span>HP</span> screener<span class="dot">.</span></div>'
        '<div class="brand-sub">TWO-MENU FUNCTION TEST</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="nav-label">WORKSPACE</div>', unsafe_allow_html=True)

    for page, icon in MENUS:
        active = st.session_state['page'] == page
        if st.button(
            page,
            key=f'nav_{page}',
            icon=f':material/{icon}:',
            width='stretch',
            type='primary' if active else 'tertiary',
        ):
            st.session_state['page'] = page
            st.rerun()

    st.markdown(
        '<div class="test-note">This build intentionally contains only Dashboard and Market Overview.</div>',
        unsafe_allow_html=True,
    )
    return st.session_state['page']


def apply_style() -> None:
    css_path = Path(__file__).with_name('style.css')
    if css_path.exists():
        st.markdown('<style>' + css_path.read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)
