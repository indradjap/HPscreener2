# HP Screener — Streamlit deployment package

This folder is the deployable repository root. Do not rename files and do not upload duplicate `(1)` copies beside them.

## Required GitHub root

```
app.py
market.py
yahoo.py
yahoo_download.py
ui.py
style.css
idx_quality_200.csv
requirements.txt
.streamlit/config.toml
```

`test_app.py`, `test_yahoo.py`, and `deploy_check.py` are optional for deployment but included for validation.

## Streamlit Community Cloud

1. Push **the contents of this folder** to the root of one GitHub repository.
2. Confirm the repository has exactly `app.py` (not `app(1).py`) and `requirements.txt` (not `requirements(1).txt`).
3. Deploy with entrypoint `app.py`.
4. Python 3.12 is the safest default. The pinned dependency set is also selected to have Python 3.14-compatible distributions as of September 2026.
5. Do not add the older HP package files to the same root; mixed old/new `market.py` or `yahoo.py` files can cause import errors.

## Local validation

```bash
python deploy_check.py
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Optional tests:

```bash
python -m unittest test_app test_yahoo -v
```

## Data notes

- `Quality 200` is the bundled static 200-name selection, not an official IDX index.
- Yahoo data is downloaded through `yfinance`; availability/rate limits depend on Yahoo and the hosting network.
- Yahoo failures are reported rather than silently replaced with demo prices.
