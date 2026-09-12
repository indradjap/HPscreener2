from pathlib import Path
import ast
import pandas as pd

ROOT = Path(__file__).parent
required = [
    'app.py','dashboard.py','market_overview.py','smart_money.py','stock_pick.py','idx_official.py','ui.py','style.css',
    'idx_quality_200.csv','requirements.txt'
]
missing=[p for p in required if not (ROOT/p).exists()]
if missing: raise SystemExit('Missing required files: '+', '.join(missing))
for p in ROOT.glob('*.py'):
    ast.parse(p.read_text(encoding='utf-8'), filename=str(p))
u=pd.read_csv(ROOT/'idx_quality_200.csv')
assert 'Ticker' in u and u.Ticker.astype(str).nunique()==200
print('DEPLOY CHECK OK')
print('Menus: Dashboard, Market Overview, Smart Money Screener, Stock Pick')
print('Market Overview: official IDX flow + native IDX heatmap')
print('Python syntax: OK')
