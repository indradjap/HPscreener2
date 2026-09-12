"""Pure Python market calculations; no network or broker-data inference."""
import io
import numpy as np
import pandas as pd

SYMBOLS = ['BBCA','BBRI','BMRI','BBNI','TLKM','ISAT','ANTM','AMMN','INCO','ADRO','MEDC','PTBA','ASII','UNTR','ICBP','INDF','AMRT','CPIN']
COLS = ['symbol','date','open','high','low','close','volume']

def demo():
    rng = np.random.default_rng(42)
    dates = pd.bdate_range(end='2026-09-11', periods=260)
    frames=[]
    for i,s in enumerate(SYMBOLS):
        c=(1000+i*450)*np.exp(np.cumsum(rng.normal(.0006,.019,len(dates))))
        o=np.r_[c[0],c[:-1]]*rng.uniform(.995,1.005,len(c))
        frames.append(pd.DataFrame(dict(symbol=s,date=dates,open=o,high=np.maximum(c,o)*rng.uniform(1.002,1.025,len(c)),low=np.minimum(c,o)*rng.uniform(.975,.998,len(c)),close=c,volume=rng.integers(1000000,20000000,len(c)))))
    return pd.concat(frames,ignore_index=True)

def parse_csv(raw):
    d=pd.read_csv(io.BytesIO(raw))
    if not set(COLS).issubset(d): raise ValueError('Required columns: '+', '.join(COLS))
    d=d[COLS].copy()
    if d.isna().any().any(): raise ValueError('Missing values are not allowed.')
    d['symbol']=d.symbol.astype(str).str.strip().str.upper()
    if not d.symbol.str.fullmatch(r'[A-Z0-9.\-]{1,20}').all(): raise ValueError('Invalid ticker symbol.')
    if not d.date.astype(str).str.fullmatch(r'\d{4}-\d{2}-\d{2}').all(): raise ValueError('Dates must use YYYY-MM-DD.')
    d['date']=pd.to_datetime(d.date,format='%Y-%m-%d',errors='raise')
    for c in COLS[2:]: d[c]=pd.to_numeric(d[c],errors='raise')
    if not np.isfinite(d[COLS[2:]].to_numpy()).all(): raise ValueError('Numeric values must be finite.')
    if (d[['open','high','low','close']]<=0).any().any() or (d.volume<0).any(): raise ValueError('Prices must be positive; volume cannot be negative.')
    if ((d.high<d[['open','close','low']].max(axis=1)) | (d.low>d[['open','close','high']].min(axis=1))).any(): raise ValueError('Inconsistent OHLC prices.')
    if d.duplicated(['symbol','date']).any(): raise ValueError('Duplicate symbol/date rows.')
    if (d.groupby('symbol').size()<60).any(): raise ValueError('Each ticker requires at least 60 daily rows.')
    return d.sort_values(['symbol','date']).reset_index(drop=True)

def ema(s,n):
    out=pd.Series(np.nan,index=s.index)
    if len(s)>=n:
        out.iloc[n-1]=s.iloc[:n].mean()
        for i in range(n,len(s)): out.iloc[i]=s.iloc[i]*2/(n+1)+out.iloc[i-1]*(1-2/(n+1))
    return out

def indicators(d):
    d=d.sort_values('date').copy().reset_index(drop=True)
    c=d.close
    for n in (20,50): d[f'MA{n}']=c.rolling(n).mean(); d[f'EMA{n}']=ema(c,n)
    delta=c.diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
    ag=pd.Series(np.nan,index=d.index); al=ag.copy()
    if len(d)>14:
        ag.iloc[14]=gain.iloc[1:15].mean(); al.iloc[14]=loss.iloc[1:15].mean()
        for i in range(15,len(d)):
            ag.iloc[i]=(ag.iloc[i-1]*13+gain.iloc[i])/14
            al.iloc[i]=(al.iloc[i-1]*13+loss.iloc[i])/14
    d['RSI']=100-100/(1+ag/al.replace(0,np.nan))
    d.loc[(al==0)&(ag>0),'RSI']=100; d.loc[(al==0)&(ag==0),'RSI']=50
    d['MACD']=ema(c,12)-ema(c,26)
    signal=ema(d.MACD.dropna().reset_index(drop=True),9)
    d['Signal']=np.nan
    d.loc[d.MACD.notna(),'Signal']=signal.to_numpy()
    d['Histogram']=d.MACD-d.Signal
    d['RelVolume']=d.volume/d.volume.shift(1).rolling(20).mean().replace(0,np.nan)
    spread=(d.high-d.low).replace(0,np.nan)
    flow=((2*c-d.high-d.low)/spread).fillna(0)*d.volume
    d['CMF']=flow.rolling(20).sum()/d.volume.rolling(20).sum().replace(0,np.nan)
    d['PriorHigh']=d.high.shift(1).rolling(20).max()
    d['ChangePct']=c.pct_change()*100
    return d

def scan(prices):
    rows=[]
    for s,g in prices.groupby('symbol'):
        d=indicators(g); x=d.iloc[-1]; prev=d.iloc[-2]
        checks=[x.close>x.MA20,x.MA20>x.MA50,x.RSI>=50,x.Histogram>0,x.RelVolume>=1.5,x.CMF>0]
        rows.append(dict(Symbol=s,Date=x.date.date().isoformat(),Close=x.close,ChangePct=x.ChangePct,RSI=x.RSI,RelVolume=x.RelVolume,CMF=x.CMF,Score=round(sum(checks)/6*100),Trend=bool(x.close>x.MA20>x.MA50),Breakout=bool(x.close>x.PriorHigh),GoldenCross=bool(x.EMA20>x.EMA50 and prev.EMA20<=prev.EMA50),MACDPositive=bool(x.Histogram>0)))
    return pd.DataFrame(rows).sort_values('Score',ascending=False).reset_index(drop=True)

def position_size(capital,risk_pct,entry,stop):
    if capital<=0 or not 0<risk_pct<=100 or not 0<stop<entry: raise ValueError('Use positive capital and an entry above a positive stop.')
    lots=int(min(capital*risk_pct/100/(entry-stop),capital/entry)//100)
    return lots,lots*100*entry,lots*100*(entry-stop)
