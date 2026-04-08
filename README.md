# China ETF Rotation Dashboard

Static A-share ETF dashboard for after-close regime reading and sector rotation.

The project now tracks a curated set of China-listed ETFs across:

- Broad market
- Growth themes
- Cyclicals
- Domestic demand
- Defense

The data pipeline builds a static snapshot with:

- `Grade`: EMA10 / EMA20 / SMA50 trend alignment
- `ATR%`
- `ATRx50`: distance from the 50-session average in ATR units
- `RS21`: 21-session volatility-adjusted relative-strength percentile versus a benchmark ETF
- `Group%`: 20-day return percentile inside the same group
- `Amt20`: average 20-session turnover in CNY 100m
- `AmtZ`: latest turnover shock versus the last 20 sessions

## Data source

- `AkShare`
- ETF history path: `fund_etf_hist_sina`

This avoids the U.S.-market assumptions from the original repo and works better from a China-based workflow.

## Build locally

```bash
pip install -r requirements.txt
python scripts/build_data.py --out-dir data
python -m http.server 8000
```

Then open:

- `http://localhost:8000`

## Generated files

The builder writes:

- `data/snapshot.json`
- `data/meta.json`
- `data/breadth.json`
- `data/charts/*.png`

## Recommended usage

- Run the build after the A-share cash close.
- Start with the breadth cards and the `Broad` group to determine regime.
- Then sort each group by `RS21`, `Group%`, or `AmtZ` to find leadership and expanding participation.
- Use the chart panel to confirm whether a theme is trending cleanly or already too extended.

## Notes

- This is an ETF rotation dashboard, not a stock-selection terminal.
- It is designed for discretionary next-day focus lists, not automated trade execution.
