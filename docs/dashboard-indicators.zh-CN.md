# Dashboard 指标说明

本文档说明仪表盘中各项指标是如何计算的，以及应当如何解读。

范围：
- 覆盖 `data/snapshot.json`、`data/breadth.json` 和 `data/breadth_swing.json` 渲染出来的指标。
- 这里说的“好/坏”，指的是在这个仪表盘的使用场景下是否更适合做收盘后的 ETF 轮动观察，不是通用投资结论。
- 除特别说明外，收益率都是按交易日计算的简单涨跌幅。

## 全局阅读规则

### 排名型分数

很多广度分数不是绝对公式，而是当前样本内的横截面排名。

- `series_rank_pct(x)` 会把当前同一组对象按数值排序，并缩放到 `0-1`。
- 大多数广度分数会再乘以 `100`，因此显示为 `0-100`。
- `strength_score`、`persistence_score`、`confirmation_score`、`leadership_score`、`heat_score`、`regime.score`、`momentum_health.score` 都是越高越好。
- `fake_score` 是越高越差。

### 颜色和背景条

- 表格里的 `1D`、`5D`、`20D` 文本显示的是真实百分比。
- 后面的红绿底条只是在同一个组内，按该列的最小值和最大值归一化后的视觉提示，不是跨组可直接比较的绝对刻度。
- 正负颜色主要来自简单规则：
  - 有符号数值类信号：大于 0 为正向，小于 0 为负向，等于 0 为中性。
  - 分数类信号：通常 `>= 70` 为正向，`<= 40` 为负向，个别分区会使用自己的阈值。

## 顶部总览卡片

| 指标 | 计算方式 | 如何解读 |
| --- | --- | --- |
| `Tone` | 只使用 `Broad` 组。若 Broad 组 `avg_5d > 0` 且 `above_sma50 / count >= 0.5`，则为 `Risk-on`；若 `avg_5d < 0` 且 `above_sma50 / count < 0.5`，则为 `Risk-off`；其余为 `Mixed`。 | `Risk-on` 偏好，说明大盘轮动环境更友好；`Mixed` 表示多空信号冲突；`Risk-off` 表示大盘环境偏弱。 |
| `Strongest` | `avg_rs_21d` 最高的组。 | 越强说明该组相对强势最明显，更值得优先观察。 |
| `Weakest` | `avg_rs_21d` 最低的组。 | 一般应降低优先级，除非你专门做均值回归。 |
| `Breadth` | 对全部 ETF 统计：站上 `EMA20` 的比例，以及站上 `SMA50` 的比例。 | 越高越好。EMA20 看短中期参与度，SMA50 看更扎实的中期趋势。 |

## 组别摘要卡片

每个组卡片会显示：

| 指标 | 计算方式 | 如何解读 |
| --- | --- | --- |
| `RS` | 组内所有 ETF 的 `rs_21d` 平均值。 | 越高说明这一组相对各自基准更强。 |
| `5D` | 组内所有 ETF 的 5 日收益均值。 | 为正说明短波段动能较好，为负说明近期偏弱。 |
| `>EMA20` | 组内最新收盘价高于 EMA20 的 ETF 数量。 | 数量越多，短中期参与越广。 |
| `>SMA50` | 组内最新收盘价高于 SMA50 的 ETF 数量。 | 数量越多，中期趋势结构越健康。 |

## Setup 扫描

| 指标 | 计算方式 | 如何解读 |
| --- | --- | --- |
| `X of Y ETFs currently qualify as good setups` | 统计全体 ETF 中 `good_setup = true` 的数量。 | 被标记的数量越多，说明当前快筛能找到更多可关注对象；如果是 0，表示当前没有品种满足规则。 |
| `Good setup` 标记 | 行数据满足 `Trend setup` 或 `Early rotation` 任一规则时出现。 | 正向筛选结果，但仍需结合图表确认。 |

精确规则如下：

### Trend setup

必须同时满足：

- `grade == A`
- `rs_21d >= 80`
- `group_rank_20d >= 70`
- `amount_z_20d > 0`
- `0 <= atrx50 <= 2`

如何解读：
- 这是最标准的趋势跟随型候选。
- 适合找已经确认的强势领涨。
- 如果 `ATRx50` 再明显高于这个区间，就容易进入过度伸展状态。

### Early rotation

必须同时满足：

- `grade == B`
- `above_ema20 == true`
- `60 <= rs_21d <= 80`
- `group_rank_20d >= 60`
- `amount_z_20d >= 1`
- `-1 <= atrx50 <= 1`

如何解读：
- 比成熟龙头更早。
- 适合找相对强度和成交参与刚开始改善的方向。
- 一旦跌回 EMA20 或量能冲击消失，质量就会下降。

## ETF 表格与右侧图表 Chips

右侧图表区的 chips 复用了表格中的同一批指标，因此下面的定义同时适用于表格和 chips。

| 指标 | 计算方式 | 如何解读 |
| --- | --- | --- |
| `Grade` | 均线排列：若 `EMA10 > EMA20 > SMA50` 则为 `A`；若 `EMA10 < EMA20 < SMA50` 则为 `C`；其余为 `B`。 | `A` 是最干净的上升趋势；`B` 是过渡或混合结构；`C` 是偏弱或下降结构。 |
| `1D` | `(close[t] / close[t-1] - 1) * 100` | 只看最新一天的推动，适合观察当日压力，但噪音也最大。 |
| `5D` | `(close[t] / close[t-5] - 1) * 100` | 最适合看短波段动能。为正更好，明显为负说明近期走弱。 |
| `20D` | `(close[t] / close[t-20] - 1) * 100` | 看月度这段走势。20D 为正的品种，比只靠一两天反弹的品种更健康。 |
| `ATR%` | 先用 14 日 ATR 计算波动，再做 `ATR / 最新收盘价 * 100`。ATR 使用 Wilder 风格 EMA 平滑真实波幅。 | 越高表示单位仓位风险越大，不一定是坏事，但需要更小仓位。 |
| `ATRx50` | `(最新收盘价 - SMA50) / ATR14` | 大致 `0` 到 `+2` 较健康；高于 `+3` 常常偏伸展；低于 `0` 说明仍在 50 日均线下方。 |
| `RS21` | 先计算相对基准 ETF 的波动调整相对强度：`rrs = (asset_change - expected_move) / asset_ATR`，其中 `expected_move = (benchmark_change / benchmark_ATR) * asset_ATR`。然后对 `rrs` 做 50 日滚动均值，再取最近 21 个平滑值里最后一个值的分位数。 | `80-100` 代表强领导，`40-60` 大致中性，`0-20` 代表落后。越高越好。 |
| `Group%` | 当前 ETF 的 `20D` 收益在所属组内的百分位排名。 | 越高说明它在同组里也更强，不只是相对基准更强。 |
| `Amt20` | 最近 20 个交易日成交额均值，再除以 `100,000,000`，单位是“亿元”。 | 越高越有流动性，也更容易产生可信的延续。 |
| `AmtZ` | 最近一天成交额相对最近 20 天的 Z 分数：`(最新成交额 - 20日均值) / 20日标准差`。 | `> 0` 说明参与在放大；`> +1` 说明放量较明显；`< 0` 说明关注度在减弱。 |
| `RS` 小图 | 柱状图是最近 20 个 `rolling_rrs`，橙线是该平滑序列的 20 点均线，虚线为零轴。 | 柱子和橙线都在零轴上方表示相对跑赢；在零轴下方表示相对跑输；柱子抬升且橙线同步上行最好。 |

## Swing Breadth 面板

这个面板是可选的。只有在 `data/breadth_swing.json` 存在，且其 `market_date` 与 ETF 快照日期一致时才会显示。

### Regime

#### Regime score

公式：

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

其中：
- `scale(x, low, high)` 表示把 `(x - low) / (high - low)` 限制在 `0-1`
- `turnover_ratio = 最新成交额 / 20日平均成交额`
- `ad_ratio = 上涨家数 / max(下跌家数, 1)`
- `limit_spread = 真实涨停数 - 真实跌停数`
- `above_20_pct`、`above_50_pct` 为行业板块站上 20 日线和 50 日线的比例

标签阈值：

| 标签 | 阈值 |
| --- | --- |
| `Expansion` | `>= 72` |
| `Constructive` | `>= 58` 且 `< 72` |
| `Mixed` | `>= 45` 且 `< 58` |
| `Defensive` | `>= 32` 且 `< 45` |
| `Washout` | `< 32` |

如何解读：
- 越高越好。
- `Expansion` 和 `Constructive` 更适合做轮动和趋势延续。
- `Mixed` 表示只能精选，不能泛化。
- `Defensive` 和 `Washout` 表示市场环境质量较差。

#### Regime 信号卡

| 信号 | 计算方式 | 如何解读 |
| --- | --- | --- |
| `沪深成交额` | 上交所和深交所股票成交额之和，界面显示为万亿，并给出相对 20 日均值的倍数。 | 高于 `1.0x` 偏支持，高于 `1.05x` 说明明显放量，低于 `0.95x` 偏弱。 |
| `北向净流` | 来自 Eastmoney 汇总接口的当日北向净流入，单位“亿元”。 | 正值更好；负值表示外资并未确认。 |
| `上涨 / 下跌家数` | 市场涨跌家数，以及对应的 `A/D` 比值。 | 上涨明显多于下跌更好；`A/D > 2.0x` 说明广泛走强。 |
| `真实涨停 / 真实跌停` | 当日真实涨停和真实跌停数量；细节里还会显示炸板数和强势池数量。 | 涨停优势越大越好；跌停或炸板太多都要警惕。 |
| `行业站上 20DMA / 50DMA` | 站上 20 日线和 50 日线的行业板块占比。 | 越高越好，其中 50 日线占比对中期环境更重要。 |

### Sector Breadth

#### Sector Breadth 顶部信号

| 信号 | 计算方式 | 如何解读 |
| --- | --- | --- |
| `Industry Breadth` | `industry_above_20_pct / industry_above_50_pct` | 越高越好。数值低说明强势范围很窄。 |
| `Top Industry` | `leadership_score` 最高的行业，细节显示 `strength_score` 与 `persistence_score`。 | 两个分数都高才是真强，不是单日冲高。 |
| `Top Concept` | `heat_score` 最高的概念，若并列则比较净流入。 | Heat 越高，说明题材的价格表现和资金流都更强。 |

#### Industry Leaders 列表

每一行包含：

| 指标 | 计算方式 | 如何解读 |
| --- | --- | --- |
| `1D` | THS 行业汇总中的当日涨跌幅。 | 为正说明当日强。 |
| `5D` | THS 5 日行业涨跌幅；若缺失则回退到本地历史价格计算。 | 为正更好，比单看 1D 更稳。 |
| `Flow` | 当日行业净流入，单位“亿元”。 | 正流入比单纯上涨更可信。 |
| `Up/Down` | 行业内上涨和下跌个股数量。内部还会计算 `breadth_ratio = up / (up + down)`。 | 上涨家数越多越健康。 |
| `Persistence` 标签 | 来自 `persistence_score`。`>= 80` 为 `Persistent`，`>= 60` 为 `Broadening`，`>= 45` 为 `Early`，其余为 `Fragile`。 | `Persistent` 最好；`Fragile` 说明持续性差。 |
| `Leadership` 标签 | 来自 `leadership_score`。`>= 78` 为 `Institutional`，`>= 62` 为 `Credible`，`>= 48` 为 `Watchlist`，其余为 `Speculative`。 | `Institutional` 和 `Credible` 最值得重视；`Speculative` 往往偏窄、质量偏低。 |
| `Leader` 与涨幅 | 当前行业龙头股及其当日涨幅。 | 用来判断是板块共振，还是只是个股拉动。 |

行业分数公式：

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

如何解读这些行业分数：
- `strength_score` 回答的是“现在强不强”。
- `persistence_score` 回答的是“这种强势能不能持续”。
- `confirmation_score` 回答的是“有没有被更广泛的参与和强势股池确认”。
- `leadership_score` 是综合质量分，用来给最佳行业排序。

#### Concept Flow 列表

每一行包含：

| 指标 | 计算方式 | 如何解读 |
| --- | --- | --- |
| `Heat` | `heat_score`，对概念 1D、5D、20D 的涨幅和资金流做加权排名。 | 越高越热，说明价格和资金都在支持这个概念。 |
| `1D`、`5D`、`20D` | THS 概念数据里的不同周期涨跌幅。 | 多个周期同时强，比只强一天更好。 |
| `Flow` | 当日概念净流入，单位“亿元”。 | 为正更好。 |
| `Leader` 与涨幅 | 当前概念龙头股及其日涨幅。 | 用来判断题材是否只是单一龙头带动。 |

概念 Heat 公式：

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

### Momentum Health

#### Momentum score

公式：

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

标签阈值：

| 标签 | 阈值 |
| --- | --- |
| `Healthy` | `>= 70` |
| `Usable` | `>= 52` 且 `< 70` |
| `Choppy` | `>= 38` 且 `< 52` |
| `Fragile` | `< 38` |

如何解读：
- 越高越好。
- `Healthy` 说明连板/强势延续环境较好。
- `Usable` 说明还有战术机会，但延续性不够干净。
- `Choppy` 和 `Fragile` 说明突破质量较差。

#### Momentum 信号卡

| 信号 | 计算方式 | 如何解读 |
| --- | --- | --- |
| `真实涨停` | 真实涨停家数；细节中还会显示 `2+` 连板数量和最高连板数。 | 越多越好，表示短线风险偏好更高。 |
| `跌停 / 炸板` | 真实跌停数和炸板数；细节中显示 `broken_board_ratio = 炸板 / (涨停 + 炸板)`。 | 越低越好。代码中当 `broken_board_ratio >= 35%` 或 `real_limit_down >= 10` 时会把该信号标成负向。 |
| `强势股池` | 强势池数量；细节里显示 `strong_new_high_pct`，即其中创新高的比例。 | 数量越多且创新高比例越高越好。 |
| `昨日涨停延续` | `prev_limitup_positive_pct = 昨日涨停股中，今天仍然收红的比例`。 | 越高越好，表示隔日持有强势股更容易得到回报。 |

### Leadership Quality

#### Best Leadership

最佳领导列表按 `leadership_score` 排序，显示：

| 指标 | 计算方式 | 如何解读 |
| --- | --- | --- |
| `Leadership` 标签 | 来自 `leadership_score` 的标签。 | `Institutional` 和 `Credible` 是最好的质量层级。 |
| `Strength` | `strength_score`，保留 1 位小数。 | 越高越好。 |
| `Persistence` | `persistence_score`，保留 1 位小数。 | 越高越好。 |
| 细节行 | 显示资金流、广度、强势池数量。 | 三者同时确认时质量最高。 |

#### Weak or Fake

这个列表会从当天上涨的行业里，按 `fake_score` 从高到低排序。

触发假强风险标记的条件：

- `day-one pop without inflow`：`change_pct > 0` 且 `net_flow_100m <= 0`
- `leader-only breadth`：`change_pct > 0` 且 `breadth_ratio < 0.58`
- `still negative on the 20-day leg`：`change_pct > 0` 且 `change_20d_pct <= 0`
- `single-stock squeeze`：`leader_change_pct > max(8.0, change_pct * 2)` 且 `breadth_ratio < 0.65`
- `broken-board pressure`：`broken_board_count > max(1, strong_pool_count)`

Fake 分数公式：

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

如何解读：
- 越高越差。
- `fake_score` 高，说明表面上看起来很强，但内部结构并不扎实。
- 这是一个风险提示工具，不是做多信号。

## 构建脚本里的数据备注

- 沪深成交额来自交易所汇总，因此和 20 日均值的对比在口径上是一致的。
- Swing Breadth 面板里的 20DMA / 50DMA 参与率是按行业板块统计，不是按全部 A 股逐只统计。
- 北向资金使用的是 Eastmoney 当前净流入汇总接口。
- 行业和概念资金流来自 THS 页面，经本地 AkShare 解析流程整理。
