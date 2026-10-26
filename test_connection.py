#!/usr/bin/env python3
"""
API 接続テストスクリプト (test_connection.py)

概要:
    TypeSafe Jev と Microsoft-Decision-1 の両エンドポイントに対して
    テストリクエスト（1問）を送信し、認証ヘッダー、疎通性、および
    レスポンスJSON構造が正常か事前診断します。

使用方法:
    python3 test_connection.py
    python3 test_connection.py --model jev
    python3 test_connection.py --model decision1
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, Optional, Tuple

# .env ファイルの自動読み込み
def load_env_file(filepath: str = ".env") -> None:
    """Load environment variables from .env if python-dotenv is not installed."""
    try:
        from dotenv import load_dotenv
        load_dotenv(filepath)
    except ImportError:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key not in os.environ:
                        os.environ[key] = val

load_env_file()

# テスト用入力文（領収書発行＝billing期待）
SAMPLE_INPUT = "先月分の領収書を再発行してほしいのですが、管理画面のどこからダウンロードできますか？"
TASK_QUESTION = "このユーザー問い合わせの主目的を分類してください"
TASK_OPTIONS = {
    "billing": "料金・請求・見積もり",
    "contract": "契約更新・プラン変更・解約手続き",
    "technical": "操作方法・不具合・エラー報告",
    "other": "どれにも該当しない、または判断が困難",
}


def send_http_post(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float = 15.0) -> Tuple[int, Any, float, Optional[str]]:
    """
    POSTリクエストを送信し、(status_code, response_data, latency_ms, error_message) を返却する。
    """
    start_time = time.perf_counter()

    try:
        import requests
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            lat_ms = round((time.perf_counter() - start_time) * 1000, 2)
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            err = None if resp.status_code == 200 else f"HTTP {resp.status_code}: {resp.text[:300]}"
            return resp.status_code, body, lat_ms, err
        except requests.exceptions.Timeout:
            lat_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return 0, None, lat_ms, f"接続タイムアウト ({timeout}秒を超過しました)"
        except requests.exceptions.RequestException as e:
            lat_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return 0, None, lat_ms, f"リクエスト例外: {str(e)}"
    except ImportError:
        import urllib.error
        import urllib.request
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                lat_ms = round((time.perf_counter() - start_time) * 1000, 2)
                res_body = response.read().decode("utf-8")
                try:
                    body = json.loads(res_body)
                except Exception:
                    body = res_body
                return response.status, body, lat_ms, None
        except urllib.error.HTTPError as e:
            lat_ms = round((time.perf_counter() - start_time) * 1000, 2)
            err_body = e.read().decode("utf-8", errors="replace")[:300]
            return e.code, err_body, lat_ms, f"HTTP {e.code}: {err_body}"
        except urllib.error.URLError as e:
            lat_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return 0, None, lat_ms, f"URLエラー: {e.reason}"
        except TimeoutError:
            lat_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return 0, None, lat_ms, f"接続タイムアウト ({timeout}秒を超過しました)"


def normalize_endpoint_url(url: str, default_path: str = "/v1/systemone") -> str:
    """
    エンドポイントURLを正規化する。
    - 詳細タブの完全URL (末尾 /v1/systemone)
    - SDKサンプルコードの base_url (末尾 /providers/microsoft 等)
    - 旧来の /v1/decision
    のいずれが設定されていても、自動的に正しい REST API エンドポイントに統一する。
    """
    clean_url = url.strip().rstrip("/")
    if not clean_url:
        return ""
    if clean_url.endswith("/v1/decision"):
        return clean_url.replace("/v1/decision", default_path)
    if clean_url.endswith(default_path):
        return clean_url
    return f"{clean_url}{default_path}"


def test_jev() -> bool:
    print("\n" + "=" * 65)
    print("  [1/2] TypeSafe Jev API 接続診断")
    print("=" * 65)

    raw_url = os.getenv("JEV_API_URL", "https://api.typesafe.ai/v1/systemone").strip()
    api_url = normalize_endpoint_url(raw_url)
    api_key = os.getenv("JEV_API_KEY", "").strip()
    model_name = os.getenv("JEV_MODEL_NAME", "jev-latest").strip()

    print(f"入力URL : {raw_url or '(未設定)'}")
    print(f"正規化後: {api_url}")
    print(f"KEY    : {'*' * (len(api_key) - 4) + api_key[-4:] if len(api_key) > 4 else '(未設定)'}")
    print(f"MODEL  : {model_name}")

    if not api_url or not api_key:
        print("\n❌ 診断失敗: JEV_API_URL または JEV_API_KEY が .env に設定されていません。")
        return False

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    payload = {
        "model": model_name,
        "state": SAMPLE_INPUT,
        "questions": {
            "intent": {
                "type": "choice",
                "instructions": TASK_QUESTION,
                "criteria": TASK_OPTIONS,
            }
        },
    }

    print("\n>> リクエスト送信中...")
    status, body, lat_ms, err = send_http_post(api_url, headers, payload)
    print(f">> レイテンシ: {lat_ms} ms")
    print(f">> HTTPステータス: {status}")

    if err:
        print(f"\n❌ エラー発生: {err}")
        return False

    print("\n✅ 接続成功！ 生レスポンス (JSON):")
    if isinstance(body, dict):
        print(json.dumps(body, ensure_ascii=False, indent=2))
    else:
        print(body)
    return True


def test_decision1() -> bool:
    print("\n" + "=" * 65)
    print("  [2/2] Microsoft-Decision-1 (Microsoft Foundry) 接続診断")
    print("=" * 65)

    raw_url = os.getenv("DECISION1_API_URL", "").strip()
    api_url = normalize_endpoint_url(raw_url)
    api_key = os.getenv("DECISION1_API_KEY", "").strip()
    model_name = os.getenv("DECISION1_MODEL_NAME", "decision-1").strip()

    print(f"入力URL : {raw_url or '(未設定)'}")
    print(f"正規化後: {api_url}")
    print(f"KEY    : {'*' * (len(api_key) - 4) + api_key[-4:] if len(api_key) > 4 else '(未設定)'}")
    print(f"MODEL  : {model_name}")

    if not api_url or not api_key:
        print("\n❌ 診断失敗: DECISION1_API_URL または DECISION1_API_KEY が .env に設定されていません。")
        return False

    # Microsoft Foundry は api-key ヘッダーまたは Bearer トークンに対応
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
        "Authorization": f"Bearer {api_key}",
    }

    # System One 規格ペイロード (model 指定を追加)
    payload = {
        "model": model_name,
        "state": SAMPLE_INPUT,
        "questions": {
            "intent": {
                "type": "choice",
                "instructions": TASK_QUESTION,
                "criteria": TASK_OPTIONS,
            }
        },
    }

    print("\n>> リクエスト送信中...")
    status, body, lat_ms, err = send_http_post(api_url, headers, payload)

    print(f">> レイテンシ: {lat_ms} ms")
    print(f">> HTTPステータス: {status}")

    if err:
        print(f"\n❌ エラー発生: {err}")
        return False

    print("\n✅ 接続成功！ 生レスポンス (JSON):")
    if isinstance(body, dict):
        print(json.dumps(body, ensure_ascii=False, indent=2))
    else:
        print(body)
    return True


def main():
    parser = argparse.ArgumentParser(description="Test API connections for Jev and Microsoft-Decision-1.")
    parser.add_argument("--model", choices=["all", "jev", "decision1"], default="all", help="Target model to test (default: all)")
    args = parser.parse_args()

    print("=================================================================")
    print("  System One Model API 接続事前テスト (Pre-flight Check)")
    print("=================================================================")
    print("テスト用問い合わせ: 「先月分の領収書を再発行してほしいのですが...」")

    jev_ok = None
    dec_ok = None

    if args.model in ["all", "jev"]:
        jev_ok = test_jev()

    if args.model in ["all", "decision1"]:
        dec_ok = test_decision1()

    print("\n" + "=" * 65)
    print("  📋 総合接続診断サマリー")
    print("=" * 65)
    if jev_ok is not None:
        print(f"  TypeSafe Jev         : {'✅ 疎通成功' if jev_ok else '❌ 接続失敗'}")
    if dec_ok is not None:
        print(f"  Microsoft-Decision-1 : {'✅ 疎通成功' if dec_ok else '❌ 接続失敗'}")
    print("=" * 65)

    if (jev_ok is True or jev_ok is None) and (dec_ok is True or dec_ok is None):
        print("\n🎉 すべての接続テストに成功しました！")
        print("本番の80問ベンチマークを実行するには以下を実行してください:")
        print("  python3 evaluate_models.py\n")
    else:
        print("\n⚠️ 失敗した項目があります。上記のエラーメッセージおよび .env の設定内容をご確認ください。\n")


if __name__ == "__main__":
    main()

