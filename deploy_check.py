from pathlib import Path
import py_compile
import pandas as pd

ROOT = Path(__file__).resolve().parent
required = [
    'app.py', 'ui.py', 'dashboard.py', 'market_overview.py', 'market.py',
    'yahoo.py', 'yahoo_download.py', 'idx_quality_200.csv', 'style.css',
    'requirements.txt', '.streamlit/config.toml'
]
missing = [name for name in required if not (ROOT / name).exists()]
if missing:
    raise SystemExit('Missing required files: ' + ', '.join(missing))

for name in ['app.py','ui.py','dashboard.py','market_overview.py','market.py','yahoo.py','yahoo_download.py']:
    py_compile.compile(str(ROOT / name), doraise=True)

u = pd.read_csv(ROOT / 'idx_quality_200.csv')
if 'Ticker' not in u.columns or u['Ticker'].astype(str).str.upper().nunique() != 200:
    raise SystemExit('idx_quality_200.csv must contain exactly 200 unique tickers.')

app = (ROOT / 'app.py').read_text(encoding='utf-8')
if "section == 'Dashboard'" not in app or "section == 'Market Overview'" not in app:
    raise SystemExit('Two-menu router is incomplete.')
if any(x in app for x in ['Technical Screener', 'Stock Charts', 'Trading Journal']):
    raise SystemExit('Unexpected old menu routes remain in app.py.')

print('DEPLOY CHECK OK')
print('Menus: Dashboard, Market Overview')
print('Universe: 200 unique IDX tickers')
print('Python syntax: OK')
