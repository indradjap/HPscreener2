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
