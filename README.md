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


## HPLP Lab v0.2 Directional

HPLP v0.2 keeps v0.1 available as a benchmark, but changes the default research model to a more directional pressure score. It adds 10-day close pressure, 20-day signed up/down-volume pressure, and a price-impact absorption factor designed to favor strong activity with positive volume pressure before full price expansion. Relative volume is deliberately reduced to a 5% default weight.

Backtest validation now includes same-date universe excess return, beat-universe rate, HPLP 80–100 minus 0–20 forward-return spread, positive spread days, and daily Spearman Rank IC. These metrics test whether HPLP has cross-sectional ranking power even when the overall market is weak.


## HPLP Lab v0.3

v0.3 separates **HPLP Pressure** from **Technical Confirmation**. Pressure uses the v0.2 directional liquidity model. Confirmation is a 0–100 score using only contemporaneous/past data: close above MA20, rising MA20, improving MACD histogram, 20D breakout, close above 20D VWAP, relative-volume confirmation and RSI 50–70.

The lab automatically compares four setups on the same dataset: HPLP High Score, Bullish HPLP Divergence, HPLP + Confirmation, and HPLP Divergence + Confirmation. This is intended to test whether confirmation improves forward return, excess return, win rate and path quality before any rule is promoted to the live screener.

## HPLP Lab v0.4 — Pressure → Trigger Study

v0.4 no longer treats a static bullish technical state as confirmation. It separates:

- **Pressure date**: HPLP identifies possible accumulation pressure.
- **Future trigger**: the first qualifying transition event within 3, 5, or 10 sessions.
- **Entry date**: the trigger date; forward return/MFE/MAE are measured from that trigger.

Trigger Score (0–100):
- fresh MA20 reclaim: 20
- fresh VWAP20 reclaim: 15
- MACD histogram cross above zero: 15
- RSI cross above 50: 10
- 10-session pivot breakout: 20
- relative volume >= 1.3x: 10
- close in upper 30% of daily range: 10

The lab automatically compares pressure-only entries against 3D/5D/10D trigger windows for
both HPLP High Score and Bullish HPLP Divergence setups.

Current execution assumption: entry at trigger-day close. This avoids using bars after the
trigger for the signal itself, but a later research version should also test next-session-open
execution for a more conservative implementation.


## Stock Pick v1

Medium-term swing-trade ranking menu (research horizon roughly 2–8 weeks).

Score = 100 points:
- Trend / MA structure: 20
- Relative Strength vs IHSG: 15
- Momentum (RSI, MACD, ADX): 15
- Breakout / relative volume / base quality: 20
- Accumulation (CMF, OBV, value acceleration, IDX foreign intensity): 15
- Risk / liquidity / ATR / extension: 15

Golden Cross is only a small bonus and is not required. The menu classifies candidates as
Base Breakout, Breakout, Pullback MA20, Trend Continuation, Early Reversal, or Momentum Watch.
Entry, stop, T1 and T2 are mechanical ATR-based research levels, not recommendations.
