"""Yahoo daily prices for IDX; explicit failures, no synthetic fallback."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
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

def quality_universe():
    from pathlib import Path
    table=pd.read_csv(Path(__file__).with_name('idx_quality_200.csv'))
    symbols=normalize_symbols(' '.join(table.Ticker.astype(str)))
    if len(symbols)!=200: raise ValueError('Bundled universe must contain 200 distinct tickers.')
    return symbols

def fetch_universe(symbols,period='2y',include_today=False,chunk_size=60):
    from yahoo_download import download_universe
    raw_frames,errors=download_universe(symbols,period=period,chunk_size=chunk_size)
    frames=[]; reports=[]
    today=datetime.now(ZoneInfo('Asia/Jakarta')).date()
    for s in symbols:
        try:
            if s+'.JK' not in raw_frames: raise ValueError(errors.get(s+'.JK','No data returned'))
            d=raw_frames[s+'.JK'].copy().reset_index()
            d=d.rename(columns={d.columns[0]:'date',**{c:c.lower() for c in d.columns[1:]}})
            d['date']=pd.to_datetime(d.date)
            if d.date.dt.tz is not None: d['date']=d.date.dt.tz_convert('Asia/Jakarta').dt.tz_localize(None)
            if not include_today: d=d[d.date.dt.date<today].copy()
            d['date']=d.date.dt.strftime('%Y-%m-%d');d['symbol']=s
            d=parse_csv(d.to_csv(index=False).encode())
            latest=d.date.max().date(); stale=(today-latest).days>7
            reports.append(dict(Symbol=s,Yahoo=s+'.JK',Status='Stale — excluded' if stale else 'OK',Rows=len(d),Latest=latest.isoformat(),Detail='Older than 7 calendar days; check suspension or provider coverage.' if stale else ''))
            if not stale: frames.append(d)
        except Exception as exc:
            reports.append(dict(Symbol=s,Yahoo=s+'.JK',Status='Failed',Rows=0,Latest='',Detail=str(exc)[:300]))
    return (pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(),pd.DataFrame(reports),datetime.now(ZoneInfo('Asia/Jakarta')).isoformat(timespec='seconds'))
