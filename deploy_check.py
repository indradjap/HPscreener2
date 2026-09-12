"""Fast repository sanity check. Does not contact Yahoo Finance."""
from pathlib import Path
import ast
import csv

ROOT=Path(__file__).resolve().parent
REQUIRED=[
    'app.py','market.py','yahoo.py','yahoo_download.py','ui.py','style.css',
    'idx_quality_200.csv','requirements.txt'
]
missing=[name for name in REQUIRED if not (ROOT/name).exists()]
if missing:
    raise SystemExit('Missing required files: '+', '.join(missing))

for name in ['app.py','market.py','yahoo.py','yahoo_download.py','ui.py']:
    ast.parse((ROOT/name).read_text(encoding='utf-8'), filename=name)

with (ROOT/'idx_quality_200.csv').open(newline='',encoding='utf-8-sig') as f:
    rows=list(csv.DictReader(f))
if 'Ticker' not in (rows[0].keys() if rows else []):
    raise SystemExit('idx_quality_200.csv is missing the Ticker column')
tickers=[r['Ticker'].strip().upper() for r in rows]
if len(tickers)!=200 or len(set(tickers))!=200:
    raise SystemExit(f'Expected 200 unique tickers, found {len(set(tickers))} unique / {len(tickers)} rows')
if any(len(t)!=4 or not t.isalnum() for t in tickers):
    raise SystemExit('Every bundled IDX ticker must be exactly four alphanumeric characters')
print('DEPLOY CHECK OK: files, Python syntax, and 200-stock universe are valid.')
