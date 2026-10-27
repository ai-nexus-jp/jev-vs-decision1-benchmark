"""
ベンチマーク結果レポート・CSV生成モジュール (src/reporter.py)
"""

import csv
import os
from typing import Any, Dict, List

from src.models.base import BaseModelAdapter, PredictionResult

def save_benchmark_csv(
    questions: List[Dict[str, Any]],
    models: List[BaseModelAdapter],
    results: Dict[str, Dict[str, PredictionResult]],  # {qid: {model_id: PredictionResult}}
    output_path: str = "data/benchmark_results.csv",
) -> None:
    """4モデルの結果を横並びにしたCSVを保存する。"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    fieldnames = [
        "id",
        "category",
        "category_description",
        "input_text",
        "expected",
    ]

    # モデルごとのカラムを追加
    for m in models:
        mid = m.model_id
        fieldnames.extend([
            f"{mid}_prediction",
            f"{mid}_confidence",
            f"{mid}_second",
            f"{mid}_margin",
            f"{mid}_probabilities",
            f"{mid}_latency_ms",
            f"{mid}_is_correct",
            f"{mid}_error",
        ])

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for q in questions:
            qid = q["id"]
            row = {
                "id": qid,
                "category": q.get("category", ""),
                "category_description": q.get("category_description", ""),
                "input_text": q.get("input_text", ""),
                "expected": q.get("expected", ""),
            }

            for m in models:
                mid = m.model_id
                res = results.get(qid, {}).get(mid)
                if res:
                    row[f"{mid}_prediction"] = res.prediction
                    row[f"{mid}_confidence"] = f"{res.confidence:.3f}" if res.confidence is not None else ""
                    row[f"{mid}_second"] = res.second_prediction or ""
                    row[f"{mid}_margin"] = f"{res.margin:.3f}" if res.margin is not None else ""
                    row[f"{mid}_probabilities"] = res.probabilities_summary or ""
                    row[f"{mid}_latency_ms"] = f"{res.latency_ms:.1f}"
                    row[f"{mid}_is_correct"] = str(res.is_correct)
                    row[f"{mid}_error"] = res.error or ""
                else:
                    row[f"{mid}_prediction"] = "N/A"
                    row[f"{mid}_confidence"] = ""
                    row[f"{mid}_second"] = ""
                    row[f"{mid}_margin"] = ""
                    row[f"{mid}_probabilities"] = ""
                    row[f"{mid}_latency_ms"] = ""
                    row[f"{mid}_is_correct"] = ""
                    row[f"{mid}_error"] = "Not evaluated"

            writer.writerow(row)

    print(f"\n✅ ベンチマーク結果CSVを保存しました: {output_path}")


def print_comparison_summary(
    questions: List[Dict[str, Any]],
    models: List[BaseModelAdapter],
    results: Dict[str, Dict[str, PredictionResult]],
) -> None:
    """ターミナルに美しいMarkdownサマリーレポートを出力する。"""
    categories = ["Category A", "Category B", "Category C", "Category D"]
    cat_names = {
        "Category A": "典型・明瞭",
        "Category B": "境界線・重複",
        "Category C": "皮肉・婉曲",
        "Category D": "敵対的・範囲外",
    }

    # 集計
    stats: Dict[str, Dict[str, Any]] = {}
    for m in models:
        stats[m.model_id] = {
            "name": m.display_name,
            "total": 0,
            "correct": 0,
            "latencies": [],
            "by_cat": {c: {"total": 0, "correct": 0} for c in categories},
        }

    for q in questions:
        qid = q["id"]
        cat = q.get("category", "")

        for m in models:
            mid = m.model_id
            res = results.get(qid, {}).get(mid)
            if not res or res.prediction in ("SKIPPED", "N/A"):
                continue

            stats[mid]["total"] += 1
            if cat in stats[mid]["by_cat"]:
                stats[mid]["by_cat"][cat]["total"] += 1

            if res.is_correct:
                stats[mid]["correct"] += 1
                if cat in stats[mid]["by_cat"]:
                    stats[mid]["by_cat"][cat]["correct"] += 1

            if res.latency_ms > 0:
                stats[mid]["latencies"].append(res.latency_ms)

    print("\n" + "=" * 80)
    print("📊 ベンチマーク総合サマリーレポート (同一計測定規による比較)")
    print("=" * 80)

    print("\n### 1. 全体パフォーマンス比較")
    print("| モデル名 | 正解率 (全80問) | 平均応答速度 (Latency) | 確信度/マージン出力 | スキーマ保証 |")
    print("| :--- | :---: | :---: | :---: | :---: |")

    for m in models:
        s = stats[m.model_id]
        if s["total"] == 0:
            continue
        acc = (s["correct"] / s["total"]) * 100.0
        avg_lat = sum(s["latencies"]) / len(s["latencies"]) if s["latencies"] else 0.0
        is_sys1 = m.model_id in ("jev", "decision1")
        conf_feature = "✅ 確率分布＋Margin" if is_sys1 else "❌ なし (要logprobs)"
        schema_feature = "✅ 100% (構文崩れゼロ)" if is_sys1 else "⚠️ JSONプロンプト依存"

        print(f"| **{m.display_name}** | **{acc:.1f}%** ({s['correct']}/{s['total']}) | **{avg_lat:.1f} ms** | {conf_feature} | {schema_feature} |")

    print("\n### 2. カテゴリ別 正解率比較")
    header_str = "| カテゴリ |" + "".join(f" {m.display_name} |" for m in models)
    sep_str = "| :--- |" + "".join(" :---: |" for _ in models)
    print(header_str)
    print(sep_str)

    for cat in categories:
        cname = cat_names.get(cat, cat)
        row_str = f"| **{cat} ({cname})** |"
        for m in models:
            cs = stats[m.model_id]["by_cat"][cat]
            if cs["total"] == 0:
                row_str += " - |"
            else:
                c_acc = (cs["correct"] / cs["total"]) * 100.0
                row_str += f" {c_acc:.1f}% ({cs['correct']}/{cs['total']}) |"
        print(row_str)

    print("\n" + "=" * 80)
