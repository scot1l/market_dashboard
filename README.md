# Market Dashboard

**Live Site**: https://market-dashboard-4bd66d.gitlab.io

Static stock dashboard with daily auto-refresh via GitLab CI/CD (Yahoo Finance), hosted on GitLab Pages.

## Features

- **Multi-Category ETF Tracking**: Monitor 180+ ETFs across 6 categories:
  - Indices (SPY, QQQ, DIA, etc.)
  - S&P Style ETFs (Value, Growth, etc.)
  - Select Sector ETFs (XLE, XLF, XLK, etc.)
  - Equal-Weight Sector ETFs
  - Industry ETFs
  - Country ETFs (EEM, EFA, etc.)

- **Advanced Technical Indicators**:
  - **Grade (ABC Rating)**: Trend strength based on EMA10 > EMA20 > SMA50 alignment
  - **ATR%**: Daily ATR as percentage of price
  - **ATRx**: Distance from SMA50 in ATR units
  - **1M-VARS**: Volatility-Adjusted Relative Strength vs SPY (21-day)
  - **VARS**: Relative strength visualization chart
  - **Daily/Intra/5D/20D**: Performance metrics with visual bars

- **Interactive Charts**: TradingView integration with:
  - Single chart view (one symbol at a time)
  - Multi-chart grid view (entire sector at once)
  - SPY overlay comparison
  - MA% Ribbon indicator

- **ETF Holdings**: View top 10 holdings for any ETF with weight percentages

- **Market Data Tools**:
  - Economic Calendar (TradingView widget)
  - Market Breadth overview

- **User Experience**:
  - Keyboard navigation (Arrow keys to browse, H for holdings)
  - Column sorting (click any header to sort)
  - Dark theme UI
  - Auto-refresh daily via GitLab CI/CD

## Build data locally

```bash
cd market-dashboard
pip install -r requirements.txt
python scripts/build_data.py --out-dir data
```

This generates: `data/snapshot.json`, `data/events.json`, `data/meta.json`, and `data/charts/*.png`.

**Local preview (required):** Do not double-click `index.html` - the browser will block loading `data/*.json`. From the `market-dashboard` folder run a local server, then open the URL:

```bash
cd market-dashboard
python -m http.server 8000
```

Then in your browser open: **http://localhost:8000**

## Publish to GitLab (first time)

1. On [GitLab](https://gitlab.com/new), create a **new repository** (e.g. `market-dashboard`). Do **not** add a README or .gitignore.
2. In a terminal, from the `market-dashboard` folder run (replace `YOUR_USERNAME` and repo name if different):

```bash
git remote add origin git@gitlab.com:YOUR_USERNAME/market-dashboard.git
git branch -M main
git push -u origin main
```

3. Then follow **Deploy to GitLab Pages** below.

## Deploy to GitLab Pages

1. Create a new GitLab repository and push this directory's contents to it (or push as the repo root).
2. **Before first deploy** you need initial data. Either:
   - **Recommended:** In the repo go to **CI/CD > Pipelines** > Run Pipeline. When it finishes, it will commit `data/` to the repo.
   - Or run locally: `python scripts/build_data.py --out-dir data`, then `git add data/`, commit and push.
3. In the repo **Settings > Pages**:
   - The site will be automatically deployed from the `main` branch.
   - Enable GitLab Pages in Settings if not already enabled.
4. The pipeline runs daily at 20:30 UTC (Mon-Fri) to refresh data; you can also run it manually from **CI/CD > Pipelines**.

Site URL: `https://<your-username>.gitlab.io/<repo-name>/`

## Project structure

```
market-dashboard/
├── .gitlab-ci.yml                    # Daily data refresh (GitLab CI/CD)
├── scripts/build_data.py             # Fetches data, outputs JSON + charts
├── data/                             # Generated (commit for Pages)
│   ├── snapshot.json
│   ├── events.json
│   ├── meta.json
│   └── charts/*.png
├── index.html                        # Static frontend
├── requirements.txt
└── README.md
```

Data: Yahoo Finance (yfinance), economic calendar (investpy). Charts: TradingView embed.
