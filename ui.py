from pathlib import Path
import streamlit as st

MENUS={
 'WORKSPACE':[('Dashboard','space_dashboard'),('Market Overview','public'),('Watchlist','star'),('HP Desk','edit_note')],
 'INFORMATION':[('Stock Universe','list_alt')],
 'MARKET ANALYSIS':[('Stock Charts','candlestick_chart'),('Top Movers','trending_up'),('Leaders & Laggards','leaderboard'),('Volume Activity','bar_chart'),('HP Metrics','analytics')],
 'SCREENER':[('Technical Screener','filter_alt'),('Saved Screens','bookmark')],
 'PORTFOLIO':[('Trading Journal','menu_book'),('Risk Calculator','calculate'),('Average Price','balance')],
}

def navigate(page): st.session_state.page=page

def sidebar_menu():
 st.markdown('<div class="brand"><span>HP</span> screener<span class="dot">.</span></div><div class="brand-sub">YOUR MARKET. YOUR EDGE.</div>',unsafe_allow_html=True)
 if 'page' not in st.session_state: st.session_state.page='Dashboard'
 q=st.text_input('Find a tool',placeholder='Search menu…',label_visibility='collapsed')
 for group,items in MENUS.items():
  visible=[(p,i) for p,i in items if q.lower() in p.lower()]
  if not visible: continue
  st.markdown(f'<div class="nav-label">{group}</div>',unsafe_allow_html=True)
  for page,icon in visible:
   st.button(page,key='nav_'+page,icon=f':material/{icon}:',width='stretch',type='primary' if st.session_state.page==page else 'tertiary',on_click=navigate,args=(page,))
 return st.session_state.page

def apply_style():
 css_path=Path(__file__).with_name('style.css')
 if css_path.exists():
  st.markdown('<style>'+css_path.read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)
 else:
  st.warning('style.css is missing. The app will continue with default Streamlit styling.')

def open_stock(symbol):
 st.session_state.chart_stock=symbol
 st.session_state.page='Stock Charts'
