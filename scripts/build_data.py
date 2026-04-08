from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import akshare as ak
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "china_etf_universe.json"


def load_universe() -> Dict[str, object]:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="data", help="Output directory")
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
    for group_name in universe["group_order"]:
        assign_group_ranks(groups[group_name])
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

    write_json(out_dir / "snapshot.json", snapshot)
    write_json(out_dir / "meta.json", meta)
    write_json(out_dir / "breadth.json", breadth)

    print(f"Wrote {out_dir / 'snapshot.json'}")
    print(f"Wrote {out_dir / 'meta.json'}")
    print(f"Wrote {out_dir / 'breadth.json'}")


if __name__ == "__main__":
    main()
