# HP Screener — menu-router fixed edition

This build fixes the grouped sidebar navigation so menu state remains deterministic on Streamlit reruns.

## Menu fixes

- Sidebar buttons now use an explicit click -> route state -> `st.rerun()` flow instead of callback-only navigation.
- The app no longer uses global `st.stop()` calls for missing Yahoo/CSV data.
- Data-dependent pages remain navigable and show a clear Market Data Required state when no prices are loaded.
- Independent pages remain fully usable without market data: HP Desk, Stock Universe, Trading Journal, Risk Calculator, Average Price, Saved Screens.
- A `Use Demo data now` action is available from gated market pages.
- Watchlist/chart/screener shortcuts continue to route through the same central page state.

## Deploy

Upload the *contents* of this folder to the root of the GitHub repository. Keep `app.py` as the Streamlit entrypoint.

Required root files include `app.py`, `ui.py`, `style.css`, `market.py`, `yahoo.py`, `yahoo_download.py`, `idx_quality_200.csv`, and `requirements.txt`.

Run the package check locally with:

```bash
python deploy_check.py
```

Start locally with:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```
