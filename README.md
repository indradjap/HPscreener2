# HP Screener — Streamlit edition

A standalone Python rebuild of HP Screener with a clean light sidebar, green accents, Plotly candlestick charts, and eight working pages. No JavaScript build is required.

## Run locally

Use Python 3.11 or 3.12. From this folder:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Deploy privately on Streamlit Community Cloud

1. Create a **private** GitHub repository named `hp-screener-streamlit` and upload this folder's contents, including `.streamlit/config.toml`.
2. Sign into https://share.streamlit.io with the GitHub account that can access the repository.
3. Choose Create app, select that repository and branch, and set the entrypoint to `app.py`.
4. Choose Python 3.12 in Advanced settings and deploy.
5. Verify App settings → Sharing → **Only specific people can view this app**. Do not enable public access.

A local Git repository is included in the working checkout; the downloadable ZIP contains source files without Git history. No remote GitHub repository or Streamlit deployment was created in this environment. The previous React Site has not been replaced by this Python app.

Community Cloud currently allows one private app at a time. If your account already uses that slot, do not delete it automatically: choose another private hosting arrangement or decide which app to retain.

Official deployment and privacy references:
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app

## Working pages

- Dashboard: breadth, interactive chart, ranking.
- Market Overview: universe, gainers, losers, volume leaders and exports.
- Stock Charts: daily candles, volume, MA/EMA20/50, MACD and signal, watchlist action.
- Screener: RSI interval, relative volume, trend, prior 20-day high breakout, EMA20/50 crossover; presets, saved rules, CSV export.
- Watchlist: add/remove tickers and view screened metrics.
- Research Notes: ticker-specific thesis notes.
- Trading Journal: closed long trades, realized P&L after specified fees, removal and CSV export.
- Calculators: capital/risk-capped sizing and weighted average cost, 100 shares/lot.

Removed: AI Market Analyst, Education, Chart Detective, Data Sources page, insider/broker/ownership/foreign-flow pages, unconnected alerts and Telegram integrations. These are possible in Python, but require additional services or data and are outside this edition.

## Data and persistence

Defaults to **Yahoo Finance**. Click Fetch & scan in the sidebar to retrieve real adjusted daily OHLCV through yfinance. The default list contains 18 tickers; edit it to scan your own universe (up to 250), using BBCA or BBCA.JK. This list is not an official IDX index or a verified liquid-stock universe. Yahoo downloads use one request per ticker, one retry, a 15-second request timeout, and a 15-minute successful-result cache. Bypass cache explicitly when refreshing. There is no scheduled background refresh or broker feed.

Today’s Jakarta-dated bar is excluded by default, even after close, to avoid incomplete daily signals. Include it only if you want provisional signals. Prices may be delayed. Adjusted OHLC includes Yahoo corporate-action adjustments, so historical levels can differ from unadjusted exchange prices. Fetch report gives every requested ticker's status, bar count, latest date and failure reason; prices older than 7 calendar days are flagged and excluded (this conservative rule can also exclude prices during long exchange closures). At least 60 rows are required. Failed downloads are never replaced with demo prices. A partial universe is clearly labeled. Input edits require another Fetch & scan; old results are labeled until then. The displayed retrieval time is when the scan assembled its results; some prices can come from the 15-minute cache.

Choose Demo explicitly for the original 18 **synthetic demo** series fixed at September 11, 2026; they are not market observations and weekdays are not an IDX holiday calendar. Choose CSV upload to use your own prices in the sidebar; no dedicated Data Sources menu exists. Imports replace the entire session universe. Invalid input stops rendering instead of silently using demo prices.

CSV columns: `symbol,date,open,high,low,close,volume`. Dates must be YYYY-MM-DD. Minimum 60 rows per symbol, no duplicate symbol/date rows, finite positive prices, nonnegative volume, consistent high/low ranges. Rows are sorted before analysis. Zero reference volume produces undefined ratios rather than invented signals. Different latest dates are flagged. Imported prices must have consistent corporate-action adjustment; the app does not adjust them.

Watchlists, notes, saved rules and journal entries are **session-only** and are not shared between users. Download the JSON workspace backup to keep them, then restore in a future session. Price imports must be uploaded separately. No credentials or private account data are stored in the package. No persistent database or scheduled scans are included.

## Calculations

MA uses a simple rolling average. EMA is seeded with a simple average. RSI14 uses Wilder smoothing with the initial 14 changes. MACD is EMA12 minus EMA26 with an EMA9 signal. Relative volume uses the previous 20 bars, excluding today's volume. Breakout compares close with the preceding 20 highs. Golden cross is EMA20 crossing EMA50 on the last bar. CMF20 is a price/volume proxy and does not prove broker accumulation. Score is the percentage of six conditions passed, not a forecast probability. See the Screener explanation for the six checks.

Position sizing excludes fees/slippage and gaps can exceed the chosen stop. Journal fees are total IDR, not percentages. All prices and volumes come from the chosen input and must use consistent units (volume in shares).

## Validation

```sh
python -m unittest test_app test_yahoo -v
```

Tests cover indicator reference values, risk sizing, malformed imports, all eight page renders, screen preset changes, note saving and journal recording through Streamlit AppTest. These are runtime tests, not browser screenshot verification.

Extend `market.py` for your own technical analysis. Keep new calculations independent from `app.py` so they can be tested and reused in future scheduled scans.

## Yahoo adapter

`yahoo.py` owns ticker normalization, retrieval and the coverage report. `app.py` caches successful per-ticker requests and connects results to all charts and screens. No Yahoo API key is required. yfinance is an unofficial client; availability and rate limits depend on Yahoo and the deployment network. The app reports provider errors rather than promising uninterrupted access. Consult Yahoo terms for your intended use.

Reference: https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html

Validation for this update: all seven automated tests passed, including controlled Yahoo responses and partial-failure handling. A real BBCA.JK/ISAT.JK request from the build environment returned Yahoo rate-limit errors (and a connection timeout); successful external retrieval could not be verified here. Retry from your Streamlit deployment or local machine. The app requires working outbound access to Yahoo Finance.
