import hashlib
import json
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from market import demo, parse_csv, indicators, scan, position_size, SYMBOLS
from yahoo import normalize_symbols, fetch_one, fetch_universe

st.set_page_config(page_title='HP Screener', page_icon='📈', layout='wide')
st.markdown('''<style>.block-container{padding-top:2rem;max-width:1600px} [data-testid="stSidebar"]{border-right:1px solid #e2e9e4} h1{letter-spacing:-1.5px} [data-testid="stMetric"]{background:#f3f6f4;border-radius:12px;padding:16px} .hp-logo{font-size:28px;font-weight:800;color:#143a25}</style>''',unsafe_allow_html=True)
for key,value in dict(watchlist=['BBCA','ISAT'],notes={},journal=[],saved_rules={}).items():
    if key not in st.session_state: st.session_state[key]=value

@st.cache_data
def demo_prices(): return demo()
@st.cache_data
def cached_scan(d): return scan(d)

@st.cache_data(ttl=900, show_spinner=False)
def cached_yahoo(symbol, period, include_today):
    return fetch_one(symbol, period, include_today)

with st.sidebar:
    st.markdown('<div class="hp-logo">HP Screener<span style="color:#22c55e">.</span></div>',unsafe_allow_html=True)
    st.caption('IDX RESEARCH WORKSPACE')
    st.divider()
    section=st.radio('Workspace',['Dashboard','Market Overview','Stock Charts','Screener','Watchlist','Research Notes','Trading Journal','Calculators'])
    st.divider()
    source=st.selectbox('Price input',['Yahoo Finance','CSV upload','Demo'])
    if source=='Yahoo Finance':
        tickers=st.text_area('IDX tickers',value=', '.join(SYMBOLS),help='Separate with commas or spaces. BBCA and BBCA.JK both work. Up to 250 tickers.')
        history=st.selectbox('Price history',['1y','2y','5y'],index=1)
        include_today=st.checkbox('Include today’s daily bar',value=False,help='Today can be incomplete. By default all bars dated today in Jakarta are excluded, even after market close.')
        st.caption('Yahoo daily data · adjusted OHLC · 15-minute cache · may be delayed')
        refresh=st.checkbox('Bypass cached prices on next fetch',value=False)
        if st.button('Fetch & scan',type='primary'):
            try:
                requested=normalize_symbols(tickers)
                if refresh: cached_yahoo.clear()
                progress=st.progress(0.,text='Downloading IDX prices…')
                bundle=fetch_universe(requested,history,include_today,loader=cached_yahoo,progress=progress.progress)
                st.session_state.yahoo_bundle=bundle
                st.session_state.yahoo_request=(requested,history,include_today)
                progress.empty()
            except ValueError as exc: st.error(str(exc))
    with st.expander('Import price CSV'):
        st.caption('Daily OHLCV, at least 60 rows per ticker. Select CSV upload above to use this universe for this session.')
        upload=st.file_uploader('Prices',type=['csv'],key='prices_upload')
        st.download_button('Download example CSV',demo_prices().to_csv(index=False).encode(),'hp-demo-prices.csv','text/csv')
    with st.expander('Workspace backup'):
        st.caption('Watchlist, notes, journal and rules are session-only. Download a backup before closing. Imported prices are not included.')
        payload={k:st.session_state[k] for k in ('watchlist','notes','journal','saved_rules')}
        st.download_button('Download workspace',json.dumps(payload,indent=2).encode(),'hp-workspace.json','application/json')
        restore=st.file_uploader('Restore workspace',type=['json'])
        if st.button('Restore backup',disabled=restore is None):
            try:
                x=json.loads(restore.getvalue())
                assert isinstance(x.get('watchlist'),list) and all(isinstance(v,str) for v in x['watchlist'])
                assert isinstance(x.get('notes'),dict) and all(isinstance(k,str) and isinstance(v,str) for k,v in x['notes'].items())
                assert isinstance(x.get('journal'),list)
                for t in x['journal']:
                    assert set(t)=={'Date','Symbol','Entry','Exit','Lots','Fees','PnL'}
                    assert isinstance(t['Symbol'],str) and isinstance(t['Date'],str)
                    for f in ('Entry','Exit','Lots','Fees','PnL'): assert isinstance(t[f],(int,float)) and abs(t[f])<1e15
                assert isinstance(x.get('saved_rules'),dict)
                for r in x['saved_rules'].values():
                    assert set(r)=={'min_rsi','max_rsi','rel_volume','trend','breakout','golden'}
                    assert 0<=r['min_rsi']<=r['max_rsi']<=100 and 0<=r['rel_volume']<=100
                    assert all(isinstance(r[k],bool) for k in ('trend','breakout','golden'))
                for k in payload: st.session_state[k]=x[k]
                st.rerun()
            except (ValueError,AssertionError,KeyError,TypeError): st.error('Invalid workspace backup.')

prices=demo_prices(); mode='DEMO · Synthetic prices, not live market data'
if source=='Yahoo Finance':
    if 'yahoo_bundle' not in st.session_state:
        st.title('HP Screener')
        st.info('Enter your IDX tickers in the sidebar, then click Fetch & scan to download Yahoo Finance prices.')
        st.stop()
    prices,report,fetched_at=st.session_state.yahoo_bundle
    request=st.session_state.yahoo_request
    try: changed=(normalize_symbols(tickers),history,include_today)!=request
    except ValueError: changed=True
    if changed:
        st.warning('Input settings have changed. Click Fetch & scan to apply them. Results below are from the previous fetch.')
    good=int(report.Status.eq('OK').sum())
    st.caption(f'Yahoo scan: {good} usable / {len(report)} requested · Retrieved {fetched_at}')
    if good<len(report): st.warning(f'{len(report)-good} tickers failed or were stale and are excluded. Open Download report for details.')
    with st.expander('Download report',expanded=good<len(report)):
        st.dataframe(report,hide_index=True,width='stretch')
        st.download_button('Export download report',report.to_csv(index=False).encode(),'hp-yahoo-report.csv','text/csv')
    if prices.empty:
        st.error('No usable Yahoo prices. Check the download report and retry. No demo prices have been substituted.')
        st.stop()
    mode='YAHOO FINANCE · Adjusted daily prices · May be delayed'
    if request[2]: st.warning('Today’s bar is included and may still be incomplete. Signals can change.')
    else: st.caption('Conservative daily scan: all bars dated today in Jakarta are excluded.')
    st.download_button('Export fetched prices',prices.to_csv(index=False).encode(),'hp-yahoo-prices.csv','text/csv')
elif source=='CSV upload':
    if upload is None:
        st.info('Upload a price CSV using the sidebar.'); st.stop()
    try:
        prices=parse_csv(upload.getvalue()); mode='IMPORTED · User-supplied daily prices'
    except Exception as e:
        st.error(f'Import failed: {e}'); st.stop()
results=cached_scan(prices)
st.caption(mode)
st.title(section)
st.caption(f'{len(results)} tickers · Latest date {prices.date.max():%d %b %Y} · Daily bars · All currency values in IDR')
if results.Date.nunique()>1: st.warning('Tickers have different latest dates. Check the Date column before comparing results.')

def table(d,name='results'):
    st.dataframe(d,hide_index=True,width='stretch',column_config={k:st.column_config.NumberColumn(format='%.2f') for k in ['Close','ChangePct','RSI','RelVolume','CMF'] if k in d})
    st.download_button('Export CSV',d.to_csv(index=False).encode(),f'hp-{name}.csv','text/csv',key='export_'+name)

def chart():
    a,b,c=st.columns([2,1,1]); symbol=a.selectbox('Stock',sorted(prices.symbol.unique())); period=b.selectbox('Period',['1 month','3 months','6 months','1 year'],index=2); overlay=c.multiselect('Overlays',['MA20','MA50','EMA20','EMA50'],default=['MA20','MA50'])
    d=indicators(prices[prices.symbol==symbol]); x=d.iloc[-1]
    m=st.columns(4)
    for col,label,val in zip(m,['Close','Change','RSI (14)','Relative volume'],[f'{x.close:,.0f}',f'{x.ChangePct:+.2f}%',f'{x.RSI:.1f}',f'{x.RelVolume:.2f}×']): col.metric(label,val)
    d=d.tail({'1 month':22,'3 months':66,'6 months':132,'1 year':260}[period])
    f=make_subplots(rows=3,cols=1,shared_xaxes=True,vertical_spacing=.03,row_heights=[.65,.18,.17])
    f.add_trace(go.Candlestick(x=d.date,open=d.open,high=d.high,low=d.low,close=d.close,name=symbol,increasing_line_color='#15803d',decreasing_line_color='#dc4141'),row=1,col=1)
    for col in overlay: f.add_trace(go.Scatter(x=d.date,y=d[col],name=col,line={'width':1.5}),row=1,col=1)
    f.add_trace(go.Bar(x=d.date,y=d.volume,name='Volume',marker_color='#b4c9bd'),row=2,col=1)
    for col in ['MACD','Signal']: f.add_trace(go.Scatter(x=d.date,y=d[col],name=col),row=3,col=1)
    f.update_layout(height=650,template='plotly_white',margin=dict(l=10,r=10,t=15,b=10),legend=dict(orientation='h'),xaxis_rangeslider_visible=False)
    f.update_xaxes(rangebreaks=[dict(bounds=['sat','mon'])]); st.plotly_chart(f,width='stretch')
    if st.button('Remove from watchlist' if symbol in st.session_state.watchlist else 'Add to watchlist'):
        if symbol in st.session_state.watchlist: st.session_state.watchlist.remove(symbol)
        else: st.session_state.watchlist.append(symbol)
        st.rerun()

if section=='Dashboard':
    cols=st.columns(4)
    for col,label,value in zip(cols,['Universe','Advancing','Above MA20 / MA50','Volume ≥ 1.5×'],[len(results),int((results.ChangePct>0).sum()),int(results.Trend.sum()),int((results.RelVolume>=1.5).sum())]): col.metric(label,value)
    st.subheader('Market workspace'); chart()
    st.subheader('Highest rule scores'); table(results.head(8),'dashboard')
elif section=='Stock Charts': chart()
elif section=='Market Overview':
    tab=st.segmented_control('View',['All stocks','Gainers','Losers','Volume leaders'],default='All stocks')
    d=results.copy()
    if tab=='Gainers': d=d[d.ChangePct>0].sort_values('ChangePct',ascending=False)
    elif tab=='Losers': d=d[d.ChangePct<0].sort_values('ChangePct')
    elif tab=='Volume leaders': d=d.sort_values('RelVolume',ascending=False)
    table(d,'market')
elif section=='Screener':
    st.write('Combine daily technical conditions. Every enabled condition must pass.')
    presets={'All stocks':dict(min_rsi=0,max_rsi=100,rel_volume=0.,trend=False,breakout=False,golden=False),'Trend + volume':dict(min_rsi=50,max_rsi=80,rel_volume=1.5,trend=True,breakout=False,golden=False),'Prior 20-day breakout':dict(min_rsi=0,max_rsi=100,rel_volume=1.,trend=False,breakout=True,golden=False),'Oversold watch':dict(min_rsi=0,max_rsi=35,rel_volume=0.,trend=False,breakout=False,golden=False)}
    options=list(presets)+['Saved: '+s for s in st.session_state.saved_rules]
    selected=st.selectbox('Preset',options)
    defaults=st.session_state.saved_rules[selected[7:]] if selected.startswith('Saved: ') else presets[selected]
    key=hashlib.sha256(selected.encode()).hexdigest()[:12]
    cols=st.columns(3)
    lo,hi=cols[0].slider('RSI range',0,100,(int(defaults['min_rsi']),int(defaults['max_rsi'])),key=key+'rsi')
    rv=cols[1].number_input('Minimum relative volume',0.,100.,float(defaults['rel_volume']),.1,key=key+'rv')
    search=cols[2].text_input('Ticker search').upper().strip()
    cols=st.columns(3)
    trend=cols[0].checkbox('Close > MA20 > MA50',defaults['trend'],key=key+'trend')
    breakout=cols[1].checkbox('Close > prior 20-day high',defaults['breakout'],key=key+'breakout')
    golden=cols[2].checkbox('EMA20 crosses above EMA50 today',defaults['golden'],key=key+'golden')
    d=results[results.RSI.between(lo,hi)&results.RelVolume.ge(rv)&results.Symbol.str.contains(search,regex=False)]
    for flag,column in [(trend,'Trend'),(breakout,'Breakout'),(golden,'GoldenCross')]:
        if flag: d=d[d[column]]
    st.subheader(f'{len(d)} matches / {len(results)} tickers'); table(d,'screen')
    name=st.text_input('Save these conditions as')
    if st.button('Save screen',disabled=not name.strip()):
        st.session_state.saved_rules[name.strip()]=dict(min_rsi=lo,max_rsi=hi,rel_volume=rv,trend=trend,breakout=breakout,golden=golden)
        st.success('Saved for this session. Download a workspace backup to keep it.')
    with st.expander('How scores are calculated'):
        st.write('Six equal checks: close above MA20; MA20 above MA50; RSI ≥ 50; MACD histogram positive; relative volume ≥ 1.5; CMF positive. Score is the percentage passed, not a probability or recommendation. Relative volume compares today with the previous 20 sessions. CMF is a price/volume proxy, not verified broker accumulation.')
elif section=='Watchlist':
    st.session_state.watchlist=st.multiselect('Tracked symbols',sorted(set(prices.symbol)|set(st.session_state.watchlist)),default=st.session_state.watchlist)
    missing=set(st.session_state.watchlist)-set(prices.symbol)
    if missing: st.warning('No data in this universe for: '+', '.join(sorted(missing)))
    table(results[results.Symbol.isin(st.session_state.watchlist)],'watchlist')
elif section=='Research Notes':
    symbol=st.selectbox('Stock',sorted(set(prices.symbol)|set(st.session_state.notes)))
    body=st.text_area('Thesis, triggers, invalidation and follow-up',value=st.session_state.notes.get(symbol,''),height=300,key='note_'+symbol)
    if st.button('Save note'): st.session_state.notes[symbol]=body; st.success('Saved for this session. Export a workspace backup to keep it.')
elif section=='Trading Journal':
    st.caption('Closed long trades. Fees are total entry + exit fees in IDR. One lot = 100 shares.')
    with st.form('trade'):
        cols=st.columns(3); date=cols[0].date_input('Exit date'); symbol=cols[1].selectbox('Symbol',sorted(prices.symbol.unique())); lots=cols[2].number_input('Lots',1,1000000,1)
        cols=st.columns(3); entry=cols[0].number_input('Entry price',1.,value=1000.); exit_price=cols[1].number_input('Exit price',1.,value=1100.); fees=cols[2].number_input('Total fees',0.,value=0.)
        if st.form_submit_button('Record closed trade'):
            st.session_state.journal.append(dict(Date=date.isoformat(),Symbol=symbol,Entry=entry,Exit=exit_price,Lots=lots,Fees=fees,PnL=(exit_price-entry)*lots*100-fees))
    if st.session_state.journal:
        trades=pd.DataFrame(st.session_state.journal); st.metric('Realized net P&L',f'{trades.PnL.sum():,.0f} IDR'); table(trades,'journal')
        remove=st.selectbox('Trade to remove',range(len(trades)),format_func=lambda i:f'{i+1}: {trades.iloc[i].Symbol} / {trades.iloc[i].Date}')
        if st.button('Remove selected trade'): st.session_state.journal.pop(remove); st.rerun()
    else: st.info('No closed trades recorded yet.')
elif section=='Calculators':
    risk,average=st.tabs(['Position sizing','Average price'])
    with risk:
        capital=st.number_input('Available capital (IDR)',1.,value=10000000.)
        pct=st.number_input('Risk budget (%)',.1,100.,1.,.1)
        a,b=st.columns(2); entry=a.number_input('Planned entry',1.,value=1000.); stop=b.number_input('Stop price',1.,value=950.)
        try:
            lots,cost,risk_value=position_size(capital,pct,entry,stop)
            for col,label,value in zip(st.columns(3),['Lots','Capital required','Planned price risk'],[f'{lots:,}',f'{cost:,.0f}',f'{risk_value:,.0f}']): col.metric(label,value)
            st.caption('Capped by both capital and risk budget. Excludes fees and slippage; actual loss can exceed planned risk.')
        except ValueError as e: st.error(str(e))
    with average:
        rows=st.data_editor(pd.DataFrame({'Price':[1000.,950.],'Lots':[10.,10.]}),num_rows='dynamic',hide_index=True,key='average_rows')
        if rows.empty or rows.isna().any().any() or (rows<=0).any().any() or (rows.Lots%1!=0).any(): st.info('Enter positive prices and whole positive lots.')
        else:
            st.metric('Weighted average price',f'{(rows.Price*rows.Lots).sum()/rows.Lots.sum():,.2f}')
            st.caption(f'Total: {rows.Lots.sum():,.0f} lots · Cost: {(rows.Price*rows.Lots*100).sum():,.0f} IDR before fees')
