# Dashboard Indicator Guide

This guide explains how each indicator in the dashboard is calculated and how to read it.

Scope:
- It covers the values rendered from `data/snapshot.json`, `data/breadth.json`, and `data/breadth_swing.json`.
- "Good" and "bad" here mean better or worse for this dashboard's use case: after-close ETF rotation review.
- Unless noted otherwise, returns are simple percentage returns over trading sessions.

## Reading rules used across the dashboard

### Rank-based scores

Several breadth scores are cross-sectional percentiles inside the current snapshot, not absolute market formulas.

- `series_rank_pct(x)` ranks each item within the current peer set and scales it to `0-1`.
- Most breadth scores then multiply the weighted result by `100`, so the display is `0-100`.
- Higher is better for `strength_score`, `persistence_score`, `confirmation_score`, `leadership_score`, `heat_score`, `regime.score`, and `momentum_health.score`.
- Higher is worse for `fake_score`.

### Color and bar cues

- `1D`, `5D`, and `20D` table cells show the real percentage value as text.
- The green/red background bar behind those values is normalized only inside the same group, using that group's min and max for the column. It is a relative cue, not a cross-group absolute scale.
- Positive/negative signal tones come from simple code rules:
  - Signed-value signals are positive if the value is above zero, negative if below zero, otherwise neutral.
  - Score-based signals are usually positive at `>= 70` and negative at `<= 40`, unless a section overrides the thresholds.

## Overview cards

| Indicator | How it is calculated | How to read it |
| --- | --- | --- |
| `Tone` | Uses only the `Broad` ETF group. `Risk-on` if Broad `avg_5d > 0` and `above_sma50 / count >= 0.5`; `Risk-off` if Broad `avg_5d < 0` and `above_sma50 / count < 0.5`; otherwise `Mixed`. | `Risk-on` is constructive. `Mixed` means conflicting evidence. `Risk-off` means the broad tape is weak. |
| `Strongest` | Group with the highest `avg_rs_21d`. | Better when leadership is coming from a group you want to rotate into. |
| `Weakest` | Group with the lowest `avg_rs_21d`. | Usually avoid unless you are specifically looking for mean reversion. |
| `Breadth` | Two percentages across all dashboard ETFs: `% above EMA20` and `% above SMA50`. | Higher is better. EMA20 shows short/intermediate participation; SMA50 is the harder medium-term test. |

## Group summary cards

Each group card shows:

| Indicator | How it is calculated | How to read it |
| --- | --- | --- |
| `RS` | Average `rs_21d` across ETFs in the group. | Higher means the group is outperforming its own benchmarks more consistently. |
| `5D` | Average 5-day return of ETFs in the group. | Positive is near-term momentum; negative is short-swing weakness. |
| `>EMA20` | Count of ETFs in the group with latest close above EMA20. | Higher counts mean broader short/intermediate participation. |
| `>SMA50` | Count of ETFs in the group with latest close above SMA50. | Higher counts mean healthier medium-term trend structure. |

## Setup scan

| Indicator | How it is calculated | How to read it |
| --- | --- | --- |
| `X of Y ETFs currently qualify as good setups` | Counts rows where `good_setup = true` across the full snapshot. | More marked names means the scan is finding more actionable candidates. Zero means nothing currently matches the rules. |
| `Good setup` badge | A row is marked when it matches either `Trend setup` or `Early rotation`. | Positive screen result, but still needs chart confirmation. |

Exact setup rules:

### Trend setup

Marked when all of these are true:

- `grade == A`
- `rs_21d >= 80`
- `group_rank_20d >= 70`
- `amount_z_20d > 0`
- `0 <= atrx50 <= 2`

How to read it:
- Best classic trend-following profile.
- Good when you want confirmed leadership with participation.
- Worse when `ATRx50` is already too stretched above this zone.

### Early rotation

Marked when all of these are true:

- `grade == B`
- `above_ema20 == true`
- `60 <= rs_21d <= 80`
- `group_rank_20d >= 60`
- `amount_z_20d >= 1`
- `-1 <= atrx50 <= 1`

How to read it:
- Earlier than a full leader.
- Good when money flow and relative rank are improving before the chart becomes obvious.
- Worse when it loses EMA20 or the volume shock fades.

## ETF table and chart chips

The chart panel chips reuse the same row metrics, so the definitions below apply to both the table and the right-side chip strip.

| Indicator | How it is calculated | How to read it |
| --- | --- | --- |
| `Grade` | From moving-average alignment: `A` if `EMA10 > EMA20 > SMA50`; `C` if `EMA10 < EMA20 < SMA50`; otherwise `B`. | `A` is the cleanest uptrend. `B` is transition or mixed structure. `C` is weak/downtrend structure. |
| `1D` | `(close[t] / close[t-1] - 1) * 100` | Latest push only. Good for spotting immediate pressure, but too noisy by itself. |
| `5D` | `(close[t] / close[t-5] - 1) * 100` | Best quick swing-momentum check. Positive is constructive; strong negative means recent weakness. |
| `20D` | `(close[t] / close[t-20] - 1) * 100` | Monthly leg. Positive is healthier trend context than a name that is only bouncing for one or two days. |
| `ATR%` | First compute 14-day ATR using Wilder-style EMA of true range, then `ATR / latest_close * 100`. | Higher means more movement and more risk per position unit. Not automatically bad, but it demands smaller sizing. |
| `ATRx50` | `(latest_close - SMA50) / ATR14` | Around `0` to `+2` is constructive. Above `+3` is often stretched. Below `0` means price is still below its 50-day average. |
| `RS21` | Build volatility-adjusted relative strength versus the ETF's benchmark. For each day: `rrs = (asset_change - expected_move) / asset_ATR`, where `expected_move = (benchmark_change / benchmark_ATR) * asset_ATR`. Smooth with a 50-day rolling mean, then take the percentile of the latest smoothed value inside the last 21 observations. | `80-100` is strong leadership, `40-60` is middling, `0-20` is lagging. Higher is better. |
| `Group%` | Percentile rank of the ETF's `20D` return inside its own dashboard group. | High means it is beating its direct peers, not just beating the benchmark. |
| `Amt20` | Average `amount` over the last 20 sessions, divided by `100,000,000`, so the unit is CNY `100m`. | Higher is better for liquidity and follow-through credibility. |
| `AmtZ` | Z-score of the latest traded amount versus the last 20 sessions: `(latest_amount - mean_20) / std_20`. | `> 0` means participation is expanding. `> +1` is notable. `< 0` means interest is fading. |
| `RS` mini chart | Bars are the last 20 values of `rolling_rrs`; the orange line is a 20-point moving average of that smoothed series; the dashed line is zero. | Bars and line above zero mean relative outperformance. Below zero means underperformance. Rising bars with a rising signal line are best. |

## Swing breadth panel

This panel is optional and only renders when `data/breadth_swing.json` exists and its `market_date` matches the ETF snapshot date.

### Regime

#### Regime score

Formula:

```text
regime_score =
(
  scale(turnover_ratio, 0.85, 1.25) * 0.24 +
  scale(northbound_net_flow_100m, -120, 180) * 0.18 +
  scale(ad_ratio, 0.7, 3.0) * 0.24 +
  scale(limit_spread, -15, 90) * 0.16 +
  ((above_20_pct / 100) * 0.45 + (above_50_pct / 100) * 0.55) * 0.18
) * 100
```

Where:
- `scale(x, low, high)` clamps `(x - low) / (high - low)` into `0-1`
- `turnover_ratio = latest_turnover / 20-day average turnover`
- `ad_ratio = advancers / max(decliners, 1)`
- `limit_spread = real_limit_up - real_limit_down`
- `above_20_pct` and `above_50_pct` are industry-board participation rates

Labels:

| Label | Threshold |
| --- | --- |
| `Expansion` | `>= 72` |
| `Constructive` | `>= 58` and `< 72` |
| `Mixed` | `>= 45` and `< 58` |
| `Defensive` | `>= 32` and `< 45` |
| `Washout` | `< 32` |

How to read it:
- Higher is better.
- `Expansion` and `Constructive` are favorable for rotation and follow-through.
- `Mixed` means selective opportunity only.
- `Defensive` and `Washout` mean lower-quality tape.

#### Regime signals

| Signal | How it is calculated | How to read it |
| --- | --- | --- |
| `Shanghai+Shenzhen turnover` | Latest SSE + SZSE stock turnover, displayed in CNY trillions, with detail `turnover_ratio` vs the 20-day average. | Above `1.0x` is supportive. Above `1.05x` is clearly expanding. Below `0.95x` is weak. |
| `Northbound net flow` | Current northbound net flow from the Eastmoney summary feed, in CNY `100m`. | Positive is supportive. Negative means foreign flow is not confirming. |
| `Advancers / Decliners` | Daily market activity counts and the derived `A/D` ratio. | More advancers than decliners is good. `A/D > 2.0x` is broad strength. |
| `Real limit-up / real limit-down` | Daily counts of real limit-up and real limit-down names. Detail also shows broken-board count and strong-pool count. | Higher limit-up spread is good. Too many limit-downs or broken boards is a warning. |
| `Industry above 20DMA / 50DMA` | Percent of industry boards above the 20-day and 50-day moving averages. | Higher is better. The 50DMA percentage matters more for durable regime health. |

### Sector breadth

#### Sector breadth headline signals

| Signal | How it is calculated | How to read it |
| --- | --- | --- |
| `Industry Breadth` | `industry_above_20_pct / industry_above_50_pct` | Higher is better. Low values mean leadership is narrow. |
| `Top Industry` | Industry with the highest `leadership_score`, with detail showing `strength_score` and `persistence_score`. | Best when both scores are high, not just one. |
| `Top Concept` | Concept with the highest `heat_score`, using net flow as the tiebreaker. | Higher heat means the concept is attracting broader price and flow leadership. |

#### Industry leaders list

Each row shows:

| Indicator | How it is calculated | How to read it |
| --- | --- | --- |
| `1D` | Today's industry percentage change from THS summary data. | Positive is immediate strength. |
| `5D` | 5-day industry percentage change from THS flow data, or local price-history fallback if missing. | Positive is better; stronger than 1D alone. |
| `Flow` | Today's industry net flow in CNY `100m`. | Positive inflow is better confirmation than price alone. |
| `Up/Down` | Raw counts of advancing and declining stocks in the industry. Internally the model also uses `breadth_ratio = up / (up + down)`. | More advancers than decliners is healthier. |
| `Persistence` chip | From `persistence_score`. Labels: `Persistent` if `>= 80`, `Broadening` if `>= 60`, `Early` if `>= 45`, else `Fragile`. | `Persistent` is best. `Fragile` means the move has poor staying power. |
| `Leadership` chip | From `leadership_score`. Labels: `Institutional` if `>= 78`, `Credible` if `>= 62`, `Watchlist` if `>= 48`, else `Speculative`. | `Institutional` and `Credible` are best. `Speculative` means narrow or low-quality leadership. |
| `Leader` and leader move | The leading stock name and its daily percentage move. | Useful for spotting whether the theme is broad or being driven by one name only. |

Industry score formulas:

```text
strength_score =
(
  rank(change_pct) * 0.22 +
  rank(net_flow_100m) * 0.18 +
  rank(breadth_ratio) * 0.16 +
  rank(change_5d_pct) * 0.14 +
  rank(change_20d_pct) * 0.12 +
  rank(net_flow_5d_100m) * 0.10 +
  rank(net_flow_20d_100m) * 0.08
) / 1.00 * 100
```

```text
persistence_score =
(
  above_20dma * 0.24 +
  above_50dma * 0.24 +
  (positive_days_5 / 5) * 0.18 +
  rank(change_5d_pct) * 0.12 +
  rank(change_20d_pct) * 0.12 +
  I(net_flow_5d_100m > 0) * 0.05 +
  I(net_flow_20d_100m > 0) * 0.05
) * 100
```

```text
confirmation_score =
(
  rank(limit_up_count) * 0.14 +
  rank(strong_pool_count) * 0.16 +
  (1 - rank(broken_board_count)) * 0.14 +
  breadth_ratio * 0.18 +
  above_20dma * 0.19 +
  above_50dma * 0.19
) * 100
```

```text
leadership_score =
  strength_score * 0.45 +
  persistence_score * 0.25 +
  confirmation_score * 0.30
```

How to read the industry scores:
- `strength_score` answers "how strong is the move right now?"
- `persistence_score` answers "how durable is the move?"
- `confirmation_score` answers "is the move being confirmed by broad participation and strong-stock pools?"
- `leadership_score` is the combined quality score used to rank the best industries.

#### Concept flow list

Each row shows:

| Indicator | How it is calculated | How to read it |
| --- | --- | --- |
| `Heat` | `heat_score`, a weighted rank of concept price strength and flow across 1D, 5D, and 20D windows. | Higher is hotter and better supported by both performance and flow. |
| `1D`, `5D`, `20D` | Concept returns from THS concept flow data. | Better when strength persists across more than one window. |
| `Flow` | Today's concept net flow in CNY `100m`. | Positive is better. |
| `Leader` and leader move | Current leading stock in the concept and its daily change. | Helps separate a broad theme from a one-stock spike. |

Concept heat formula:

```text
heat_score =
(
  rank(change_pct) * 0.22 +
  rank(net_flow_100m) * 0.20 +
  rank(change_5d_pct) * 0.18 +
  rank(net_flow_5d_100m) * 0.16 +
  rank(change_20d_pct) * 0.12 +
  rank(net_flow_20d_100m) * 0.12
) * 100
```

### Momentum health

#### Momentum score

Formula:

```text
momentum_score =
(
  scale(real_limit_up, 15, 120) * 0.26 +
  scale(strong_pool_count, 20, 120) * 0.18 +
  scale(prev_limitup_positive_pct, 35, 70) * 0.26 +
  (1 - scale(broken_board_ratio, 0.18, 0.55)) * 0.18 +
  (1 - scale(real_limit_down, 5, 35)) * 0.12
) * 100
```

Labels:

| Label | Threshold |
| --- | --- |
| `Healthy` | `>= 70` |
| `Usable` | `>= 52` and `< 70` |
| `Choppy` | `>= 38` and `< 52` |
| `Fragile` | `< 38` |

How to read it:
- Higher is better.
- `Healthy` means continuation behavior is supportive.
- `Usable` means tactical opportunity exists, but follow-through is less clean.
- `Choppy` and `Fragile` mean breakout quality is weak.

#### Momentum signals

| Signal | How it is calculated | How to read it |
| --- | --- | --- |
| `Real limit-up` | Count of real limit-up names. Detail also shows number of `2+` streaks and the max streak. | Higher is better for momentum appetite. |
| `Limit-down / broken-board` | Real limit-down count and broken-board count. Detail shows `broken_board_ratio = broken / (limit_up + broken)`. | Lower is better. The code marks this signal negative when `broken_board_ratio >= 35%` or `real_limit_down >= 10`. |
| `Strong pool` | Count of names in the strong-stock pool. Detail shows `strong_new_high_pct`, the percent making new highs. | More names and more new highs are better. |
| `Previous limit-up continuation` | `prev_limitup_positive_pct = percent of yesterday's limit-up names still positive today`. | Higher is better. Good continuation means traders are getting paid for holding strength overnight. |

### Leadership quality

#### Best leadership

The best list ranks industries by `leadership_score` and shows:

| Indicator | How it is calculated | How to read it |
| --- | --- | --- |
| `Leadership` chip | Label from `leadership_score`. | `Institutional` and `Credible` are the best quality buckets. |
| `Strength` | `strength_score` rounded to one decimal. | Higher is better. |
| `Persistence` | `persistence_score` rounded to one decimal. | Higher is better. |
| Detail line | Displays flow, breadth, and strong-pool count. | Best when all three confirm each other. |

#### Weak or fake

The fake list ranks positive industries by `fake_score` descending.

Fake flags are added when these conditions fire:

- `day-one pop without inflow`: `change_pct > 0` and `net_flow_100m <= 0`
- `leader-only breadth`: `change_pct > 0` and `breadth_ratio < 0.58`
- `still negative on the 20-day leg`: `change_pct > 0` and `change_20d_pct <= 0`
- `single-stock squeeze`: `leader_change_pct > max(8.0, change_pct * 2)` and `breadth_ratio < 0.65`
- `broken-board pressure`: `broken_board_count > max(1, strong_pool_count)`

Fake-score formula:

```text
fake_score =
(
  rank(change_pct) * 0.26 +
  rank(leader_change_pct) * 0.14 +
  rank(broken_board_count) * 0.20 +
  (1 - rank(breadth_ratio)) * 0.18 +
  (1 - rank(net_flow_5d_100m)) * 0.12 +
  (1 - rank(change_20d_pct)) * 0.10
) * 100
```

How to read it:
- Higher is worse.
- A high `fake_score` means the move looks flashy, but the internal quality is weak.
- This is a warning tool, not a long-entry tool.

## Data caveats shown by the build

- Shanghai + Shenzhen turnover uses exchange summaries, so the 20-day turnover comparison stays internally consistent.
- 20DMA and 50DMA participation in the swing-breadth panel is measured on industry boards, not every individual A-share.
- Northbound flow uses the current Eastmoney net-flow summary feed.
- Industry and concept flow tables come from THS pages through the local AkShare-based parser.
