"""
共通通信・計測定規クライアント (src/client.py)
Jev, Decision-1, GPT-5, GPT-5-mini のすべてのモデルが
完全に同一のHTTP POST通信・高精度ミリ秒タイマー（time.perf_counter）定規で計測されることを保証します。
"""

import json
import time
from typing import Any, Dict, Optional, Tuple

def send_post_request(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout: float = 15.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[float], Optional[str]]:
    """
    POSTリクエストを送信し、高精度にレイテンシを計測する。
    戻り値: (response_json, latency_ms, error_string)
    """
    start_time = time.perf_counter()

    # 1. requests が利用可能な場合は requests を優先使用
    try:
        import requests
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if resp.status_code != 200:
                return None, latency_ms, f"HTTP_{resp.status_code}: {resp.text[:200]}"
            return resp.json(), latency_ms, None
        except requests.exceptions.Timeout:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, latency_ms, f"TIMEOUT ({timeout}s)"
        except requests.exceptions.RequestException as e:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, latency_ms, f"REQUEST_ERROR: {str(e)[:150]}"
        except json.JSONDecodeError:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, latency_ms, "INVALID_JSON_RESPONSE"

    # 2. requests 未インストール環境向けの標準 urllib フォールバック
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
            err_body = e.read().decode("utf-8", errors="ignore")[:200]
            return None, latency_ms, f"HTTP_{e.code}: {err_body}"
        except urllib.error.URLError as e:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, latency_ms, f"URL_ERROR: {str(e.reason)[:150]}"
        except TimeoutError:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, latency_ms, f"TIMEOUT ({timeout}s)"
        except json.JSONDecodeError:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return None, latency_ms, "INVALID_JSON_RESPONSE"
