# HP Screener — Streamlit deployment package

This package is rebuilt for Streamlit Community Cloud runtimes including Python 3.14.

## Files to upload to GitHub

Upload the contents of this folder to the repository root. `app.py`, `market.py`, `yahoo.py`, and `requirements.txt` must stay at the same level. Keep the `.streamlit` folder too.

## Streamlit Community Cloud

1. Push these files to a GitHub repository.
2. In Streamlit Community Cloud, create or redeploy the app.
3. Set the entrypoint to `app.py`.
4. Python 3.14 is supported by this package. Python 3.12/3.13 should also work with these dependencies.
5. Deploy.

The important dependency change from the previous package is `pandas==3.0.5`. The earlier package pinned `pandas==2.2.3`, which was a poor match for a Python 3.14 deployment environment.

## Local test

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python smoke_test.py
python -m unittest test_app test_yahoo -v
python -m streamlit run app.py
```

## Current application behavior

- Dashboard, Market Overview, Stock Charts, Screener, Watchlist, Research Notes, Trading Journal and Calculators are preserved.
- Yahoo Finance remains the default live-data source.
- Failed Yahoo downloads remain explicit and are never silently replaced by demo data.
- The current built-in symbol list contains 18 tickers. You can enter a larger list in the sidebar (up to 250).
- Yahoo Finance is an unofficial upstream source and can rate-limit cloud deployments. A successful app deployment does not guarantee every live Yahoo request will succeed.

## Deployment troubleshooting

If the build fails, copy the first error beginning with `ERROR`, `Traceback`, or `ModuleNotFoundError` from the Streamlit log. Dependency-install errors and Yahoo runtime errors are separate problems.
