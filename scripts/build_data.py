from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from functools import lru_cache
from io import StringIO
from pathlib import Path
from typing import Dict, List
from zoneinfo import ZoneInfo

import akshare as ak
import matplotlib
import pandas as pd
from akshare.stock_feature import stock_fund_flow as ak_ths_fund_flow

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "china_etf_universe.json"
CHINA_TZ = ZoneInfo("Asia/Shanghai")
AFTER_CLOSE_READY_TIME = time(15, 45)
THS_LEVEL1_BY_LEVEL2 = {
    "半导体": "电子",
    "元件": "电子",
    "消费电子": "电子",
    "其他电子": "电子",
    "光学光电子": "电子",
    "电子化学品": "电子",
    "通信设备": "通信",
    "通信服务": "通信",
    "计算机设备": "计算机",
    "软件开发": "计算机",
    "IT服务": "计算机",
    "电池": "电力设备",
    "风电设备": "电力设备",
    "光伏设备": "电力设备",
    "电网设备": "电力设备",
    "其他电源设备": "电力设备",
    "电机": "电力设备",
    "汽车整车": "汽车",
    "汽车零部件": "汽车",
    "汽车服务及其他": "汽车",
    "通用设备": "机械设备",
    "专用设备": "机械设备",
    "自动化设备": "机械设备",
    "工程机械": "机械设备",
    "轨交设备": "机械设备",
    "军工电子": "国防军工",
    "军工装备": "国防军工",
    "化学原料": "基础化工",
    "化学制品": "基础化工",
    "化学纤维": "基础化工",
    "塑料制品": "基础化工",
    "橡胶制品": "基础化工",
    "农化制品": "基础化工",
    "非金属材料": "基础化工",
    "金属新材料": "有色金属",
    "工业金属": "有色金属",
    "能源金属": "有色金属",
    "小金属": "有色金属",
    "贵金属": "有色金属",
    "钢铁": "黑色金属",
    "煤炭开采加工": "煤炭",
    "石油加工贸易": "石油石化",
    "油气开采及服务": "石油石化",
    "电力": "公用事业",
    "燃气": "公用事业",
    "环保设备": "环保",
    "环境治理": "环保",
    "白色家电": "家用电器",
    "黑色家电": "家用电器",
    "小家电": "家用电器",
    "厨卫电器": "家用电器",
    "食品加工制造": "食品饮料",
    "饮料制造": "食品饮料",
    "白酒": "食品饮料",
    "纺织制造": "纺织服装",
    "服装家纺": "纺织服装",
    "包装印刷": "轻工制造",
    "造纸": "轻工制造",
    "家居用品": "轻工制造",
    "建筑材料": "建筑材料",
    "建筑装饰": "建筑装饰",
    "房地产": "房地产",
    "银行": "银行",
    "证券": "非银金融",
    "保险": "非银金融",
    "多元金融": "非银金融",
    "医疗器械": "医药生物",
    "生物制品": "医药生物",
    "化学制药": "医药生物",
    "中药": "医药生物",
    "医药商业": "医药生物",
    "医疗服务": "医药生物",
    "美容护理": "美容护理",
    "零售": "商贸零售",
    "互联网电商": "商贸零售",
    "贸易": "商贸零售",
    "农产品加工": "农林牧渔",
    "种植业与林业": "农林牧渔",
    "养殖业": "农林牧渔",
    "港口航运": "交通运输",
    "机场航运": "交通运输",
    "公路铁路运输": "交通运输",
    "物流": "交通运输",
    "文化传媒": "传媒",
    "影视院线": "传媒",
    "游戏": "传媒",
    "教育": "社会服务",
    "旅游及酒店": "社会服务",
    "其他社会服务": "社会服务",
    "综合": "综合",
}


def load_universe() -> Dict[str, object]:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def previous_weekday(day):
    candidate = day - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def expected_market_date(now: datetime | None = None) -> str:
    current = now or datetime.now(CHINA_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=CHINA_TZ)
    else:
        current = current.astimezone(CHINA_TZ)

    day = current.date()
    if day.weekday() == 5:
        return (day - timedelta(days=1)).isoformat()
    if day.weekday() == 6:
        return (day - timedelta(days=2)).isoformat()
    if current.time() >= AFTER_CLOSE_READY_TIME:
        return day.isoformat()
    return previous_weekday(day).isoformat()


def assert_fresh_market_date(market_date: str, allow_stale: bool = False, now: datetime | None = None) -> None:
    expected = expected_market_date(now)
    if market_date >= expected or allow_stale:
        return
    raise RuntimeError(
        f"Generated ETF snapshot is stale: market_date={market_date}, expected={expected}. "
        "The upstream ETF history source has not published the latest China session yet; "
        "skip this commit and let the next scheduled retry run."
    )


def provider_symbol(exchange: str, code: str) -> str:
    if exchange == "SSE":
        return f"sh{code}"
    if exchange == "SZSE":
        return f"sz{code}"
    raise ValueError(f"Unsupported exchange: {exchange}")


def tradingview_symbol(exchange: str, code: str) -> str:
    return f"{exchange}:{code}"


def fetch_history(exchange: str, code: str, cache: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    cache_key = f"{exchange}:{code}"
    if cache_key in cache:
        return cache[cache_key].copy()

    history = ak.fund_etf_hist_sina(symbol=provider_symbol(exchange, code))
    if history.empty:
        raise ValueError(f"No history returned for {exchange}:{code}")

    normalized = history.copy()
    normalized["date"] = pd.to_datetime(normalized["date"])
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized = normalized.dropna(subset=["date", "open", "high", "low", "close", "volume", "amount"])
    normalized = normalized.sort_values("date").drop_duplicates(subset="date").tail(260).reset_index(drop=True)
    if len(normalized) < 60:
        raise ValueError(f"Insufficient history for {exchange}:{code}")

    cache[cache_key] = normalized
    return normalized.copy()


def calculate_atr(history: pd.DataFrame, period: int = 14) -> float:
    true_range = pd.concat(
        [
            history["high"] - history["low"],
            (history["high"] - history["close"].shift(1)).abs(),
            (history["low"] - history["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return float(true_range.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


def calculate_grade(history: pd.DataFrame) -> str:
    ema10 = history["close"].ewm(span=10, adjust=False).mean().iloc[-1]
    ema20 = history["close"].ewm(span=20, adjust=False).mean().iloc[-1]
    sma50 = history["close"].rolling(window=50).mean().iloc[-1]
    if ema10 > ema20 and ema20 > sma50:
        return "A"
    if ema10 < ema20 and ema20 < sma50:
        return "C"
    return "B"


def calculate_relative_strength(asset_history: pd.DataFrame, benchmark_history: pd.DataFrame) -> pd.DataFrame:
    merged = asset_history[["date", "high", "low", "close"]].merge(
        benchmark_history[["date", "high", "low", "close"]],
        on="date",
        suffixes=("_asset", "_bench"),
        how="inner",
    )
    if len(merged) < 30:
        raise ValueError("Not enough overlapping sessions for relative-strength calculation")

    for suffix in ["asset", "bench"]:
        true_range = pd.concat(
            [
                merged[f"high_{suffix}"] - merged[f"low_{suffix}"],
                (merged[f"high_{suffix}"] - merged[f"close_{suffix}"].shift(1)).abs(),
                (merged[f"low_{suffix}"] - merged[f"close_{suffix}"].shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)
        merged[f"atr_{suffix}"] = true_range.ewm(alpha=1 / 14, adjust=False).mean()

    asset_change = merged["close_asset"] - merged["close_asset"].shift(1)
    benchmark_change = merged["close_bench"] - merged["close_bench"].shift(1)
    benchmark_pressure = benchmark_change / merged["atr_bench"]
    expected_move = benchmark_pressure * merged["atr_asset"]

    merged["rrs"] = (asset_change - expected_move) / merged["atr_asset"]
    merged["rolling_rrs"] = merged["rrs"].rolling(window=50, min_periods=5).mean()
    merged["signal"] = merged["rolling_rrs"].rolling(window=20, min_periods=3).mean()
    return merged[["date", "rrs", "rolling_rrs", "signal"]].dropna(subset=["rolling_rrs"]).reset_index(drop=True)


def percentile_of_last(series: pd.Series) -> float:
    recent = series.dropna().tail(21)
    if recent.empty or len(recent) == 1:
        return 50.0
    ranks = recent.rank(method="average")
    return float(((ranks.iloc[-1] - 1) / (len(recent) - 1)) * 100)


def zscore_of_last(series: pd.Series) -> float:
    recent = series.dropna().tail(20)
    if recent.empty:
        return 0.0
    std = float(recent.std(ddof=0))
    if std == 0:
        return 0.0
    return float((recent.iloc[-1] - recent.mean()) / std)


def create_rs_chart(rs_frame: pd.DataFrame, code: str, charts_dir: Path) -> str:
    recent = rs_frame.tail(20)
    if recent.empty:
        raise ValueError(f"Relative-strength chart is empty for {code}")

    fig, axis = plt.subplots(figsize=(4.2, 1.2))
    fig.patch.set_facecolor("#08111f")
    axis.set_facecolor("#08111f")

    bars = recent["rolling_rrs"]
    signal = recent["signal"]
    strongest_index = int(bars.argmax())
    colors = ["#38bdf8" if idx == strongest_index else "#475569" for idx in range(len(bars))]

    axis.bar(range(len(bars)), bars, color=colors, width=0.82)
    axis.plot(range(len(signal)), signal, color="#f59e0b", linewidth=1.8)
    axis.axhline(y=0, color="#64748b", linestyle="--", linewidth=0.9)
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_visible(False)

    fig.tight_layout(pad=0.1)
    output_path = charts_dir / f"{code}.png"
    fig.savefig(output_path, dpi=110, bbox_inches="tight", facecolor="#08111f")
    plt.close(fig)
    return f"data/charts/{code}.png"


def build_row(
    item: Dict[str, str],
    benchmark_name: str,
    history_cache: Dict[str, pd.DataFrame],
    charts_dir: Path,
) -> Dict[str, object]:
    history = fetch_history(item["exchange"], item["code"], history_cache)
    benchmark_history = fetch_history(item["benchmark_exchange"], item["benchmark_code"], history_cache)

    close = history["close"]
    amount = history["amount"]
    ema20 = history["close"].ewm(span=20, adjust=False).mean().iloc[-1]
    sma50 = history["close"].rolling(window=50).mean().iloc[-1]
    atr = calculate_atr(history)
    rs_frame = calculate_relative_strength(history, benchmark_history)

    return {
        "code": item["code"],
        "label": item["label"],
        "name": item["name"],
        "group": item["group"],
        "exchange": item["exchange"],
        "chart_symbol": tradingview_symbol(item["exchange"], item["code"]),
        "benchmark_code": item["benchmark_code"],
        "benchmark_name": benchmark_name,
        "benchmark_chart_symbol": tradingview_symbol(item["benchmark_exchange"], item["benchmark_code"]),
        "market_date": history.iloc[-1]["date"].date().isoformat(),
        "daily": round((close.iloc[-1] / close.iloc[-2] - 1) * 100, 2),
        "5d": round((close.iloc[-1] / close.iloc[-6] - 1) * 100, 2),
        "20d": round((close.iloc[-1] / close.iloc[-21] - 1) * 100, 2),
        "atr_pct": round((atr / close.iloc[-1]) * 100, 2),
        "atrx50": round((close.iloc[-1] - sma50) / atr, 2),
        "rs_21d": round(percentile_of_last(rs_frame["rolling_rrs"]), 0),
        "amount_20d_avg": round(amount.tail(20).mean() / 100000000, 1),
        "amount_z_20d": round(zscore_of_last(amount), 2),
        "grade": calculate_grade(history),
        "above_ema20": bool(close.iloc[-1] > ema20),
        "above_sma50": bool(close.iloc[-1] > sma50),
        "rs_chart": create_rs_chart(rs_frame, item["code"], charts_dir),
        "good_setup": False,
        "good_setup_reason": None,
    }


def assign_group_ranks(rows: List[Dict[str, object]]) -> None:
    if not rows:
        return
    if len(rows) == 1:
        rows[0]["group_rank_20d"] = 50.0
        return

    values = pd.Series([row["20d"] for row in rows], index=range(len(rows)))
    ranks = values.rank(method="average")
    for index, row in enumerate(rows):
        row["group_rank_20d"] = round(((ranks.iloc[index] - 1) / (len(rows) - 1)) * 100, 0)


def assign_good_setups(rows: List[Dict[str, object]]) -> None:
    for row in rows:
        trend_setup = (
            row["grade"] == "A"
            and row["rs_21d"] >= 80
            and row["group_rank_20d"] >= 70
            and row["amount_z_20d"] > 0
            and 0 <= row["atrx50"] <= 2
        )
        early_rotation = (
            row["grade"] == "B"
            and row["above_ema20"]
            and 60 <= row["rs_21d"] <= 80
            and row["group_rank_20d"] >= 60
            and row["amount_z_20d"] >= 1
            and -1 <= row["atrx50"] <= 1
        )

        row["good_setup"] = bool(trend_setup or early_rotation)
        if trend_setup:
            row["good_setup_reason"] = "Trend setup"
        elif early_rotation:
            row["good_setup_reason"] = "Early rotation"
        else:
            row["good_setup_reason"] = None


def build_breadth(groups: Dict[str, List[Dict[str, object]]], group_order: List[str], built_at: str) -> Dict[str, object]:
    summaries = []
    all_rows = [row for rows in groups.values() for row in rows]

    for group_name in group_order:
        rows = groups[group_name]
        if not rows:
            continue
        strongest = sorted(rows, key=lambda row: row["rs_21d"], reverse=True)
        weakest = sorted(rows, key=lambda row: row["rs_21d"])
        summaries.append(
            {
                "group": group_name,
                "count": len(rows),
                "avg_daily": round(sum(row["daily"] for row in rows) / len(rows), 2),
                "avg_5d": round(sum(row["5d"] for row in rows) / len(rows), 2),
                "avg_20d": round(sum(row["20d"] for row in rows) / len(rows), 2),
                "avg_rs_21d": round(sum(row["rs_21d"] for row in rows) / len(rows), 0),
                "above_ema20": sum(1 for row in rows if row["above_ema20"]),
                "above_sma50": sum(1 for row in rows if row["above_sma50"]),
                "leaders": [{"code": row["code"], "label": row["label"], "rs_21d": row["rs_21d"]} for row in strongest[:3]],
                "laggards": [{"code": row["code"], "label": row["label"], "rs_21d": row["rs_21d"]} for row in weakest[:3]],
            }
        )

    broad_rows = groups.get("Broad", [])
    broad_average = sum(row["5d"] for row in broad_rows) / len(broad_rows)
    broad_participation = sum(1 for row in broad_rows if row["above_sma50"]) / len(broad_rows)
    if broad_average > 0 and broad_participation >= 0.5:
        market_tone = "Risk-on"
    elif broad_average < 0 and broad_participation < 0.5:
        market_tone = "Risk-off"
    else:
        market_tone = "Mixed"

    strongest_group = max(summaries, key=lambda summary: summary["avg_rs_21d"])
    weakest_group = min(summaries, key=lambda summary: summary["avg_rs_21d"])

    return {
        "built_at": built_at,
        "groups": summaries,
        "overview": {
            "market_tone": market_tone,
            "strongest_group": strongest_group["group"],
            "weakest_group": weakest_group["group"],
            "above_ema20_pct": round(sum(1 for row in all_rows if row["above_ema20"]) / len(all_rows) * 100, 0),
            "above_sma50_pct": round(sum(1 for row in all_rows if row["above_sma50"]) / len(all_rows) * 100, 0),
        },
    }


def parse_number(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        normalized = value.strip().replace(",", "")
        if not normalized:
            return None
        if normalized.endswith("%"):
            normalized = normalized[:-1]
        try:
            return float(normalized)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def scale_unit_interval(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.5
    return max(0.0, min(1.0, (value - low) / (high - low)))


def series_rank_pct(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    ranked = pd.Series(0.5, index=numeric.index, dtype=float)
    if valid.empty or len(valid) == 1:
        return ranked
    ranks = valid.rank(method="average")
    ranked.loc[valid.index] = (ranks - 1) / (len(valid) - 1)
    return ranked


def tone_from_score(score: float, strong: float = 70, weak: float = 40) -> str:
    if score >= strong:
        return "positive"
    if score <= weak:
        return "negative"
    return "neutral"


def tone_from_signed(value: float, positive_floor: float = 0.0, negative_floor: float = 0.0) -> str:
    if value > positive_floor:
        return "positive"
    if value < negative_floor:
        return "negative"
    return "neutral"


def format_money_100m(value: float) -> str:
    if abs(value) >= 10000:
        return f"{value / 10000:.2f}万亿"
    return f"{value:.0f}亿"


def format_turnover_trillion(value: float) -> str:
    return f"{value:.2f}万亿"


def normalize_sector_name(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", "", text)
    text = text.translate(str.maketrans("", "", "ⅠⅡⅢⅣⅤ()（）"))
    return text


def rolling_return(series: pd.Series, lookback: int) -> float:
    cleaned = pd.to_numeric(series, errors="coerce").dropna().reset_index(drop=True)
    if len(cleaned) <= lookback:
        return 0.0
    return float((cleaned.iloc[-1] / cleaned.iloc[-lookback - 1] - 1) * 100)


def positive_day_count(series: pd.Series, lookback: int) -> int:
    changes = pd.to_numeric(series, errors="coerce").pct_change().dropna().tail(lookback)
    return int((changes > 0).sum())


def first_valid(values: pd.Series, default: float = 0.0) -> float:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return default
    return float(numeric.iloc[0])


def parse_trade_date(value: object) -> str | None:
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def ensure_trade_date(source: str, actual_date: str | None, expected_date: str) -> None:
    if actual_date is None:
        raise ValueError(f"{source} trade date is missing")
    if actual_date != expected_date:
        raise ValueError(f"{source} trade date {actual_date} does not match snapshot market date {expected_date}")


def fetch_market_activity() -> Dict[str, object]:
    frame = ak.stock_market_activity_legu()
    activity: Dict[str, object] = {}
    for _, row in frame.iterrows():
        key = str(row["item"]).strip()
        parsed = parse_number(row["value"])
        activity[key] = parsed if parsed is not None else str(row["value"]).strip()
    trade_date = parse_trade_date(activity.get("统计日期"))
    if trade_date is None:
        raise ValueError("Market activity date is missing")
    activity["trade_date"] = trade_date
    return activity


def fetch_northbound_summary() -> Dict[str, object]:
    frame = ak.stock_hsgt_fund_flow_summary_em()
    north = frame[frame["资金方向"] == "北向"].copy()
    if north.empty:
        raise ValueError("Northbound summary is empty")
    latest_trade_date = north["交易日"].max()
    if pd.isna(latest_trade_date):
        raise ValueError("Northbound trade date is missing")
    north = north[north["交易日"] == latest_trade_date].copy()
    return {
        "trade_date": latest_trade_date.isoformat(),
        "net_flow_100m": round(float(north["资金净流入"].sum()), 2),
        "up_count": int(north["上涨数"].sum()),
        "flat_count": int(north["持平数"].sum()),
        "down_count": int(north["下跌数"].sum()),
        "sh_index_change_pct": round(first_valid(north.loc[north["板块"] == "沪股通", "指数涨跌幅"]), 2),
        "sz_index_change_pct": round(first_valid(north.loc[north["板块"] == "深股通", "指数涨跌幅"]), 2),
    }


@lru_cache(maxsize=64)
def fetch_sse_stock_turnover(date: str) -> float:
    frame = ak.stock_sse_deal_daily(date=date)
    row = frame.loc[frame["单日情况"] == "成交金额", "股票"]
    if row.empty:
        raise ValueError(f"Missing SSE turnover for {date}")
    value = parse_number(row.iloc[0])
    if value is None:
        raise ValueError(f"Invalid SSE turnover for {date}")
    return value * 100000000


@lru_cache(maxsize=64)
def fetch_szse_stock_turnover(date: str) -> float:
    frame = ak.stock_szse_summary(date=date)
    row = frame.loc[frame["证券类别"] == "股票", "成交金额"]
    if row.empty:
        raise ValueError(f"Missing SZSE turnover for {date}")
    value = parse_number(row.iloc[0])
    if value is None:
        raise ValueError(f"Invalid SZSE turnover for {date}")
    return value


def build_turnover_series(trading_dates: List[pd.Timestamp]) -> List[Dict[str, object]]:
    series = []
    for date in trading_dates:
        date_str = date.strftime("%Y%m%d")
        total = fetch_sse_stock_turnover(date_str) + fetch_szse_stock_turnover(date_str)
        series.append({"date": date.date().isoformat(), "turnover": total})
    return series


def ths_hexin_v() -> str:
    js = ak_ths_fund_flow.py_mini_racer.MiniRacer()
    js.eval(ak_ths_fund_flow._get_file_content_ths("ths.js"))
    return js.call("v")


def fetch_ths_fund_flow(kind: str, window: str) -> pd.DataFrame:
    if kind not in {"industry", "concept"}:
        raise ValueError(f"Unsupported THS flow kind: {kind}")
    if window not in {"today", "5d", "20d"}:
        raise ValueError(f"Unsupported THS flow window: {window}")

    path = "hyzjl" if kind == "industry" else "gnzjl"
    referer = f"http://data.10jqka.com.cn/funds/{path}/"
    board_segment = "" if window == "today" else f"board/{window[:-1]}/"
    first_url = f"http://data.10jqka.com.cn/funds/{path}/{board_segment}field/tradezdf/order/desc/ajax/1/free/1/"
    page_url = f"http://data.10jqka.com.cn/funds/{path}/{board_segment}field/tradezdf/order/desc/page/{{}}/ajax/1/free/1/"
    def request(url: str):
        headers = {
            "Accept": "text/html, */*; q=0.01",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "hexin-v": ths_hexin_v(),
            "Host": "data.10jqka.com.cn",
            "Pragma": "no-cache",
            "Referer": referer,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        return ak_ths_fund_flow.requests.get(url, headers=headers)

    response = request(first_url)
    tables = [pd.read_html(StringIO(response.text))[0]]
    soup = ak_ths_fund_flow.BeautifulSoup(response.text, features="lxml")
    page_info = soup.find(name="span", attrs={"class": "page_info"})
    page_count = int(page_info.text.split("/")[1]) if page_info else 1

    for page in range(2, page_count + 1):
        response = request(page_url.format(page))
        tables.append(pd.read_html(StringIO(response.text))[0])

    frame = pd.concat(tables, ignore_index=True)
    if window == "today":
        if frame.shape[1] != 11:
            raise ValueError(f"Unexpected THS today flow shape: {frame.shape}")
        frame.columns = [
            "rank",
            "name",
            "index_value",
            "change_pct",
            "inflow_100m",
            "outflow_100m",
            "net_flow_100m",
            "company_count",
            "leader",
            "leader_change_pct",
            "leader_last_price",
        ]
        for column in ["change_pct", "leader_change_pct"]:
            frame[column] = frame[column].astype(str).str.rstrip("%")
        numeric_columns = [
            "rank",
            "index_value",
            "change_pct",
            "inflow_100m",
            "outflow_100m",
            "net_flow_100m",
            "company_count",
            "leader_change_pct",
            "leader_last_price",
        ]
    else:
        if frame.shape[1] != 8:
            raise ValueError(f"Unexpected THS ranked flow shape: {frame.shape}")
        frame.columns = [
            "rank",
            "name",
            "company_count",
            "index_value",
            "period_change_pct",
            "inflow_100m",
            "outflow_100m",
            "net_flow_100m",
        ]
        frame["period_change_pct"] = frame["period_change_pct"].astype(str).str.rstrip("%")
        numeric_columns = [
            "rank",
            "company_count",
            "index_value",
            "period_change_pct",
            "inflow_100m",
            "outflow_100m",
            "net_flow_100m",
        ]

    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def fetch_industry_summary_ths() -> pd.DataFrame:
    def request(page: int):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Cookie": f"v={ths_hexin_v()}",
        }
        url = f"http://q.10jqka.com.cn/thshy/index/field/199112/order/desc/page/{page}/ajax/1/"
        return ak_ths_fund_flow.requests.get(url, headers=headers)

    response = request(1)
    tables = [pd.read_html(StringIO(response.text))[0]]
    soup = ak_ths_fund_flow.BeautifulSoup(response.text, features="lxml")
    page_info = soup.find(name="span", attrs={"class": "page_info"})
    page_count = int(page_info.text.split("/")[1]) if page_info else 1

    for page in range(2, page_count + 1):
        response = request(page)
        tables.append(pd.read_html(StringIO(response.text))[0])

    frame = pd.concat(tables, ignore_index=True)
    frame.columns = [
        "序号",
        "板块",
        "涨跌幅",
        "总成交量",
        "总成交额",
        "净流入",
        "上涨家数",
        "下跌家数",
        "均价",
        "领涨股",
        "领涨股-最新价",
        "领涨股-涨跌幅",
    ]
    for column in ["涨跌幅", "总成交量", "总成交额", "净流入", "上涨家数", "下跌家数", "均价", "领涨股-最新价", "领涨股-涨跌幅"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


@lru_cache(maxsize=256)
def fetch_industry_index_history(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    return ak.stock_board_industry_index_ths(symbol=symbol, start_date=start_date, end_date=end_date)


def build_industry_pool_counts(frame: pd.DataFrame) -> Counter:
    counts: Counter = Counter()
    if "所属行业" not in frame.columns:
        return counts
    for name in frame["所属行业"].dropna():
        counts[normalize_sector_name(name)] += 1
    return counts


def describe_persistence(score: float) -> str:
    if score >= 80:
        return "Persistent"
    if score >= 60:
        return "Broadening"
    if score >= 45:
        return "Early"
    return "Fragile"


def describe_leadership(score: float) -> str:
    if score >= 78:
        return "Institutional"
    if score >= 62:
        return "Credible"
    if score >= 48:
        return "Watchlist"
    return "Speculative"


def describe_fake_risk(flags: List[str]) -> str:
    return "; ".join(flags[:3]) if flags else "Narrow leadership"


def ths_watch_status(score: float, *, extended: bool = False, weak: bool = False) -> str:
    if weak:
        return "Avoid"
    if score >= 72:
        return "Watch on pullback" if extended else "Watch"
    if score >= 56:
        return "Wait"
    return "Avoid"


def normalize_ths_index_history(history: pd.DataFrame) -> pd.DataFrame:
    if history.shape[1] < 7:
        raise ValueError(f"Unexpected THS index history shape: {history.shape}")
    normalized = pd.DataFrame(
        {
            "date": pd.to_datetime(history.iloc[:, 0]),
            "open": pd.to_numeric(history.iloc[:, 1], errors="coerce"),
            "high": pd.to_numeric(history.iloc[:, 2], errors="coerce"),
            "low": pd.to_numeric(history.iloc[:, 3], errors="coerce"),
            "close": pd.to_numeric(history.iloc[:, 4], errors="coerce"),
            "volume": pd.to_numeric(history.iloc[:, 5], errors="coerce"),
            "amount": pd.to_numeric(history.iloc[:, 6], errors="coerce"),
        }
    )
    normalized = normalized.dropna(subset=["date", "open", "high", "low", "close", "volume", "amount"])
    normalized = normalized.sort_values("date").drop_duplicates(subset="date").reset_index(drop=True)
    if len(normalized) < 60:
        raise ValueError("Insufficient THS index history for ETF-style metrics")
    return normalized


def assign_percentile_rank(
    frame: pd.DataFrame,
    source_column: str,
    output_column: str,
    group_column: str | None = None,
) -> None:
    frame[output_column] = 50.0
    grouped = [(None, frame)] if group_column is None else frame.groupby(group_column, sort=False)
    for _, group in grouped:
        valid = pd.to_numeric(group[source_column], errors="coerce").dropna()
        if len(valid) <= 1:
            frame.loc[group.index, output_column] = 50.0
            continue
        ranks = valid.rank(method="average")
        frame.loc[valid.index, output_column] = ((ranks - 1) / (len(valid) - 1) * 100).round(0)


def weighted_average(group: pd.DataFrame, column: str, weight_column: str = "company_count") -> float:
    values = pd.to_numeric(group[column], errors="coerce")
    weights = pd.to_numeric(group[weight_column], errors="coerce").fillna(1).clip(lower=1)
    valid = values.notna()
    if not valid.any():
        return 0.0
    return float((values[valid] * weights[valid]).sum() / weights[valid].sum())


def aggregate_grade(group: pd.DataFrame) -> str:
    grade_scores = group["grade"].map({"A": 2.0, "B": 1.0, "C": 0.0}).fillna(1.0)
    weights = pd.to_numeric(group["company_count"], errors="coerce").fillna(1).clip(lower=1)
    score = float((grade_scores * weights).sum() / weights.sum())
    if score >= 1.45:
        return "A"
    if score <= 0.55:
        return "C"
    return "B"


def etf_style_setup_reason(row: pd.Series | Dict[str, object]) -> str | None:
    grade = str(row.get("grade", ""))
    rs_21d = float(row.get("rs_21d", 0) or 0)
    group_rank = float(row.get("group_rank_20d", 0) or 0)
    amount_z = float(row.get("amount_z_20d", 0) or 0)
    atrx50 = float(row.get("atrx50", 0) or 0)
    above_ema20 = bool(row.get("above_ema20", False))

    trend_setup = grade == "A" and rs_21d >= 80 and group_rank >= 70 and amount_z > 0 and 0 <= atrx50 <= 2
    early_rotation = grade == "B" and above_ema20 and 60 <= rs_21d <= 80 and group_rank >= 60 and amount_z >= 1 and -1 <= atrx50 <= 1
    if trend_setup:
        return "Trend setup"
    if early_rotation:
        return "Early rotation"
    return None


def industry_metric_payload(row: pd.Series | Dict[str, object]) -> Dict[str, object]:
    reason = row.get("good_setup_reason")
    if reason is None or pd.isna(reason) or reason == "":
        reason = etf_style_setup_reason(row)
    return {
        "daily": round(float(row.get("daily", 0) or 0), 2),
        "5d": round(float(row.get("5d", row.get("change_5d_pct", 0)) or 0), 2),
        "20d": round(float(row.get("20d", row.get("change_20d_pct", 0)) or 0), 2),
        "atr_pct": round(float(row.get("atr_pct", 0) or 0), 2),
        "atrx50": round(float(row.get("atrx50", 0) or 0), 2),
        "rs_21d": round(float(row.get("rs_21d", 50) or 50), 0),
        "group_rank_20d": round(float(row.get("group_rank_20d", 50) or 50), 0),
        "amount_20d_avg": round(float(row.get("amount_20d_avg", 0) or 0), 1),
        "amount_z_20d": round(float(row.get("amount_z_20d", 0) or 0), 2),
        "grade": str(row.get("grade", "B") or "B"),
        "good_setup": bool(reason),
        "good_setup_reason": reason,
    }


def build_ths_industry_watchlist(industry_frame: pd.DataFrame) -> Dict[str, object]:
    watch_frame = industry_frame.copy()
    watch_frame["level1"] = watch_frame["name"].map(THS_LEVEL1_BY_LEVEL2).fillna("未分组")
    assign_percentile_rank(watch_frame, "20d", "group_rank_20d", "level1")
    watch_frame["good_setup_reason"] = watch_frame.apply(etf_style_setup_reason, axis=1)
    watch_frame["good_setup"] = watch_frame["good_setup_reason"].notna()
    watch_frame["watch_score"] = (
        watch_frame["strength_score"] * 0.42
        + watch_frame["persistence_score"] * 0.26
        + watch_frame["confirmation_score"] * 0.32
    ).round(1)
    watch_frame["extended"] = (watch_frame["change_5d_pct"] >= 8.0) | (watch_frame["amount_ratio_20d"] >= 1.8)
    watch_frame["weak"] = (~watch_frame["above_20dma"].astype(bool)) & (watch_frame["change_5d_pct"] <= 0)

    level2 = []
    for _, row in watch_frame.sort_values(["watch_score", "strength_score"], ascending=False).iterrows():
        level2.append(
            {
                "name": row["name"],
                "level1": row["level1"],
                "status": ths_watch_status(float(row["watch_score"]), extended=bool(row["extended"]), weak=bool(row["weak"])),
                "score": round(float(row["watch_score"]), 1),
                "change_pct": round(float(row["change_pct"]), 2),
                "change_5d_pct": round(float(row["change_5d_pct"]), 2),
                "change_20d_pct": round(float(row["change_20d_pct"]), 2),
                **industry_metric_payload(row),
                "net_flow_100m": round(float(row["net_flow_100m"]), 2),
                "breadth_pct": round(float(row["breadth_ratio"]) * 100, 1),
                "above_20dma": bool(row["above_20dma"]),
                "above_50dma": bool(row["above_50dma"]),
                "amount_ratio_20d": round(float(row["amount_ratio_20d"]), 2),
                "leader": row["leader"],
                "leader_change_pct": round(float(row["leader_change_pct"]), 2),
                "company_count": int(row["company_count"]),
            }
        )

    level1_rows = []
    for level1_name, group in watch_frame.groupby("level1", sort=False):
        leaders = group.sort_values("watch_score", ascending=False).head(3)
        up_count = int(group["up_count"].sum())
        down_count = int(group["down_count"].sum())
        breadth_pct = up_count / max(up_count + down_count, 1) * 100
        score = (
            float(group["watch_score"].mean()) * 0.55
            + float(leaders["watch_score"].mean()) * 0.25
            + breadth_pct * 0.20
        )
        l1_metric = {
            "daily": weighted_average(group, "daily"),
            "5d": weighted_average(group, "5d"),
            "20d": weighted_average(group, "20d"),
            "atr_pct": weighted_average(group, "atr_pct"),
            "atrx50": weighted_average(group, "atrx50"),
            "rs_21d": weighted_average(group, "rs_21d"),
            "amount_20d_avg": float(pd.to_numeric(group["amount_20d_avg"], errors="coerce").fillna(0).sum()),
            "amount_z_20d": weighted_average(group, "amount_z_20d"),
            "grade": aggregate_grade(group),
            "above_ema20": weighted_average(group.assign(above_ema20_numeric=group["above_ema20"].astype(int)), "above_ema20_numeric") >= 0.5,
        }
        level1_rows.append(
            {
                "name": level1_name,
                "status": ths_watch_status(score, extended=bool((leaders["extended"]).mean() >= 0.67)),
                "score": round(score, 1),
                "change_pct": round(float(group["change_pct"].mean()), 2),
                "change_5d_pct": round(float(group["change_5d_pct"].mean()), 2),
                "change_20d_pct": round(float(group["change_20d_pct"].mean()), 2),
                **l1_metric,
                "net_flow_100m": round(float(group["net_flow_100m"].sum()), 2),
                "breadth_pct": round(breadth_pct, 1),
                "child_count": int(len(group)),
                "leaders": [
                    {
                        "name": child["name"],
                        "score": round(float(child["watch_score"]), 1),
                        "status": ths_watch_status(
                            float(child["watch_score"]),
                            extended=bool(child["extended"]),
                            weak=bool(child["weak"]),
                        ),
                    }
                    for _, child in leaders.iterrows()
                ],
            }
        )

    level1_frame = pd.DataFrame(level1_rows)
    if not level1_frame.empty:
        assign_percentile_rank(level1_frame, "20d", "group_rank_20d")
        level1_frame["good_setup_reason"] = level1_frame.apply(etf_style_setup_reason, axis=1)
        level1_frame["good_setup"] = level1_frame["good_setup_reason"].notna()
        level1 = sorted(
            [{**row, **industry_metric_payload(row)} for row in level1_frame.to_dict(orient="records")],
            key=lambda item: item["score"],
            reverse=True,
        )
    else:
        level1 = []
    return {
        "summary": "THS level-1 industries are aggregated from the public THS industry-board list; level-2 entries are the strongest THS industry boards by strength, persistence, and confirmation.",
        "level1": level1,
        "level2": level2,
    }


def build_regime_summary(turnover_ratio: float, northbound_flow: float, advancers: int, decliners: int, above_50_pct: float) -> str:
    phrases = []
    if turnover_ratio >= 1.05:
        phrases.append("turnover is expanding")
    elif turnover_ratio <= 0.95:
        phrases.append("turnover is below its 20-day baseline")
    else:
        phrases.append("turnover is roughly in line with its 20-day baseline")
    phrases.append("northbound is supportive" if northbound_flow > 0 else "northbound is not confirming")
    phrases.append("breadth is broad" if advancers > decliners * 2 else "breadth is mixed")
    phrases.append("medium-term participation is healthy" if above_50_pct >= 55 else "medium-term participation is still selective")
    return ", ".join(phrases) + "."


def build_swing_breadth(
    market_date: str,
    built_at: str,
    benchmark_history: pd.DataFrame,
) -> Dict[str, object]:
    market_date_dt = pd.to_datetime(market_date)
    market_date_compact = market_date_dt.strftime("%Y%m%d")

    trading_dates = benchmark_history["date"].dropna().drop_duplicates().sort_values().tail(20).tolist()
    turnover_series = build_turnover_series(trading_dates)
    latest_turnover = turnover_series[-1]["turnover"]
    average_turnover = sum(item["turnover"] for item in turnover_series) / len(turnover_series)
    turnover_ratio = latest_turnover / average_turnover if average_turnover else 1.0

    market_activity = fetch_market_activity()
    northbound = fetch_northbound_summary()
    ensure_trade_date("Market activity", market_activity.get("trade_date"), market_date)
    ensure_trade_date("Northbound summary", northbound.get("trade_date"), market_date)

    industry_today = fetch_ths_fund_flow("industry", "today")
    industry_5d = fetch_ths_fund_flow("industry", "5d")[["name", "period_change_pct", "net_flow_100m"]].rename(
        columns={"period_change_pct": "change_5d_pct", "net_flow_100m": "net_flow_5d_100m"}
    )
    industry_20d = fetch_ths_fund_flow("industry", "20d")[["name", "period_change_pct", "net_flow_100m"]].rename(
        columns={"period_change_pct": "change_20d_pct", "net_flow_100m": "net_flow_20d_100m"}
    )

    history_start = benchmark_history["date"].dropna().sort_values().iloc[-80].strftime("%Y%m%d")
    industry_rows = []
    for _, row in industry_today.iterrows():
        history = fetch_industry_index_history(row["name"], history_start, market_date_compact)
        history = normalize_ths_index_history(history)
        close = history["close"]
        amount = history["amount"]
        ema20 = history["close"].ewm(span=20, adjust=False).mean().iloc[-1]
        atr = calculate_atr(history)
        rs_frame = calculate_relative_strength(history, benchmark_history)
        sma20 = float(close.rolling(window=20).mean().iloc[-1])
        sma50 = float(close.rolling(window=50).mean().iloc[-1])
        industry_rows.append(
            {
                "name": row["name"],
                "company_count": int(row["company_count"]),
                "above_20dma": bool(close.iloc[-1] > sma20),
                "above_ema20": bool(close.iloc[-1] > ema20),
                "above_50dma": bool(close.iloc[-1] > sma50),
                "daily": round(rolling_return(close, 1), 2),
                "5d": round(rolling_return(close, 5), 2),
                "20d": round(rolling_return(close, 20), 2),
                "atr_pct": round((atr / close.iloc[-1]) * 100, 2),
                "atrx50": round((close.iloc[-1] - sma50) / atr, 2),
                "rs_21d": round(percentile_of_last(rs_frame["rolling_rrs"]), 0),
                "amount_20d_avg": round(amount.tail(20).mean() / 100000000, 1),
                "amount_z_20d": round(zscore_of_last(amount), 2),
                "grade": calculate_grade(history),
                "change_5d_pct_hist": round(rolling_return(close, 5), 2),
                "change_20d_pct_hist": round(rolling_return(close, 20), 2),
                "positive_days_5": positive_day_count(close, 5),
                "amount_ratio_20d": round(float(amount.iloc[-1] / amount.tail(20).mean()), 2),
            }
        )

    industry_frame = pd.DataFrame(industry_rows).merge(industry_5d, on="name", how="left").merge(industry_20d, on="name", how="left")
    industry_summary = fetch_industry_summary_ths()
    industry_summary = industry_summary.rename(
        columns={
            "板块": "name",
            "涨跌幅": "change_pct",
            "净流入": "net_flow_100m",
            "上涨家数": "up_count",
            "下跌家数": "down_count",
            "领涨股": "leader",
            "领涨股-涨跌幅": "leader_change_pct",
        }
    )
    industry_summary = industry_summary[["name", "change_pct", "net_flow_100m", "up_count", "down_count", "leader", "leader_change_pct"]]
    for column in ["change_pct", "net_flow_100m", "leader_change_pct"]:
        industry_summary[column] = pd.to_numeric(industry_summary[column], errors="coerce")

    industry_frame = industry_frame.merge(industry_summary, on="name", how="left")
    industry_frame["change_pct"] = industry_frame["change_pct"].fillna(0.0)
    industry_frame["change_5d_pct"] = industry_frame["change_5d_pct"].fillna(industry_frame["change_5d_pct_hist"])
    industry_frame["change_20d_pct"] = industry_frame["change_20d_pct"].fillna(industry_frame["change_20d_pct_hist"])
    industry_frame["net_flow_5d_100m"] = industry_frame["net_flow_5d_100m"].fillna(0.0)
    industry_frame["net_flow_20d_100m"] = industry_frame["net_flow_20d_100m"].fillna(0.0)
    industry_frame["net_flow_100m"] = industry_frame["net_flow_100m"].fillna(0.0)
    industry_frame["up_count"] = industry_frame["up_count"].fillna(industry_frame["company_count"]).astype(int)
    industry_frame["down_count"] = industry_frame["down_count"].fillna(0).astype(int)
    industry_frame["breadth_ratio"] = industry_frame["up_count"] / (industry_frame["up_count"] + industry_frame["down_count"]).replace(0, pd.NA)
    industry_frame["breadth_ratio"] = industry_frame["breadth_ratio"].fillna(0.5)
    industry_frame["leader"] = industry_frame["leader"].fillna("")
    industry_frame["leader_change_pct"] = industry_frame["leader_change_pct"].fillna(0.0)

    zt_pool = ak.stock_zt_pool_em(date=market_date_compact)
    previous_zt_pool = ak.stock_zt_pool_previous_em(date=market_date_compact)
    strong_pool = ak.stock_zt_pool_strong_em(date=market_date_compact)
    broken_pool = ak.stock_zt_pool_zbgc_em(date=market_date_compact)
    limit_down_pool = ak.stock_zt_pool_dtgc_em(date=market_date_compact)

    zt_counts = build_industry_pool_counts(zt_pool)
    strong_counts = build_industry_pool_counts(strong_pool)
    broken_counts = build_industry_pool_counts(broken_pool)

    industry_frame["limit_up_count"] = industry_frame["name"].map(lambda name: zt_counts.get(normalize_sector_name(name), 0))
    industry_frame["strong_pool_count"] = industry_frame["name"].map(lambda name: strong_counts.get(normalize_sector_name(name), 0))
    industry_frame["broken_board_count"] = industry_frame["name"].map(lambda name: broken_counts.get(normalize_sector_name(name), 0))

    strength_weights = {
        "change_pct": 0.22,
        "net_flow_100m": 0.18,
        "breadth_ratio": 0.16,
        "change_5d_pct": 0.14,
        "change_20d_pct": 0.12,
        "net_flow_5d_100m": 0.10,
        "net_flow_20d_100m": 0.08,
    }
    industry_frame["strength_score"] = (
        sum(series_rank_pct(industry_frame[column]) * weight for column, weight in strength_weights.items())
        / sum(strength_weights.values())
        * 100
    ).round(1)
    industry_frame["persistence_score"] = (
        (
            industry_frame["above_20dma"].astype(int) * 0.24
            + industry_frame["above_50dma"].astype(int) * 0.24
            + (industry_frame["positive_days_5"] / 5.0) * 0.18
            + series_rank_pct(industry_frame["change_5d_pct"]) * 0.12
            + series_rank_pct(industry_frame["change_20d_pct"]) * 0.12
            + (industry_frame["net_flow_5d_100m"] > 0).astype(int) * 0.05
            + (industry_frame["net_flow_20d_100m"] > 0).astype(int) * 0.05
        )
        * 100
    ).round(1)
    industry_frame["confirmation_score"] = (
        (
            series_rank_pct(industry_frame["limit_up_count"]) * 0.14
            + series_rank_pct(industry_frame["strong_pool_count"]) * 0.16
            + (1 - series_rank_pct(industry_frame["broken_board_count"])) * 0.14
            + industry_frame["breadth_ratio"] * 0.18
            + industry_frame["above_20dma"].astype(int) * 0.19
            + industry_frame["above_50dma"].astype(int) * 0.19
        )
        * 100
    ).round(1)
    industry_frame["leadership_score"] = (
        industry_frame["strength_score"] * 0.45
        + industry_frame["persistence_score"] * 0.25
        + industry_frame["confirmation_score"] * 0.30
    ).round(1)

    fake_flags = []
    for _, row in industry_frame.iterrows():
        flags = []
        if row["change_pct"] > 0 and row["net_flow_100m"] <= 0:
            flags.append("day-one pop without inflow")
        if row["change_pct"] > 0 and row["breadth_ratio"] < 0.58:
            flags.append("leader-only breadth")
        if row["change_pct"] > 0 and row["change_20d_pct"] <= 0:
            flags.append("still negative on the 20-day leg")
        if row["leader_change_pct"] > max(8.0, row["change_pct"] * 2) and row["breadth_ratio"] < 0.65:
            flags.append("single-stock squeeze")
        if row["broken_board_count"] > max(1, row["strong_pool_count"]):
            flags.append("broken-board pressure")
        fake_flags.append(flags)
    industry_frame["fake_flags"] = fake_flags
    industry_frame["fake_score"] = (
        series_rank_pct(industry_frame["change_pct"]) * 0.26
        + series_rank_pct(industry_frame["leader_change_pct"]) * 0.14
        + series_rank_pct(industry_frame["broken_board_count"]) * 0.20
        + (1 - series_rank_pct(industry_frame["breadth_ratio"])) * 0.18
        + (1 - series_rank_pct(industry_frame["net_flow_5d_100m"])) * 0.12
        + (1 - series_rank_pct(industry_frame["change_20d_pct"])) * 0.10
    ) * 100

    concept_today = fetch_ths_fund_flow("concept", "today")
    concept_5d = fetch_ths_fund_flow("concept", "5d")[["name", "period_change_pct", "net_flow_100m"]].rename(
        columns={"period_change_pct": "change_5d_pct", "net_flow_100m": "net_flow_5d_100m"}
    )
    concept_20d = fetch_ths_fund_flow("concept", "20d")[["name", "period_change_pct", "net_flow_100m"]].rename(
        columns={"period_change_pct": "change_20d_pct", "net_flow_100m": "net_flow_20d_100m"}
    )
    concept_frame = concept_today.merge(concept_5d, on="name", how="left").merge(concept_20d, on="name", how="left")
    for column in ["change_pct", "net_flow_100m", "change_5d_pct", "net_flow_5d_100m", "change_20d_pct", "net_flow_20d_100m", "leader_change_pct"]:
        concept_frame[column] = concept_frame[column].fillna(0.0)
    concept_frame["heat_score"] = (
        (
            series_rank_pct(concept_frame["change_pct"]) * 0.22
            + series_rank_pct(concept_frame["net_flow_100m"]) * 0.20
            + series_rank_pct(concept_frame["change_5d_pct"]) * 0.18
            + series_rank_pct(concept_frame["net_flow_5d_100m"]) * 0.16
            + series_rank_pct(concept_frame["change_20d_pct"]) * 0.12
            + series_rank_pct(concept_frame["net_flow_20d_100m"]) * 0.12
        )
        * 100
    ).round(1)

    industry_above_20_pct = round(industry_frame["above_20dma"].mean() * 100, 1)
    industry_above_50_pct = round(industry_frame["above_50dma"].mean() * 100, 1)
    advancers = int(market_activity.get("上涨", 0))
    decliners = int(market_activity.get("下跌", 0))
    real_limit_up = int(market_activity.get("真实涨停", market_activity.get("涨停", len(zt_pool))))
    real_limit_down = int(market_activity.get("真实跌停", market_activity.get("跌停", len(limit_down_pool))))
    ad_ratio = advancers / max(decliners, 1)
    limit_spread = real_limit_up - real_limit_down

    regime_score = round(
        (
            scale_unit_interval(turnover_ratio, 0.85, 1.25) * 0.24
            + scale_unit_interval(northbound["net_flow_100m"], -120, 180) * 0.18
            + scale_unit_interval(ad_ratio, 0.7, 3.0) * 0.24
            + scale_unit_interval(limit_spread, -15, 90) * 0.16
            + ((industry_above_20_pct / 100) * 0.45 + (industry_above_50_pct / 100) * 0.55) * 0.18
        )
        * 100,
        1,
    )
    momentum_score = round(
        (
            scale_unit_interval(real_limit_up, 15, 120) * 0.26
            + scale_unit_interval(len(strong_pool), 20, 120) * 0.18
            + scale_unit_interval(
                ((previous_zt_pool["涨跌幅"] > 0).sum() / len(previous_zt_pool) * 100) if len(previous_zt_pool) else 0,
                35,
                70,
            )
            * 0.26
            + (1 - scale_unit_interval(len(broken_pool) / max(len(zt_pool) + len(broken_pool), 1), 0.18, 0.55)) * 0.18
            + (1 - scale_unit_interval(real_limit_down, 5, 35)) * 0.12
        )
        * 100,
        1,
    )

    if regime_score >= 72:
        regime_label = "Expansion"
    elif regime_score >= 58:
        regime_label = "Constructive"
    elif regime_score >= 45:
        regime_label = "Mixed"
    elif regime_score >= 32:
        regime_label = "Defensive"
    else:
        regime_label = "Washout"

    if momentum_score >= 70:
        momentum_label = "Healthy"
    elif momentum_score >= 52:
        momentum_label = "Usable"
    elif momentum_score >= 38:
        momentum_label = "Choppy"
    else:
        momentum_label = "Fragile"

    strong_new_high_pct = round((strong_pool["是否新高"].eq("是").sum() / len(strong_pool) * 100) if len(strong_pool) else 0, 1)
    prev_limitup_positive_pct = round((previous_zt_pool["涨跌幅"] > 0).sum() / len(previous_zt_pool) * 100, 1) if len(previous_zt_pool) else 0.0
    broken_board_ratio = round(len(broken_pool) / max(len(zt_pool) + len(broken_pool), 1) * 100, 1)
    streak_two_plus = int(pd.to_numeric(zt_pool["连板数"], errors="coerce").fillna(0).ge(2).sum())
    max_streak = int(pd.to_numeric(zt_pool["连板数"], errors="coerce").fillna(0).max()) if len(zt_pool) else 0

    top_industries = industry_frame.sort_values(["leadership_score", "strength_score"], ascending=False).head(8)
    weak_industries = industry_frame[industry_frame["change_pct"] > 0].sort_values(["fake_score", "strength_score"], ascending=[False, False]).head(4)
    top_concepts = concept_frame.sort_values(["heat_score", "net_flow_100m"], ascending=False).head(8)
    industry_watchlist = build_ths_industry_watchlist(industry_frame)

    notes = [
        "沪深成交额 uses Shanghai + Shenzhen stock turnover from exchange summaries, which keeps the 20-day comparison internally consistent.",
        "20DMA / 50DMA participation is measured on industry boards, not all individual A-shares, to keep the build practical and still useful for swing breadth.",
        "Northbound uses the current Eastmoney net-flow feed because recent net-buy fields are incomplete in the historical endpoint.",
        "Industry and concept flow tables come from THS pages via AkShare's token workflow; the local parser avoids the stale wrapper column mapping.",
    ]
    regime_summary = build_regime_summary(turnover_ratio, northbound["net_flow_100m"], advancers, decliners, industry_above_50_pct)

    return {
        "built_at": built_at,
        "market_date": market_date,
        "notes": notes,
        "regime": {
            "label": regime_label,
            "score": regime_score,
            "summary": regime_summary,
            "signals": [
                {
                    "label": "沪深成交额",
                    "display": format_turnover_trillion(latest_turnover / 1000000000000),
                    "detail": f"{turnover_ratio:.2f}x vs 20D avg",
                    "tone": tone_from_signed(turnover_ratio - 1, 0.05, -0.05),
                },
                {
                    "label": "北向净流",
                    "display": format_money_100m(northbound["net_flow_100m"]),
                    "detail": f"沪股通 {northbound['sh_index_change_pct']:+.2f}% | 深股通 {northbound['sz_index_change_pct']:+.2f}%",
                    "tone": tone_from_signed(northbound["net_flow_100m"]),
                },
                {
                    "label": "涨跌家数",
                    "display": f"{advancers} / {decliners}",
                    "detail": f"A/D {ad_ratio:.2f}x",
                    "tone": tone_from_signed(advancers - decliners),
                },
                {
                    "label": "涨停对跌停",
                    "display": f"{real_limit_up} / {real_limit_down}",
                    "detail": f"炸板 {len(broken_pool)} | 强势池 {len(strong_pool)}",
                    "tone": tone_from_signed(limit_spread),
                },
                {
                    "label": "行业站上均线",
                    "display": f"{industry_above_20_pct:.0f}% / {industry_above_50_pct:.0f}%",
                    "detail": "Above 20DMA / 50DMA",
                    "tone": tone_from_score((industry_above_20_pct * 0.4 + industry_above_50_pct * 0.6), 62, 38),
                },
            ],
        },
        "sector_breadth": {
            "summary": f"{industry_above_20_pct:.0f}% of industry boards are above the 20DMA and {industry_above_50_pct:.0f}% are above the 50DMA.",
            "signals": [
                {
                    "label": "Industry Breadth",
                    "display": f"{industry_above_20_pct:.0f}% / {industry_above_50_pct:.0f}%",
                    "detail": "Above 20DMA / 50DMA",
                    "tone": tone_from_score((industry_above_20_pct + industry_above_50_pct) / 2, 60, 40),
                },
                {
                    "label": "Top Industry",
                    "display": top_industries.iloc[0]["name"],
                    "detail": f"Strength {top_industries.iloc[0]['strength_score']:.0f} | Persistence {top_industries.iloc[0]['persistence_score']:.0f}",
                    "tone": "positive",
                },
                {
                    "label": "Top Concept",
                    "display": top_concepts.iloc[0]['name'],
                    "detail": f"Heat {top_concepts.iloc[0]['heat_score']:.0f} | Flow {format_money_100m(top_concepts.iloc[0]['net_flow_100m'])}",
                    "tone": "positive",
                },
            ],
            "industries": [
                {
                    "name": row["name"],
                    "change_pct": round(float(row["change_pct"]), 2),
                    "change_5d_pct": round(float(row["change_5d_pct"]), 2),
                    "change_20d_pct": round(float(row["change_20d_pct"]), 2),
                    "net_flow_100m": round(float(row["net_flow_100m"]), 2),
                    "up_count": int(row["up_count"]),
                    "down_count": int(row["down_count"]),
                    "persistence": describe_persistence(float(row["persistence_score"])),
                    "leadership": describe_leadership(float(row["leadership_score"])),
                    "strength_score": round(float(row["strength_score"]), 1),
                    "limit_up_count": int(row["limit_up_count"]),
                    "strong_pool_count": int(row["strong_pool_count"]),
                    "broken_board_count": int(row["broken_board_count"]),
                    "leader": row["leader"],
                    "leader_change_pct": round(float(row["leader_change_pct"]), 2),
                }
                for _, row in top_industries.iterrows()
            ],
            "concepts": [
                {
                    "name": row["name"],
                    "change_pct": round(float(row["change_pct"]), 2),
                    "change_5d_pct": round(float(row["change_5d_pct"]), 2),
                    "change_20d_pct": round(float(row["change_20d_pct"]), 2),
                    "net_flow_100m": round(float(row["net_flow_100m"]), 2),
                    "net_flow_5d_100m": round(float(row["net_flow_5d_100m"]), 2),
                    "net_flow_20d_100m": round(float(row["net_flow_20d_100m"]), 2),
                    "leader": row["leader"],
                    "leader_change_pct": round(float(row["leader_change_pct"]), 2),
                    "heat_score": round(float(row["heat_score"]), 1),
                }
                for _, row in top_concepts.iterrows()
            ],
        },
        "industry_watchlist": industry_watchlist,
        "momentum_health": {
            "label": momentum_label,
            "score": momentum_score,
            "summary": f"Continuation is {momentum_label.lower()} with {prev_limitup_positive_pct:.0f}% of yesterday's limit-ups still positive and a {broken_board_ratio:.0f}% broken-board ratio.",
            "signals": [
                {
                    "label": "真实涨停",
                    "display": str(real_limit_up),
                    "detail": f"连板 2+ {streak_two_plus} | 最高连板 {max_streak}",
                    "tone": tone_from_score(real_limit_up, 80, 25),
                },
                {
                    "label": "跌停 / 炸板",
                    "display": f"{real_limit_down} / {len(broken_pool)}",
                    "detail": f"炸板率 {broken_board_ratio:.1f}%",
                    "tone": "negative" if broken_board_ratio >= 35 or real_limit_down >= 10 else "neutral",
                },
                {
                    "label": "强势股池",
                    "display": str(len(strong_pool)),
                    "detail": f"{strong_new_high_pct:.0f}% making new highs",
                    "tone": tone_from_score(strong_new_high_pct, 55, 25),
                },
                {
                    "label": "昨日涨停延续",
                    "display": f"{prev_limitup_positive_pct:.0f}%",
                    "detail": f"{len(previous_zt_pool)} names in sample",
                    "tone": tone_from_score(prev_limitup_positive_pct, 62, 42),
                },
            ],
        },
        "leadership_quality": {
            "summary": "Best leadership needs breadth, inflow, persistence, and stock-pool confirmation. Fake leadership is usually a single-stock squeeze or a one-day pop without follow-through.",
            "best": [
                {
                    "name": row["name"],
                    "leadership": describe_leadership(float(row["leadership_score"])),
                    "strength_score": round(float(row["strength_score"]), 1),
                    "persistence_score": round(float(row["persistence_score"]), 1),
                    "detail": f"Flow {format_money_100m(float(row['net_flow_100m']))} | breadth {int(row['up_count'])}/{int(row['down_count'])} | strong {int(row['strong_pool_count'])}",
                }
                for _, row in top_industries.head(4).iterrows()
            ],
            "fake": [
                {
                    "name": row["name"],
                    "fake_score": round(float(row["fake_score"]), 1),
                    "detail": describe_fake_risk(row["fake_flags"]),
                }
                for _, row in weak_industries.iterrows()
            ],
        },
    }


def build_column_ranges(groups: Dict[str, List[Dict[str, object]]]) -> Dict[str, Dict[str, List[float]]]:
    ranges = {}
    for group_name, rows in groups.items():
        daily_values = [row["daily"] for row in rows]
        five_day_values = [row["5d"] for row in rows]
        twenty_day_values = [row["20d"] for row in rows]
        ranges[group_name] = {
            "daily": [min(daily_values), max(daily_values)],
            "5d": [min(five_day_values), max(five_day_values)],
            "20d": [min(twenty_day_values), max(twenty_day_values)],
        }
    return ranges


def write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def read_json(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def assert_swing_breadth_fresh(path: Path, market_date: str) -> None:
    if not path.exists():
        raise RuntimeError(f"Swing breadth output is missing: {path}")

    payload = read_json(path)
    swing_market_date = payload.get("market_date")
    if swing_market_date != market_date:
        raise RuntimeError(
            f"Swing breadth output is stale: market_date={swing_market_date}, expected={market_date}. "
            "Do not publish a mixed-date dashboard; retry after THS breadth sources refresh."
        )

    watchlist = payload.get("industry_watchlist")
    if not isinstance(watchlist, dict):
        raise RuntimeError(f"Swing breadth output is missing industry_watchlist: {path}")
    if not watchlist.get("level1") or not watchlist.get("level2"):
        raise RuntimeError(f"Swing breadth output has an incomplete THS industry watchlist: {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="data", help="Output directory")
    parser.add_argument(
        "--allow-stale",
        action="store_true",
        help="Write files even when the latest ETF source date is older than the expected China session.",
    )
    parser.add_argument(
        "--allow-partial-breadth",
        action="store_true",
        help="Keep stale or missing swing breadth output when optional breadth sources are unavailable.",
    )
    args = parser.parse_args()

    universe = load_universe()
    items = universe["items"]
    items_by_code = {item["code"]: item for item in items}
    for item in items:
        benchmark = items_by_code[item["benchmark_code"]]
        item["benchmark_exchange"] = benchmark["exchange"]

    out_dir = ROOT / args.out_dir
    charts_dir = out_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    history_cache: Dict[str, pd.DataFrame] = {}
    groups: Dict[str, List[Dict[str, object]]] = {group_name: [] for group_name in universe["group_order"]}

    for item in items:
        benchmark_name = items_by_code[item["benchmark_code"]]["label"]
        print(f"[{item['group']}] {item['code']} {item['label']}")
        row = build_row(item, benchmark_name, history_cache, charts_dir)
        groups[item["group"]].append(row)

    latest_market_date = max(row["market_date"] for rows in groups.values() for row in rows)
    assert_fresh_market_date(latest_market_date, allow_stale=args.allow_stale)
    for group_name in universe["group_order"]:
        assign_group_ranks(groups[group_name])
        assign_good_setups(groups[group_name])
        groups[group_name].sort(key=lambda row: (row["rs_21d"], row["5d"]), reverse=True)

    built_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    snapshot = {
        "built_at": built_at,
        "market_date": latest_market_date,
        "groups": groups,
        "column_ranges": build_column_ranges(groups),
    }
    meta = {
        "title": "China ETF Rotation Dashboard",
        "source": "AkShare / Sina ETF history",
        "group_order": universe["group_order"],
        "group_colors": universe["group_colors"],
        "default_symbol": universe["default_symbol"],
    }
    breadth = build_breadth(groups, universe["group_order"], built_at)
    swing_breadth_path = out_dir / "breadth_swing.json"

    write_json(out_dir / "snapshot.json", snapshot)
    write_json(out_dir / "meta.json", meta)
    write_json(out_dir / "breadth.json", breadth)

    print(f"Wrote {out_dir / 'snapshot.json'}")
    print(f"Wrote {out_dir / 'meta.json'}")
    print(f"Wrote {out_dir / 'breadth.json'}")

    # GitHub Pages should never publish a mixed-date dashboard. Use
    # --allow-partial-breadth only for local ETF-only debugging.
    try:
        benchmark_history = fetch_history("SSE", universe["default_symbol"], history_cache)
        swing_breadth = build_swing_breadth(latest_market_date, built_at, benchmark_history)
    except Exception as exc:
        if args.allow_partial_breadth and swing_breadth_path.exists():
            print(f"Warning: keeping existing {swing_breadth_path} because the optional swing breadth build failed: {exc}")
        elif args.allow_partial_breadth:
            print(f"Warning: skipped {swing_breadth_path} because the optional swing breadth build failed and no previous file exists: {exc}")
        else:
            raise RuntimeError(
                "Failed to build swing breadth data. The dashboard would otherwise publish fresh ETF data "
                "with stale or missing industry breadth data."
            ) from exc
    else:
        write_json(swing_breadth_path, swing_breadth)
        print(f"Wrote {swing_breadth_path}")

    if not args.allow_partial_breadth:
        assert_swing_breadth_fresh(swing_breadth_path, latest_market_date)


if __name__ == "__main__":
    main()
