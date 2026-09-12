# HP Screener — batch Yahoo edition

Independent Streamlit UI with the Yahoo batch downloader and 200-stock list ported from the supplied, working Antolui V6.2.5 package. Existing HP menus are preserved. No external account credentials are included.

## Deploy

Replace the existing GitHub repository's files with this folder's contents, including the NEW `yahoo_download.py` and `idx_quality_200.csv`. Keep `app.py` as the entrypoint. Streamlit will redeploy after the commit.

`requirements.txt` uses unpinned packages, matching the working reference's installation approach, and includes only the libraries used by HP. This allows the installer to resolve compatible versions but is not reproducible indefinitely. `requirements-tested.txt` records the actual local test versions; Streamlit should install `requirements.txt`. Python 3.12 remains the tested runtime. Do not claim Python 3.14 compatibility from these tests.

For a new private deployment: create a private GitHub repository, select it at https://share.streamlit.io, use branch main / app.py, choose Python 3.12 in Advanced settings and verify Sharing is set to Only specific people can view this app. Changing an existing app's Python version requires deleting and recreating its Streamlit deployment; keep the repository. Do not remove unrelated apps.

Official deployment reference: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

## Local start

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Yahoo workflow

1. Choose Yahoo Finance. Quality 200 is selected by default; alternatives are Quick test (18) or Custom tickers (up to 250).
2. Select history and batch size (default 60).
3. Click Fetch & scan. Charts and screens use the returned prices.

The 200-stock CSV contains 200 unique tickers: 80 tier A, 70 B and 50 C. This is a static selection from the supplied reference, not an official index or a freshly verified liquidity ranking. Tier labels are retained in the CSV but do not modify HP scores.

`yahoo_download.py` is copied from the reference `data.py`. It calls `yf.download` with `threads=True`, `group_by='column'`, `auto_adjust=False`, daily bars and two-year history by default. Requests run in batches. Both ticker-first and price-field-first MultiIndex responses are handled. Missing tickers are retried individually using the same yf.download method. HP's `yahoo.py` validates the returned frames and builds a report covering every requested ticker. The copied downloader retains the reference's default request timeouts, so slow individual retries remain possible.

This edition uses **unadjusted OHLC**, matching the reference. Corporate actions can distort historical technical signals; it does not implement a separate adjustment engine. Do not compare historical values directly with the previous adjusted HP edition.

Successful AND partial universe results are cached for 30 minutes. Select Bypass cached prices before fetching again to retry immediately. The timestamp is the cached retrieval timestamp, not a claim of fresh streaming quotes. No scheduled scans run in the background. Yahoo may delay, throttle or reject requests. No API key is required; yfinance is an unofficial client.

All Jakarta-dated bars for today are excluded by default, even after close. Include today only for provisional signals. Imports require 60 valid bars per symbol. Prices older than 7 calendar days are explicitly marked stale and excluded; long exchange closures can also trigger this conservative rule. Failures never cause synthetic substitution. The report distinguishes usable, failed and stale tickers and can be exported.

## Working menus

Dashboard, Market Overview, Stock Charts, Screener, Watchlist, Research Notes, Trading Journal, Calculators. The previously removed menus remain removed. CSV upload and explicit Demo mode remain sidebar input choices.

The chart supports candles, volume, MACD and MA/EMA20/50/200 overlays. Screener supports RSI, relative volume, trend, prior-high breakout, EMA20/50 cross, minimum traded value and Stoch RSI bullish cross. Every enabled condition must pass. Conditions can be saved with a workspace backup.

The liquidity gate defaults to Rp5 billion/day, following the reference scanner: mean(close × volume) over the latest 20 bars. This is an estimate of turnover, not exact intraday traded value. Set it to zero to disable. Even the All stocks preset respects this separate liquidity control.

Stoch RSI uses HP's Wilder RSI14, normalized over 14 RSI observations, then smoothed 3/3. Bullish cross requires K > D on the latest bar and K <= D on the preceding bar. A flat RSI range produces unavailable values and will not pass the cross condition.

HP retains its original six-check score: close > MA20, MA20 > MA50, RSI >=50, MACD histogram >0, relative volume >=1.5 and CMF20 >0. Each contributes one sixth of 100. It is not a probability. Relative volume continues to exclude today's bar from its 20-bar denominator, unlike the reference. EMA uses an SMA seed. MA200 is unavailable with less than 200 bars. CMF is a proxy, not broker accumulation.

Quick Pick, sector-relative strength, tier-weighted ranking, automatic entry/target planning and the reference's wider pattern engine have NOT been migrated. No claims of analyst-calibrated performance are made.

## Persistence and imports

Watchlist, notes, journal and saved rules remain session-only. Download a JSON workspace backup before closing. Restore it in another session; prices need a separate CSV upload or Yahoo fetch. Existing backups remain compatible; older saved rules receive the default liquidity filter and no Stoch RSI filter.

Price CSV columns: symbol,date,open,high,low,close,volume. Dates: YYYY-MM-DD. Prices: IDR, volume: shares. At least 60 rows per ticker; no duplicates, missing/invalid prices or inconsistent OHLC. Corporate-action adjustment must be consistent. Demo mode generates synthetic data, never actual market observations.

Position sizing and average price use 100 shares per lot. Position sizing excludes fees and slippage. Journal records closed long trades with total fees in IDR.

## Validation

```sh
python -m unittest test_app test_yahoo -v
```

Tests exercise all eight menus, note/journal actions, input validation and indicator checks; all 200 tickers through simulated four-batch responses (60/60/60/20) and the analysis engine; both MultiIndex orientations; individual missing-ticker recovery; failures, stale prices and current-day exclusion. Controlled data tests do not prove successful live coverage of the 200 names. Yahoo previously rate-limited requests from this environment. The user's working reference is evidence for the fetch design, not a guarantee of future provider availability.
