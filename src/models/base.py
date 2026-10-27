"""
モデルアダプタ抽象基底クラス (src/models/base.py)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

@dataclass
class PredictionResult:
    """単一モデルによる判定結果"""
    model_id: str
    display_name: str
    prediction: str
    confidence: Optional[float] = None
    second_prediction: Optional[str] = None
    margin: Optional[float] = None
    probabilities_summary: str = ""
    latency_ms: float = 0.0
    is_correct: bool = False
    error: Optional[str] = None

class BaseModelAdapter(ABC):
    """すべてのベンチマーク対象モデルの統一インターフェース"""

    def __init__(self, model_id: str, display_name: str):
        self.model_id = model_id
        self.display_name = display_name

    @abstractmethod
    def is_available(self) -> bool:
        """必要な環境変数（URL、キー）が揃っているかを判定する。"""
        pass

    @abstractmethod
    def predict(
        self,
        input_text: str,
        expected: str,
        timeout: float = 15.0,
    ) -> PredictionResult:
        """ユーザー問い合わせを判定し、PredictionResult を返却する。"""
        pass

    @abstractmethod
    def get_mock_prediction(
        self,
        category: str,
        expected: str,
    ) -> PredictionResult:
        """ドライラン（モック）用の検証データを返却する。"""
        pass

