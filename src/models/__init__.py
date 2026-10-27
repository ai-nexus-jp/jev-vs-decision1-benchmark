"""
モデル管理パッケージ (src/models/__init__.py)
ベンチマーク対象の全モデルを登録・提供します。
"""

from typing import Dict, List, Optional

from src.models.base import BaseModelAdapter
from src.models.chat_completions import ChatCompletionsAdapter
from src.models.system_one import SystemOneAdapter

def get_all_registered_models() -> Dict[str, BaseModelAdapter]:
    """登録されているすべてのモデルアダプタを返却する。"""
    return {
        "jev": SystemOneAdapter(
            model_id="jev",
            display_name="TypeSafe Jev",
            env_url_key="JEV_API_URL",
            env_api_key="JEV_API_KEY",
            default_model_name="jev-latest",
        ),
        "decision1": SystemOneAdapter(
            model_id="decision1",
            display_name="Microsoft-Decision-1",
            env_url_key="DECISION1_API_URL",
            env_api_key="DECISION1_API_KEY",
            default_model_name="decision-1",
        ),
        "gpt5": ChatCompletionsAdapter(
            model_id="gpt5",
            display_name="GPT-5 (主力)",
            env_url_key="GPT5_API_URL",
            env_api_key="GPT5_API_KEY",
            env_deployment_key="GPT5_DEPLOYMENT_NAME",
            default_deployment_name="gpt-5",
        ),
        "gpt5_mini": ChatCompletionsAdapter(
            model_id="gpt5_mini",
            display_name="GPT-5-mini (最小)",
            env_url_key="GPT5_MINI_API_URL",
            env_api_key="GPT5_MINI_API_KEY",
            env_deployment_key="GPT5_MINI_DEPLOYMENT_NAME",
            default_deployment_name="gpt-5-mini",
        ),
    }

def get_active_models(requested_ids: Optional[List[str]] = None) -> List[BaseModelAdapter]:
    """
    指定されたID（または利用可能な全モデル）のアダプタ一覧を返却する。
    requested_ids が None または 'all' の場合は、環境変数が設定されているモデルをすべて返す。
    """
    all_models = get_all_registered_models()
    
    if not requested_ids or "all" in requested_ids:
        # 有効なモデルをすべて選択
        active = [m for m in all_models.values() if m.is_available()]
        return active if active else list(all_models.values())
    
    selected = []
    for mid in requested_ids:
        clean_id = mid.strip().lower()
        if clean_id in all_models:
            selected.append(all_models[clean_id])
    return selected
