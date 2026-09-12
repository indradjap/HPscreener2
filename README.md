# HP Screener — Two-menu IDX-corrected test

Minimal functional test app containing only:

1. **Dashboard** — BBCA.JK by default, searchable single-stock Yahoo chart.
2. **Market Overview** — official IDX investor flow + native IDX stock heatmap.

## What changed in Market Overview

The TradingView widget has been removed because an invalid/unsupported Indonesia widget datasource could silently fall back to S&P 500.

### Foreign vs Domestic Net Flow
Market Overview reads IDX Digital Statistics daily trading-by-investor buckets and derives:
- Foreign Buy / Foreign Sell / Net Foreign
- Domestic Buy / Domestic Sell
- VALUE, VOLUME, and FREQUENCY views

### IDX heatmap
The heatmap is rendered natively with Plotly from IDX website endpoints:
- latest whole-market stock summary for close/change/volume/listed shares
- IDX stock-screener metadata for sector and market capitalization

It therefore cannot display US/S&P stocks. It attempts the latest recent trading day automatically and caches successful data for 15 minutes.

## Deploy

Extract the ZIP and upload its *contents* to the root of a GitHub repository. Streamlit entrypoint: `app.py`.
