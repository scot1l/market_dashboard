# China ETF Rotation Dashboard

Static A-share ETF dashboard for after-close regime reading and sector rotation.

Live dashboard: https://scot1l.github.io/market_dashboard/

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

## Deploy to GitHub Pages

This repo is a static site, so GitHub Pages can serve it directly from the
generated files in `index.html` and `data/`.

1. Push `main` to GitHub.
2. In GitHub, open **Settings > Pages**.
3. Set **Source** to **GitHub Actions**.
4. Run the **Deploy GitHub Pages** workflow, or push a commit to `main`.

For the current GitHub repository, the site URL will be:

- `https://scot1l.github.io/market_dashboard/`

The **Refresh dashboard data** workflow keeps the generated JSON and chart files
updated. When it completes successfully, the Pages deployment workflow publishes
the refreshed static site.

The refresh job polls at 15:30, 16:30, 17:30, and 18:30 Asia/Shanghai, Monday
through Friday. Each run rebuilds `data/`, commits only when the generated files
changed, and then lets the Pages workflow publish the latest snapshot. For an
immediate refresh, run **Refresh dashboard data** from the GitHub Actions tab.

## Generated files

The builder writes:

- `data/snapshot.json`
- `data/meta.json`
- `data/breadth.json`
- `data/breadth_swing.json` (optional; skipped when live breadth sources are unavailable or out of sync)
- `data/charts/*.png`

## Recommended usage

- Run the build after the A-share cash close.
- Start with the breadth cards and the `Broad` group to determine regime.
- Then sort each group by `RS21`, `Group%`, or `AmtZ` to find leadership and expanding participation.
- Use the chart panel to confirm whether a theme is trending cleanly or already too extended.

## Notes

- This is an ETF rotation dashboard, not a stock-selection terminal.
- It is designed for discretionary next-day focus lists, not automated trade execution.
