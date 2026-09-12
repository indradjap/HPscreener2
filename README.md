# HP Screener — Dashboard + Market Overview (TradingView-style native IDX heatmap)

This test build keeps only **Dashboard** and **Market Overview**.

## Market Overview
- Foreign vs Domestic Net Flow: official IDX investor data.
- Native IDX Sectoral Heatmap: no TradingView widget and no S&P fallback.
- Heatmap toolbar:
  - Universe: All Indonesian companies / Quality 200
  - Size by: Market cap / Traded value
  - Color by: Change 1D %
  - Group by: Sector / SubSector
- Sector/group parents are visually separated from stock tiles.
- Horizontal red/neutral/green legend matches the supplied reference more closely.
- Stock hover shows company, group, 1D change, close, market cap and traded value.

Stock logos are intentionally not fabricated. The current IDX feeds used by this build do not supply a reliable logo URL for every issuer. The tiles therefore use ticker + daily change, while company information is available on hover.

## Deploy
Upload the contents of this folder to the GitHub repository root and deploy `app.py` on Streamlit Community Cloud.


## v3 heatmap visibility fix
Removed the Plotly treemap depth cap that hid stock-level tiles. The tree is IDX root → sector/subsector → stock; the previous `maxdepth=2` rendered sector parents but suppressed stock leaves. v3 renders the full tree.


## Sidebar refinement v4

Removed the `WORKSPACE` navigation group label. Dashboard and Market Overview now appear directly under the HP Screener branding with no menu grouping.


## Top Movers addition
Market Overview now adds a native Top Movers card below investor flow and the heatmap. It uses the same official IDX daily stock summary already loaded by the heatmap; no new provider is required. Tabs: Top Gainer, Top Loser, Top Value, Top Volume, Top Frequency.

## Smart Money Screener v1

A third menu adds four functioning screening models on the bundled Quality 200 universe:
Foreign Accumulation, Money Flow Accumulation, Technical Breakout, and Smart Money + Technical.
Yahoo 2-year daily OHLCV supplies MA20/50/200, RSI, Stoch RSI, VWAP20, CMF20, OBV, MACD,
relative volume and breakouts. Recent whole-market IDX daily summaries provide directional
foreign-buy/foreign-sell imbalance when the public IDX endpoint is available. Results are cached
for 30 minutes. Saved screens are session-only. The foreign metric is expressed as a normalized
imbalance percentage so the UI does not assume a monetary unit for fields whose public endpoint
metadata does not explicitly expose one.

## Smart Money universe modes

Smart Money Screener supports **Quality 200** and **All IDX**.

`All IDX` uses a two-stage architecture:

1. Official IDX whole-market daily summaries evaluate every available IDX stock using
   liquidity, traded value, volume, foreign imbalance, and simple close-based activity.
2. Only Stage-1 candidates are sent to Yahoo Finance for 2-year OHLCV technical
   confirmation (MA20/50/200, RSI, Stoch RSI, VWAP, CMF, OBV, MACD and breakouts).

The UI shows the full Stage-1 universe count, candidate count, and successful Yahoo
technical count so a reduced technical set is never hidden from the user.

## HPLP Lab v0.1

The fourth menu is an isolated research/backtest environment for HP Liquidity Pressure.
It does not modify Smart Money Screener signals.

HPLP v0.1 Core uses five historically available Yahoo OHLCV factors:
- CMF pressure
- OBV slope
- traded-value acceleration
- relative volume
- close location inside the 20-session range

Each factor is percentile-ranked cross-sectionally on each date before applying the user-defined weights. Historical foreign intensity is intentionally excluded in v0.1 because the current official IDX integration only supplies a short recent foreign-flow history. A future HPLP+ version can add it once a defensible long archive is available.

Backtest outputs include forward return, MFE, MAE, +5% before -3%, score buckets, year-by-year stability, and optional de-duplication of overlapping signals. All-IDX mode uses the current listed/liquid universe and therefore has survivorship/current-listing bias; Quality 200 is the recommended first calibration universe.
