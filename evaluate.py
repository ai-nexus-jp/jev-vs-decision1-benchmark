#!/usr/bin/env python3
"""
統合ベンチマーク実行スクリプト (evaluate.py)
Jev, Decision-1, GPT-5, GPT-5-mini の4モデルを一括・同一条件で同時ベンチマークします。

使用方法:
    # 1. 有効な全モデルを一気に実行
    python3 evaluate.py

    # 2. 特定のモデルのみ実行
    python3 evaluate.py --models jev,decision1
    python3 evaluate.py --models gpt5,gpt5_mini

    # 3. モックによるドライラン確認
    python3 evaluate.py --dry-run
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

# プロジェクトモジュールの読み込み
from src.config import REQUEST_TIMEOUT_SECONDS, load_env_file
from src.models import get_active_models
from src.models.base import BaseModelAdapter, PredictionResult
from src.reporter import print_comparison_summary, save_benchmark_csv

load_env_file()

def run_benchmark(
    data_file: str = "data/test_data.json",
    output_file: str = "data/benchmark_results.csv",
    requested_models: str = "all",
    dry_run: bool = False,
    timeout: float = 15.0,
) -> None:
    """全モデルのベンチマークを実行し、CSVとレポートを生成する。"""
    if not os.path.exists(data_file):
        print(f"エラー: テストデータファイルが見つかりません: {data_file}")
        sys.exit(1)

    with open(data_file, "r", encoding="utf-8") as f:
        questions = json.load(f)

    # 評価対象モデルの選定
    m_list = [m.strip() for m in requested_models.split(",")] if requested_models != "all" else None
    models: List[BaseModelAdapter] = get_active_models(m_list)

    if not dry_run:
        # 実際に利用可能な（APIキー等がある）モデルのみを絞り込み
        available_models = [m for m in models if m.is_available()]
        if not available_models:
            print("エラー: 評価可能なモデルがありません。.env を確認してください。")
            print("  利用可能なモデルID: jev, decision1, gpt5, gpt5_mini")
            sys.exit(1)
        models = available_models

    print("=" * 80)
    print(f"🚀 統合ベンチマーク実行開始 (問題数: {len(questions)}問 | 実行モード: {'DRY-RUN (Mock)' if dry_run else '本番 API 通信'})")
    print("   ★ 計測定規: src/client.py::send_post_request (高精度ミリ秒計測) ★")
    print("対象モデル:")
    for m in models:
        print(f"  - [{m.model_id}] {m.display_name}")
    print("=" * 80)

    # 結果保持辞書: {qid: {model_id: PredictionResult}}
    results: Dict[str, Dict[str, PredictionResult]] = {}

    for i, q in enumerate(questions, 1):
        qid = q["id"]
        category = q.get("category", "")
        input_text = q.get("input_text", "")
        expected = q.get("expected", "")

        print(f"\n[{i:02d}/{len(questions):02d}] {qid} ({category}) | Expected: {expected}")
        print(f"   Input: 「{input_text[:60]}...」" if len(input_text) > 60 else f"   Input: 「{input_text}」")
        results[qid] = {}

        for m in models:
            if dry_run:
                res = m.get_mock_prediction(category=category, expected=expected)
            else:
                res = m.predict(input_text=input_text, expected=expected, timeout=timeout)

            results[qid][m.model_id] = res

            status_mark = "✅ 正解" if res.is_correct else ("❌ 誤答" if not res.error else "⚠️ エラー")
            conf_str = f" (conf: {res.confidence:.3f}, mgn: {res.margin:.3f})" if res.confidence is not None else ""
            print(f"   └─ {m.display_name:<20}: {status_mark} [{res.prediction}]{conf_str} | {res.latency_ms:.1f}ms")

        # レート制限を考慮した微小待機
        if not dry_run:
            time.sleep(0.05)

    # CSV出力
    save_benchmark_csv(
        questions=questions,
        models=models,
        results=results,
        output_path=output_file,
    )

    # 総合サマリーレポート出力
    print_comparison_summary(
        questions=questions,
        models=models,
        results=results,
    )

def main():
    parser = argparse.ArgumentParser(
        description="Unified Benchmark for System 1 (Jev / Decision-1) vs System 2 (GPT-5 / GPT-5-mini)",
    )
    parser.add_argument(
        "--data-file",
        default="data/test_data.json",
        help="Path to benchmark test data JSON (default: data/test_data.json)",
    )
    parser.add_argument(
        "--output",
        default="data/benchmark_results.csv",
        help="Path to output CSV file (default: data/benchmark_results.csv)",
    )
    parser.add_argument(
        "--models",
        default="all",
        help="Comma-separated model IDs (jev,decision1,gpt5,gpt5_mini or all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run benchmark using mock metrics without actual API calls",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=REQUEST_TIMEOUT_SECONDS,
        help="API request timeout in seconds",
    )
    args = parser.parse_args()

    run_benchmark(
        data_file=args.data_file,
        output_file=args.output,
        requested_models=args.models,
        dry_run=args.dry_run,
        timeout=args.timeout,
    )

if __name__ == "__main__":
    main()

