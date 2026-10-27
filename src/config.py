"""
ベンチマーク共通設定モジュール (src/config.py)
- 環境変数 (.env) の安全な読み込み
- エンドポイントURLの自動正規化
- タスク定義（4分類・選択肢マッピング・プロンプト定数）
"""

import os
from typing import Dict

def load_env_file(filepath: str = ".env") -> None:
    """環境変数ファイル（.env）を読み込む。python-dotenv非依存フォールバック付き。"""
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

def normalize_system_one_url(url: str, default_path: str = "/v1/systemone") -> str:
    """System One (Jev / Decision-1) エンドポイントURLを正規化する。"""
    clean_url = url.strip().rstrip("/")
    if not clean_url:
        return ""
    if clean_url.endswith("/v1/decision"):
        return clean_url.replace("/v1/decision", default_path)
    if clean_url.endswith(default_path):
        return clean_url
    return f"{clean_url}{default_path}"

def normalize_chat_endpoint(url: str, deployment_name: str) -> str:
    """Chat Completions (Azure OpenAI / Foundry) エンドポイントURLを正規化する。"""
    clean_url = url.strip().rstrip("/")
    if not clean_url:
        return ""
    if "/chat/completions" in clean_url:
        return clean_url
    if "openai.azure.com" in clean_url:
        return f"{clean_url}/openai/deployments/{deployment_name}/chat/completions?api-version=2024-08-01-preview"
    if "models.ai.azure.com" in clean_url or "services.ai.azure.com" in clean_url:
        return f"{clean_url}/chat/completions"
    return f"{clean_url}/chat/completions"

# 4分類タスク定義
TASK_QUESTION = "このユーザー問い合わせの主目的を分類してください"
TASK_OPTIONS: Dict[str, str] = {
    "billing": "料金・請求・見積もり",
    "contract": "契約更新・プラン変更・解約手続き",
    "technical": "操作方法・不具合・エラー報告",
    "other": "どれにも該当しない、または判断が困難",
}

# Chat Completions (LLM) 向けシステムプロンプト
_options_text = "\n".join(f"- {k}: {v}" for k, v in TASK_OPTIONS.items())
_options_union = " | ".join(f'"{k}"' for k in TASK_OPTIONS.keys())

LLM_SYSTEM_PROMPT = f"""あなたはユーザー問い合わせの主目的を正確に分類するAIです。
以下の選択肢から最も適切なものを1つだけ選び、JSON形式で回答してください。

【選択肢】
{_options_text}

【出力形式】
必ず以下のJSON形式のみを出力してください（Markdownコードブロックや前置き、解説は不要です）:
{{"intent": {_options_union}}}
"""

REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15"))
