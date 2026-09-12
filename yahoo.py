"""Yahoo daily prices for IDX; explicit failures, no synthetic fallback."""
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import yfinance as yf
from market import parse_csv

def normalize_symbols(text):
    tokens=re.split(r'[\s,;]+',text.strip().upper())
    symbols=[]
    for token in tokens:
        if not token: continue
        s=token[:-3] if token.endswith('.JK') else token
        if not re.fullmatch(r'[A-Z0-9]{4}',s): raise ValueError(f'Invalid IDX ticker: {token}. Use four-character codes, optionally ending .JK.')
        if s not in symbols: symbols.append(s)
    if not symbols: raise ValueError('Enter at least one ticker.')
    if len(symbols)>250: raise ValueError('Maximum 250 tickers per scan.')
    return tuple(symbols)

def fetch_one(symbol,period='2y',include_today=False):
    error=None
    for attempt in range(2):
        try:
            raw=yf.Ticker(symbol+'.JK').history(period=period,interval='1d',auto_adjust=True,actions=False,timeout=15,raise_errors=True)
            if raw.empty: raise ValueError('Yahoo returned no prices.')
            d=raw.reset_index().rename(columns=lambda c:str(c).lower())
            d['date']=pd.to_datetime(d['date'])
            if d.date.dt.tz is not None: d['date']=d.date.dt.tz_convert('Asia/Jakarta').dt.tz_localize(None)
            today=datetime.now(ZoneInfo('Asia/Jakarta')).date()
            if not include_today: d=d[d.date.dt.date<today].copy()
            d['date']=d.date.dt.strftime('%Y-%m-%d'); d['symbol']=symbol
            clean=parse_csv(d.to_csv(index=False).encode())
            return clean
        except Exception as exc:
            error=exc
            if attempt==0: time.sleep(.75)
    raise ValueError(f'{type(error).__name__}: {str(error)[:250]}')

def fetch_universe(symbols,period='2y',include_today=False,loader=fetch_one,progress=None):
    frames=[]; reports=[]
    today=datetime.now(ZoneInfo('Asia/Jakarta')).date()
    for i,s in enumerate(symbols):
        try:
            d=loader(s,period,include_today)
            latest=d.date.max().date(); age=(today-latest).days
            stale=age>7
            reports.append(dict(Symbol=s,Yahoo=s+'.JK',Status='Stale — excluded' if stale else 'OK',Rows=len(d),Latest=latest.isoformat(),Detail='Older than 7 calendar days; check suspension or provider coverage.' if stale else ''))
            if not stale: frames.append(d)
        except Exception as exc:
            reports.append(dict(Symbol=s,Yahoo=s+'.JK',Status='Failed',Rows=0,Latest='',Detail=str(exc)[:300]))
        if progress: progress((i+1)/len(symbols))
    prices=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    return prices,pd.DataFrame(reports),datetime.now(ZoneInfo('Asia/Jakarta')).isoformat(timespec='seconds')
