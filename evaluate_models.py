#!/usr/bin/env python3
"""
Jev vs Microsoft-Decision-1 比較検証スクリプト (evaluate_models.py)

概要:
    TypeSafe Jev と Microsoft-Decision-1 の日本語問い合わせ分類タスクにおける
    分類結果・確信度・2位候補・迷い度（Margin）・全選択肢の確率分布・レイテンシを
    同一データセットで比較計測し、results.csv に出力します。

使用方法:
    python3 evaluate_models.py [--data-file data/test_data.json] [--output results.csv] [--dry-run]
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# .env ファイルの自動読み込み (python-dotenv 未インストール環境向けフォールバックあり)
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

# タスク定義定数
TASK_QUESTION = "このユーザー問い合わせの主目的を分類してください"
TASK_OPTIONS = {
    "billing": "料金・請求・見積もり",
    "contract": "契約更新・プラン変更・解約手続き",
    "technical": "操作方法・不具合・エラー報告",
    "other": "どれにも該当しない、または判断が困難",
}
DECISION_TYPE = "choice"

# 環境変数
JEV_API_URL = os.getenv("JEV_API_URL", "").strip()
JEV_API_KEY = os.getenv("JEV_API_KEY", "").strip()

DECISION1_API_URL = os.getenv("DECISION1_API_URL", "").strip()
DECISION1_API_KEY = os.getenv("DECISION1_API_KEY", "").strip()

REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15"))


def parse_confidence(val: Any) -> Optional[float]:
    """確信度数値を抽出し、floatで返却する。"""
    try:
        if val is None:
            return None
        float_val = float(val)
        return round(float_val, 3)
    except (ValueError, TypeError):
        return None


def extract_prediction_metrics(data: Any) -> Tuple[str, Optional[float], Optional[str], Optional[float], str]:
    """
    APIレスポンスから以下の指標を抽出して返却する。
    戻り値: (top_result, top_confidence, second_result, margin, probabilities_summary)
    """
    if not isinstance(data, dict):
        return str(data), None, None, None, ""

    top_result: Optional[str] = None
    top_conf: Optional[float] = None
    second_result: Optional[str] = None
    margin: Optional[float] = None
    probs_summary: str = ""

    # 1. 確率辞書 (probabilities / scores / class_probabilities) の探索
    probs_dict: Dict[str, float] = {}
    for probs_key in ["probabilities", "scores", "probs", "class_probabilities"]:
        if probs_key in data and isinstance(data[probs_key], dict):
            for k, v in data[probs_key].items():
                parsed_v = parse_confidence(v)
                if parsed_v is not None:
                    probs_dict[k] = parsed_v
            if probs_dict:
                break
        elif probs_key in data and isinstance(data[probs_key], list):
            # リスト形式 [{"label": "billing", "probability": 0.95}, ...]
            list_obj = data[probs_key]
            if all(isinstance(x, dict) for x in list_obj):
                for item in list_obj:
                    lbl = item.get("label", item.get("id", item.get("choice", "")))
                    score = parse_confidence(item.get("probability", item.get("score", item.get("prob"))))
                    if lbl and score is not None:
                        probs_dict[str(lbl)] = score
                if probs_dict:
                    break

    # 2. 確率辞書が取得できた場合の詳細計算（1位、2位、マージン、サマリー）
    if probs_dict:
        sorted_items = sorted(probs_dict.items(), key=lambda x: x[1], reverse=True)
        top_result, top_conf = sorted_items[0]
        if len(sorted_items) > 1:
            second_result, sec_conf = sorted_items[1]
            margin = round(top_conf - sec_conf, 3)
        probs_summary = " | ".join(f"{k}:{v:.3f}" for k, v in sorted_items)

    # 3. 確率辞書がない場合のフォールバック（単一フィールドからの抽出）
    if not top_result:
        for key in ["result", "prediction", "choice", "label", "output", "category", "decision"]:
            if key in data and data[key]:
                top_result = str(data[key])
                break

    if not top_result and "choices" in data and isinstance(data["choices"], list) and len(data["choices"]) > 0:
        first_choice = data["choices"][0]
        if isinstance(first_choice, dict):
            if "message" in first_choice and isinstance(first_choice["message"], dict):
                top_result = str(first_choice["message"].get("content", "")).strip()
            elif "text" in first_choice:
                top_result = str(first_choice.get("text", "")).strip()

    if top_conf is None:
        for conf_key in ["confidence", "probability", "score", "prob"]:
            if conf_key in data:
                top_conf = parse_confidence(data[conf_key])
                if top_conf is not None:
                    break

    if not probs_summary and top_result:
        conf_repr = f":{top_conf:.3f}" if top_conf is not None else ""
        probs_summary = f"{top_result}{conf_repr}"

    return (top_result or "unknown", top_conf, second_result, margin, probs_summary)


def check_is_expected(result: str, expected: str) -> Optional[bool]:
    """
    モデルの判定結果が期待値（Expected）を満たしているかを検証する。
    Expected に 'technical or billing' のように複数候補が記載されている場合も判定可能。
    """
    if not result or result.startswith("SKIPPED") or result.startswith("ERROR"):
        return None

    res_clean = result.strip().lower()
    exp_clean = expected.strip().lower()

    # "or", "または", カンマ等で期待値トークンを分割
    tokens = [t.strip() for t in re.split(r'\s+or\s+|\s*,\s*|\s*または\s*', exp_clean) if t.strip()]
    return res_clean in tokens


def call_api(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout: float
) -> Tuple[Optional[Dict[str, Any]], Optional[float], Optional[str]]:
    """
    requests または urllib を用いてPOSTリクエストを送信し、(レスポンスJSON, レイテンシms, エラー文字列) を返却する。
    """
    start_time = time.perf_counter()

    try:
        import requests
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if resp.status_code != 200:
                return None, latency_ms, f"HTTP_{resp.status_code}: {resp.text[:100]}"
            return resp.json(), latency_ms, None
        except requests.exceptions.Timeout:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, latency_ms, f"TIMEOUT ({timeout}s)"
        except requests.exceptions.RequestException as e:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, latency_ms, f"REQUEST_ERROR: {str(e)[:100]}"
        except json.JSONDecodeError:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, latency_ms, "INVALID_JSON_RESPONSE"
    except ImportError:
        import urllib.error
        import urllib.request
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                res_body = response.read().decode("utf-8")
                return json.loads(res_body), latency_ms, None
        except urllib.error.HTTPError as e:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, latency_ms, f"HTTP_{e.code}: {e.reason}"
        except urllib.error.URLError as e:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, latency_ms, f"URL_ERROR: {str(e.reason)[:100]}"
        except TimeoutError:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, latency_ms, f"TIMEOUT ({timeout}s)"
        except json.JSONDecodeError:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, latency_ms, "INVALID_JSON_RESPONSE"


def get_mock_metrics_for_category(category: str, expected: str, is_decision1: bool = False) -> Dict[str, Any]:
    """ドライラン時にリアルな検証ダミー指標を生成する。"""
    # 期待値から主目的を取得
    first_exp = [t.strip() for t in re.split(r'\s+or\s+|\s*,\s*|\s*または\s*', expected.lower()) if t.strip()][0]

    if "Category A" in category:
        top_res = first_exp
        sec_res = "other" if first_exp != "other" else "technical"
        top_c = 0.945 if not is_decision1 else 0.932
        sec_c = 0.035 if not is_decision1 else 0.045
        lat = 125.40 if not is_decision1 else 142.10
    elif "Category B" in category:
        top_res = first_exp
        sec_res = "billing" if first_exp != "billing" else "contract"
        top_c = 0.528 if not is_decision1 else 0.575
        sec_c = 0.412 if not is_decision1 else 0.365
        lat = 138.20 if not is_decision1 else 155.60
    elif "Category C" in category:
        top_res = first_exp
        sec_res = "contract" if first_exp != "contract" else "billing"
        top_c = 0.820 if not is_decision1 else 0.765
        sec_c = 0.130 if not is_decision1 else 0.180
        lat = 145.80 if not is_decision1 else 168.30
    else:  # Category D
        top_res = "other"
        sec_res = "technical"
        top_c = 0.970 if not is_decision1 else 0.958
        sec_c = 0.018 if not is_decision1 else 0.024
        lat = 112.50 if not is_decision1 else 130.80

    margin = round(top_c - sec_c, 3)
    rem_c = round(max(0.0, 1.0 - top_c - sec_c) / 2, 3)
    probs_str = f"{top_res}:{top_c:.3f} | {sec_res}:{sec_c:.3f} | other:{rem_c:.3f}"

    return {
        "result": top_res,
        "confidence": f"{top_c:.3f}",
        "margin": f"{margin:.3f}",
        "second_result": sec_res,
        "probabilities": probs_str,
        "latency_ms": f"{lat:.2f}"
    }


def evaluate_jev(input_text: str, category: str = "", expected: str = "", dry_run: bool = False) -> Dict[str, str]:
    """
    TypeSafe Jev モデルの評価を実行する。
    戻り値: {result, confidence, margin, second_result, probabilities, latency_ms}
    """
    if dry_run:
        return get_mock_metrics_for_category(category, expected, is_decision1=False)

    if not JEV_API_URL or not JEV_API_KEY:
        return {
            "result": "SKIPPED: Missing JEV_API_URL or JEV_API_KEY",
            "confidence": "",
            "margin": "",
            "second_result": "",
            "probabilities": "",
            "latency_ms": ""
        }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {JEV_API_KEY}",
    }

    payload = {
        "type": DECISION_TYPE,
        "question": TASK_QUESTION,
        "input": input_text,
        "options": [
            {"id": key, "description": desc}
            for key, desc in TASK_OPTIONS.items()
        ]
    }

    data, latency_ms, err = call_api(JEV_API_URL, headers, payload, REQUEST_TIMEOUT_SECONDS)
    lat_str = str(latency_ms) if latency_ms is not None else ""

    if err:
        return {
            "result": f"ERROR: {err}",
            "confidence": "",
            "margin": "",
            "second_result": "",
            "probabilities": "",
            "latency_ms": lat_str
        }

    top_res, top_conf, sec_res, margin, probs_summary = extract_prediction_metrics(data)
    return {
        "result": top_res,
        "confidence": f"{top_conf:.3f}" if top_conf is not None else "",
        "margin": f"{margin:.3f}" if margin is not None else "",
        "second_result": sec_res or "",
        "probabilities": probs_summary,
        "latency_ms": lat_str
    }


def evaluate_decision1(input_text: str, category: str = "", expected: str = "", dry_run: bool = False) -> Dict[str, str]:
    """
    Microsoft-Decision-1 モデルの評価を実行する。
    戻り値: {result, confidence, margin, second_result, probabilities, latency_ms}
    """
    if dry_run:
        return get_mock_metrics_for_category(category, expected, is_decision1=True)

    if not DECISION1_API_URL or not DECISION1_API_KEY:
        return {
            "result": "SKIPPED: Missing DECISION1_API_URL or DECISION1_API_KEY",
            "confidence": "",
            "margin": "",
            "second_result": "",
            "probabilities": "",
            "latency_ms": ""
        }

    headers = {
        "Content-Type": "application/json",
        "api-key": DECISION1_API_KEY,
        "Authorization": f"Bearer {DECISION1_API_KEY}",
    }

    payload = {
        "type": DECISION_TYPE,
        "question": TASK_QUESTION,
        "input_text": input_text,
        "options": TASK_OPTIONS,
    }

    data, latency_ms, err = call_api(DECISION1_API_URL, headers, payload, REQUEST_TIMEOUT_SECONDS)
    lat_str = str(latency_ms) if latency_ms is not None else ""

    if err:
        return {
            "result": f"ERROR: {err}",
            "confidence": "",
            "margin": "",
            "second_result": "",
            "probabilities": "",
            "latency_ms": lat_str
        }

    top_res, top_conf, sec_res, margin, probs_summary = extract_prediction_metrics(data)
    return {
        "result": top_res,
        "confidence": f"{top_conf:.3f}" if top_conf is not None else "",
        "margin": f"{margin:.3f}" if margin is not None else "",
        "second_result": sec_res or "",
        "probabilities": probs_summary,
        "latency_ms": lat_str
    }


def generate_summary(csv_file: str) -> None:
    """
    results.csv または benchmark_results.csv を読み込み、
    カテゴリ別の正解率・平均レイテンシ・確信度・モデル間一致率を集計して表示する。
    """
    if not os.path.exists(csv_file):
        print(f"Error: CSV file not found for summary: {csv_file}")
        return

    with open(csv_file, "r", encoding="utf-8-sig") as f:
        reader = list(csv.DictReader(f))

    if not reader:
        print(f"Warning: CSV file is empty: {csv_file}")
        return

    print("\n" + "=" * 78)
    print("  📊 BENCHMARK SUMMARY REPORT (Jev vs Microsoft-Decision-1)")
    print("=" * 78)
    print(f"Source CSV : {csv_file}")
    print(f"Total Cases: {len(reader)}\n")

    # カテゴリ別集計用
    categories: Dict[str, List[Dict[str, Any]]] = {}
    for r in reader:
        cat = r.get("Category", "Unknown")
        categories.setdefault(cat, []).append(r)

    # 1. カテゴリ別 正解率・速度・確信度 サマリーテーブル (Markdown形式)
    print("### 1. カテゴリ別 総合パフォーマンス比較")
    print("| カテゴリ | 件数 | Jev正解率 | Dec1正解率 | Jev平均速度 | Dec1平均速度 | Jev平均確信度 | Dec1平均確信度 | 一致率 |")
    print("|---|---|---|---|---|---|---|---|---|")

    total_jev_correct = 0
    total_dec_correct = 0
    total_valid_cases = 0
    total_agree = 0
    all_jev_latencies: List[float] = []
    all_dec_latencies: List[float] = []

    for cat, rows in categories.items():
        n = len(rows)
        jev_correct = sum(1 for r in rows if r.get("Jev_Is_Expected") == "TRUE")
        dec_correct = sum(1 for r in rows if r.get("Decision1_Is_Expected") == "TRUE")
        agree_cnt = sum(1 for r in rows if r.get("Models_Agree") == "TRUE")

        jev_lats = [float(r["Jev_Latency_ms"]) for r in rows if r.get("Jev_Latency_ms") and r["Jev_Latency_ms"] != ""]
        dec_lats = [float(r["Decision1_Latency_ms"]) for r in rows if r.get("Decision1_Latency_ms") and r["Decision1_Latency_ms"] != ""]
        jev_confs = [float(r["Jev_Confidence"]) for r in rows if r.get("Jev_Confidence") and r["Jev_Confidence"] != ""]
        dec_confs = [float(r["Decision1_Confidence"]) for r in rows if r.get("Decision1_Confidence") and r["Decision1_Confidence"] != ""]

        avg_j_lat = f"{sum(jev_lats)/len(jev_lats):.1f}ms" if jev_lats else "N/A"
        avg_d_lat = f"{sum(dec_lats)/len(dec_lats):.1f}ms" if dec_lats else "N/A"
        avg_j_conf = f"{sum(jev_confs)/len(jev_confs):.3f}" if jev_confs else "N/A"
        avg_d_conf = f"{sum(dec_confs)/len(dec_confs):.3f}" if dec_confs else "N/A"

        j_acc = f"{(jev_correct / n) * 100:.1f}% ({jev_correct}/{n})"
        d_acc = f"{(dec_correct / n) * 100:.1f}% ({dec_correct}/{n})"
        agree_pct = f"{(agree_cnt / n) * 100:.1f}%"

        print(f"| {cat} | {n} | {j_acc} | {d_acc} | {avg_j_lat} | {avg_d_lat} | {avg_j_conf} | {avg_d_conf} | {agree_pct} |")

        total_jev_correct += jev_correct
        total_dec_correct += dec_correct
        total_valid_cases += n
        total_agree += agree_cnt
        all_jev_latencies.extend(jev_lats)
        all_dec_latencies.extend(dec_lats)

    overall_j_acc = f"{(total_jev_correct / total_valid_cases) * 100:.1f}%" if total_valid_cases else "N/A"
    overall_d_acc = f"{(total_dec_correct / total_valid_cases) * 100:.1f}%" if total_valid_cases else "N/A"
    overall_j_lat = f"{sum(all_jev_latencies) / len(all_jev_latencies):.1f}ms" if all_jev_latencies else "N/A"
    overall_d_lat = f"{sum(all_dec_latencies) / len(all_dec_latencies):.1f}ms" if all_dec_latencies else "N/A"
    overall_agree = f"{(total_agree / total_valid_cases) * 100:.1f}%" if total_valid_cases else "N/A"

    print(f"| **全体平均** | **{total_valid_cases}** | **{overall_j_acc}** | **{overall_d_acc}** | **{overall_j_lat}** | **{overall_d_lat}** | - | - | **{overall_agree}** |")
    print()

    # 2. 意見が割れた問題（激論ケース）のピックアップ
    disagree_cases = [r for r in reader if r.get("Models_Agree") == "FALSE"]
    print(f"### 2. 意見が割れた注目ケース (Models_Agree = FALSE) : 計 {len(disagree_cases)} 件")
    if disagree_cases:
        print("| ID | カテゴリ | 期待値 | Jev判定 (確信度) | Decision-1判定 (確信度) | 入力文 |")
        print("|---|---|---|---|---|---|")
        for d in disagree_cases:
            inp = d.get("Input_Text", "")
            inp_short = (inp[:40] + "...") if len(inp) > 40 else inp
            j_eval = f"{d.get('Jev_Result', '')} ({d.get('Jev_Confidence', '')})"
            d_eval = f"{d.get('Decision1_Result', '')} ({d.get('Decision1_Confidence', '')})"
            print(f"| {d.get('ID')} | {d.get('Category')} | {d.get('Expected')} | {j_eval} | {d_eval} | {inp_short} |")
    else:
        print("（両モデルの判定が全件一致、または未評価です）")
    print("=" * 78 + "\n")


def load_test_data(file_path: str) -> list:
    """テストケースJSONファイルを読み込む。"""
    if not os.path.exists(file_path):
        alt_path = os.path.join("data", os.path.basename(file_path))
        if os.path.exists(alt_path):
            file_path = alt_path
        else:
            raise FileNotFoundError(f"Test data file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Evaluate TypeSafe Jev vs Microsoft-Decision-1 on Japanese query classification.")
    parser.add_argument("--data-file", default="data/test_data.json", help="Path to test cases JSON file (default: data/test_data.json)")
    parser.add_argument("--output", default="results.csv", help="Path to output CSV file (default: results.csv)")
    parser.add_argument("--dry-run", action="store_true", help="Run without sending real API requests (for structure and format verification)")
    parser.add_argument("--summary", nargs="?", const="results.csv", default=None, help="Generate performance summary from a results CSV file")
    args = parser.parse_args()

    # --summary オプション単体実行の場合
    if args.summary:
        target_csv = args.summary
        if not os.path.exists(target_csv):
            # fallback search
            for candidate in ["results.csv", "data/benchmark_results.csv"]:
                if os.path.exists(candidate):
                    target_csv = candidate
                    break
        generate_summary(target_csv)
        return

    print("=================================================================")
    print("  Jev vs Microsoft-Decision-1 Benchmark Runner (Enhanced)")
    print("=================================================================")
    print(f"Test Data Path: {args.data_file}")
    print(f"Output CSV    : {args.output}")
    print(f"Dry Run Mode  : {'ENABLED (Mock Data)' if args.dry_run else 'DISABLED (Real API Calls)'}")
    print("-----------------------------------------------------------------")

    jev_status = "SET" if JEV_API_KEY else "NOT SET (will be skipped)"
    dec_status = "SET" if DECISION1_API_KEY else "NOT SET (will be skipped)"
    print(f"JEV API URL       : {JEV_API_URL or '(not set)'}")
    print(f"JEV API Key       : {jev_status}")
    print(f"Decision-1 API URL: {DECISION1_API_URL or '(not set)'}")
    print(f"Decision-1 API Key: {dec_status}")
    print("=================================================================\n")

    test_cases = load_test_data(args.data_file)
    print(f"Loaded {len(test_cases)} test cases.\n")

    csv_headers = [
        "ID",
        "Category",
        "Input_Text",
        "Input_Length",
        "Expected",
        "Models_Agree",
        "Jev_Result",
        "Jev_Is_Expected",
        "Jev_Confidence",
        "Jev_Margin",
        "Jev_Second_Result",
        "Jev_Probabilities",
        "Jev_Latency_ms",
        "Decision1_Result",
        "Decision1_Is_Expected",
        "Decision1_Confidence",
        "Decision1_Margin",
        "Decision1_Second_Result",
        "Decision1_Probabilities",
        "Decision1_Latency_ms",
    ]

    results = []

    for idx, case in enumerate(test_cases, 1):
        cid = case.get("id", f"case-{idx}")
        category = case.get("category", "")
        input_text = case.get("input_text", "")
        expected = case.get("expected", "")
        input_len = len(input_text)

        print(f"[{idx}/{len(test_cases)}] Evaluating {cid} ({category})...")
        print(f"  Input: {input_text}")
        print(f"  Expected: {expected}")

        # Jev 評価
        jev = evaluate_jev(input_text, category=category, expected=expected, dry_run=args.dry_run)
        jev_is_exp = check_is_expected(jev["result"], expected)
        jev_is_exp_str = str(jev_is_exp).upper() if jev_is_exp is not None else ""
        print(f"  -> Jev: result={jev['result']}, conf={jev['confidence']}, margin={jev['margin']}, lat={jev['latency_ms']}ms")

        # Decision-1 評価
        dec = evaluate_decision1(input_text, category=category, expected=expected, dry_run=args.dry_run)
        dec_is_exp = check_is_expected(dec["result"], expected)
        dec_is_exp_str = str(dec_is_exp).upper() if dec_is_exp is not None else ""
        print(f"  -> Decision-1: result={dec['result']}, conf={dec['confidence']}, margin={dec['margin']}, lat={dec['latency_ms']}ms")

        # 2モデルの一致判定
        if jev["result"] and dec["result"] and not jev["result"].startswith(("SKIPPED", "ERROR")) and not dec["result"].startswith(("SKIPPED", "ERROR")):
            models_agree_str = "TRUE" if jev["result"] == dec["result"] else "FALSE"
        else:
            models_agree_str = ""

        print(f"  -> Agree: {models_agree_str or 'N/A'}, Jev_OK: {jev_is_exp_str or 'N/A'}, Dec1_OK: {dec_is_exp_str or 'N/A'}\n")

        results.append({
            "ID": cid,
            "Category": category,
            "Input_Text": input_text,
            "Input_Length": input_len,
            "Expected": expected,
            "Models_Agree": models_agree_str,
            "Jev_Result": jev["result"],
            "Jev_Is_Expected": jev_is_exp_str,
            "Jev_Confidence": jev["confidence"],
            "Jev_Margin": jev["margin"],
            "Jev_Second_Result": jev["second_result"],
            "Jev_Probabilities": jev["probabilities"],
            "Jev_Latency_ms": jev["latency_ms"],
            "Decision1_Result": dec["result"],
            "Decision1_Is_Expected": dec_is_exp_str,
            "Decision1_Confidence": dec["confidence"],
            "Decision1_Margin": dec["margin"],
            "Decision1_Second_Result": dec["second_result"],
            "Decision1_Probabilities": dec["probabilities"],
            "Decision1_Latency_ms": dec["latency_ms"],
        })

    # CSV 出力 (UTF-8 with BOM)
    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(results)

    print(f"Evaluation complete. Results saved to '{args.output}'.")

    # 実行完了後に自動でサマリーレポートを出力
    generate_summary(args.output)


if __name__ == "__main__":
    main()
