# HP Screener — Two Menu Auto-Heatmap Test

This build contains only **Dashboard** and **Market Overview**.

## Market Overview fix

The TradingView heatmap is now emitted **before** the blocking Yahoo Quality-200 download, so the browser can start it as soon as Market Overview opens.

The TradingView embed now follows the official Stock Heatmap pattern more closely: `dataSource="Indonesia"`, `exchanges=[]`, empty `symbolUrl`, plus a one-time browser retry if TradingView does not inject its iframe promptly.

Yahoo Quality 200 still auto-loads and caches for 30 minutes. Yahoo failure no longer prevents the heatmap from being created.
