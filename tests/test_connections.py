#!/usr/bin/env python3
"""
全モデル疎通確認テスト (tests/test_connections.py)
Jev, Decision-1, GPT-5, GPT-5-mini のうち、
.env にキーが設定されているすべてのモデルに対して1問だけテスト送信し、
接続性・認証・レイテンシ・分類結果を一括検証します。

使用方法:
    python3 tests/test_connections.py
    python3 tests/test_connections.py --models jev,decision1
"""

import argparse
import os
import sys

# プロジェクトルートをインポートパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import load_env_file
from src.models import get_active_models, get_all_registered_models

load_env_file()

TEST_INPUT = "先月分の領収書を再発行してほしいのですが、管理画面のどこからダウンロードできますか？"
EXPECTED_INTENT = "billing"

def main():
    parser = argparse.ArgumentParser(description="Test model connections")
    parser.add_argument(
        "--models",
        default="all",
        help="Comma-separated model IDs to test (jev,decision1,gpt5,gpt5_mini or all)",
    )
    args = parser.parse_args()

    requested = [m.strip() for m in args.models.split(",")] if args.models != "all" else None
    models = get_active_models(requested)

    print("=" * 75)
    print("  全モデル疎通確認テスト (Test Connections)")
    print("=" * 75)
    print(f"テスト問題 : 「{TEST_INPUT}」")
    print(f"期待される分類: '{EXPECTED_INTENT}'\n")

    available_count = 0
    for m in models:
        print(f"--- [{m.display_name}] (ID: {m.model_id}) ---")
        if not m.is_available():
            print("  ⚠️ スキップ: .env に接続設定（URLまたはKEY）がありません。\n")
            continue

        available_count += 1
        res = m.predict(input_text=TEST_INPUT, expected=EXPECTED_INTENT, timeout=15.0)

        if res.error:
            print(f"  ❌ 疎通失敗: {res.error}")
            print(f"     所要時間: {res.latency_ms:.1f} ms\n")
        else:
            status = "✅ 正解" if res.is_correct else f"❌ 不一致 ({res.prediction})"
            print(f"  結果: {status} (出力: {res.prediction})")
            print(f"  応答時間 (Latency): {res.latency_ms:.1f} ms")
            if res.confidence is not None:
                print(f"  確信度: {res.confidence:.3f} | Margin: {res.margin:.3f}")
                print(f"  全選択肢確率分布: {res.probabilities_summary}")
            print()

    print("=" * 75)
    print(f"検証完了: {available_count} / {len(models)} モデルが利用可能です。")
    print("=" * 75)

if __name__ == "__main__":
    main()
