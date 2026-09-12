"""Fast deployment sanity check. Run: python smoke_test.py"""
import sys
import streamlit
import pandas
import numpy
import plotly
import yfinance
from market import demo, scan, position_size

prices = demo()
results = scan(prices)
assert len(prices) > 0
assert len(results) == 18
assert position_size(10_000_000, 1, 1000, 950) == (20, 2_000_000, 100_000)
print("HP Screener deployment smoke test: OK")
print("Python", sys.version.split()[0])
print("streamlit", streamlit.__version__)
print("pandas", pandas.__version__)
print("numpy", numpy.__version__)
print("plotly", plotly.__version__)
print("yfinance", yfinance.__version__)
