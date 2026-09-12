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

## Stock Analysis

Single-stock swing research page. Search any 4-character IDX ticker to review technical structure, relative strength versus IHSG, support/resistance, Stock Pick Score, conditional entry scenarios, ATR-based stop/targets, invalidation conditions, and a concise analysis summary. Stock Pick rows link directly into this page through the **Analyze** button.

## IDX price-fraction handling

Executable Stock Pick / Stock Analysis plan prices now follow IDX regular/cash
market price fractions:

- reference close < Rp200: Rp1
- Rp200 to < Rp500: Rp2
- Rp500 to < Rp2,000: Rp5
- Rp2,000 to < Rp5,000: Rp10
- >= Rp5,000: Rp25

IDX applies the applicable fraction for one full trading day and adjusts it on
the next trading day when the closing price moves into another price group.
For next-session swing plans, the latest close is used as the fraction reference.
Entry-zone lows and stops round down; entry-zone highs, breakout triggers and
targets round up to valid executable prices.

## Stock Analysis data-label / Foreign 20D update

- The green delta below Price is explicitly labeled `20D Return`.
- `Foreign 20D` is available even when a ticker is entered directly in Stock Analysis.
  The page caches the latest 20 IDX trading sessions and calculates the same foreign
  intensity used by Smart Money Screener:
  `sum(ForeignBuy - ForeignSell) / sum(abs(ForeignBuy) + abs(ForeignSell)) * 100`.
- If IDX history is temporarily unavailable, Stock Analysis remains usable and the
  Foreign 20D field shows a dash rather than failing the whole page.

## Stock Analysis Price card UI

The Price card now shows `20D Return` as a separate labeled row inside the card,
rather than using Streamlit's compact metric delta. This prevents the percentage
from being truncated while keeping positive/negative color semantics.


## Stock Analysis metric layout refinement

- Replaced mixed Streamlit/custom metric row with fully custom aligned metric cards.
- Price, RSI, ADX, Rel Volume, CMF20, and Foreign 20D now share the same visual height.
- Added wider inner spacing inside the Stock Analysis summary panel so the metric boxes no longer feel too close to the outer frame.

## Stock Pick — Buy on Support / Rebound

A dedicated support/rebound setup has been added without replacing the original
Stock Pick ranking model.

Hard filters (all required):
- Near Support
- No Breakdown
- Recent Correction

Timing score (0–100):
- Stoch RSI Oversold: 10
- Stoch RSI Golden Cross: 15
- MACD Improving: 10
- MACD Golden Cross: 15
- MACD Positive: 10
- Drying Pullback Volume: 8
- Rebound Volume: 10
- Reversal Candle at support: 7
- Psychological Level: 5
- Risk/Reward: up to 10

When this setup is selected, the table uses the support score and a support-specific
entry / stop / target plan. Other Stock Pick setup modes retain their original logic.

## Swing target framework

Stock Pick now uses a consistent risk-multiple ladder for planned exits:

- Stop: below structural support / invalidation with an ATR buffer, rounded to the valid IDX fraction.
- `R = entry midpoint - stop`.
- TP1: approximately 2R (preferred minimum is about 1.5R).
- TP2: approximately 3R.
- TP3: approximately 4R.

For Buy on Support / Rebound, the nearest meaningful resistance is still used as a
structural risk/reward quality check. This prevents a mathematically attractive
2R target from automatically receiving a high Good-RR score when nearby resistance
would likely cap the move earlier.

## Stock Analysis R-multiple target framework

Stock Analysis now uses the same swing risk framework as Stock Pick:

- Stop: below the relevant structural invalidation / support with ATR buffer.
- R = entry midpoint - stop.
- TP1: approximately 2R, with >=1.5R preferred as the minimum attractive first objective.
- TP2: approximately 3R.
- TP3: approximately 4R+.
- Nearest meaningful resistance is shown separately with a Structure RR value.

The R-multiple ladder remains the mechanical profit-taking framework. Structure RR
is a sanity check: if nearby resistance is below about 1.5R, the setup is flagged as
structurally tight even if mathematical TP2/TP3 levels are farther away.
