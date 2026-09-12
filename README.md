# HP Screener — Two Menu Test Build

This package is intentionally reduced to **two menus only** so navigation and market-data behavior can be tested before the rest of HP Screener is reintroduced.

## Menus

1. **Dashboard**
   - Opens by default.
   - Fetches **BBCA.JK** automatically from Yahoo Finance.
   - Search accepts a four-character IDX ticker with or without `.JK` (for example `ISAT` or `ISAT.JK`).
   - 1M / 3M / 6M / 1Y chart windows.
   - Details toggles a recent-bars table.
   - Market button opens Market Overview.

2. **Market Overview**
   - TradingView IDX sector heatmap loads independently in the right panel.
   - Yahoo Quality 200 breadth/activity is optional and loads only when **Load Quality 200** is clicked.
   - VALUE / VOLUME / BREADTH modes.
   - Yahoo data is not mislabeled as foreign-flow data.

## Deploy to Streamlit Community Cloud

Upload the **contents of this folder** to the root of one GitHub repository. The repository root must contain `app.py` directly.

Use:

- Branch: `main`
- Main file path: `app.py`
- Recommended Python: 3.12

Then deploy. This build does not require secrets or API keys.

## Local test

```bash
python -m pip install -r requirements.txt
python deploy_check.py
streamlit run app.py
```

## Notes

- Yahoo Finance is an unofficial source through `yfinance`; rate limits or temporary provider failures can occur.
- The Dashboard catches a Yahoo failure and keeps the app/navigation alive.
- TradingView is embedded browser-side, so its widget requires normal browser internet access.
- The Quality 200 is the bundled HP test universe, not an official IDX index.
