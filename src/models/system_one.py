"""
System One (Jev / Microsoft-Decision-1) アダプタ (src/models/system_one.py)
判断特化型（choice 選択肢配列・Margin・全選択肢確率分布）モデルを制御します。
"""

import os
import re
from typing import Any, Dict, Optional, Tuple

from src.client import send_post_request
from src.config import TASK_OPTIONS, TASK_QUESTION, normalize_system_one_url
from src.models.base import BaseModelAdapter, PredictionResult

class SystemOneAdapter(BaseModelAdapter):
    """TypeSafe Jev および Microsoft-Decision-1 専用アダプタ"""

    def __init__(
        self,
        model_id: str,
        display_name: str,
        env_url_key: str,
        env_api_key: str,
        default_model_name: str,
    ):
        super().__init__(model_id, display_name)
        raw_url = os.getenv(env_url_key, "")
        self.endpoint_url = normalize_system_one_url(raw_url)
        self.api_key = os.getenv(env_api_key, "").strip()
        self.model_name = os.getenv(f"{model_id.upper()}_MODEL_NAME", default_model_name).strip()

    def is_available(self) -> bool:
        return bool(self.endpoint_url and self.api_key)

    def predict(
        self,
        input_text: str,
        expected: str,
        timeout: float = 15.0,
    ) -> PredictionResult:
        if not self.is_available():
            return PredictionResult(
                model_id=self.model_id,
                display_name=self.display_name,
                prediction="SKIPPED",
                error="Environment variables (URL or KEY) not configured",
            )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "api-key": self.api_key,
        }

        # System One 規格の純粋ペイロード
        payload = {
            "model": self.model_name,
            "state": {
                "user_input": input_text,
            },
            "questions": {
                "intent": {
                    "type": "choice",
                    "instructions": TASK_QUESTION,
                    "criteria": TASK_OPTIONS,
                }
            },
        }

        data, latency_ms, error_msg = send_post_request(
            url=self.endpoint_url,
            headers=headers,
            payload=payload,
            timeout=timeout,
        )

        if error_msg or not data:
            return PredictionResult(
                model_id=self.model_id,
                display_name=self.display_name,
                prediction="ERROR",
                latency_ms=latency_ms or 0.0,
                error=error_msg or "Empty Response",
            )

        # 指標抽出
        top_res, top_conf, sec_res, margin, probs_summary = self._extract_metrics(data)
        is_correct = self._check_is_correct(top_res, expected)

        return PredictionResult(
            model_id=self.model_id,
            display_name=self.display_name,
            prediction=top_res,
            confidence=top_conf,
            second_prediction=sec_res,
            margin=margin,
            probabilities_summary=probs_summary,
            latency_ms=latency_ms or 0.0,
            is_correct=is_correct,
            error=None,
        )

    def _extract_metrics(self, data: Any) -> Tuple[str, Optional[float], Optional[str], Optional[float], str]:
        """System One レスポンスから確率分布、マージン、1位・2位結果を抽出する。"""
        if not isinstance(data, dict):
            return str(data), None, None, None, ""

        top_result = ""
        top_conf = None
        second_result = None
        margin = None
        probs_summary = ""
        probs_dict = {}

        # answers 配列または辞書の解析
        target_dict = data
        if "answers" in data:
            answers = data["answers"]
            if isinstance(answers, dict):
                first_answer = next(iter(answers.values())) if answers else {}
                if isinstance(first_answer, dict):
                    target_dict = first_answer
            elif isinstance(answers, list) and len(answers) > 0 and isinstance(answers[0], dict):
                target_dict = answers[0]

        # 確率辞書の抽出
        for probs_key in ["probabilities", "probs", "probability_distribution"]:
            if probs_key in target_dict and isinstance(target_dict[probs_key], dict):
                for k, v in target_dict[probs_key].items():
                    try:
                        probs_dict[k] = round(float(v), 3)
                    except (ValueError, TypeError):
                        pass
                if probs_dict:
                    break

        if probs_dict:
            sorted_items = sorted(probs_dict.items(), key=lambda x: x[1], reverse=True)
            top_result, top_conf = sorted_items[0]
            if len(sorted_items) > 1:
                second_result, sec_conf = sorted_items[1]
                margin = round(top_conf - sec_conf, 3)
            probs_summary = " | ".join(f"{k}:{v:.3f}" for k, v in sorted_items)

        # 直接ラベルのフォールバック
        if not top_result:
            for key in ["value", "choice", "result", "prediction", "label"]:
                if key in target_dict and target_dict[key]:
                    top_result = str(target_dict[key]).strip()
                    break

        return top_result or "unknown", top_conf, second_result, margin, probs_summary

    def _check_is_correct(self, prediction: str, expected: str) -> bool:
        """期待値との一致判定（複数許容対応）"""
        pred = (prediction or "").strip().lower()
        if not pred:
            return False
        tokens = [t.strip().lower() for t in re.split(r'\s+or\s+|\s*,\s*|\s*または\s*', expected) if t.strip()]
        return any(pred == t for t in tokens)

    def get_mock_prediction(self, category: str, expected: str) -> PredictionResult:
        first_exp = [t.strip() for t in re.split(r'\s+or\s+|\s*,\s*|\s*または\s*', expected.lower()) if t.strip()][0]
        is_dec = "decision" in self.model_id.lower()
        if "Category A" in category:
            top_c = 0.945 if not is_dec else 0.932
            lat = 210.0 if not is_dec else 315.0
            margin = 0.910 if not is_dec else 0.880
            sec_res = "other"
        elif "Category B" in category:
            top_c = 0.530 if not is_dec else 0.580
            lat = 220.0 if not is_dec else 320.0
            margin = 0.120 if not is_dec else 0.190
            sec_res = "contract" if first_exp == "billing" else "billing"
        elif "Category C" in category:
            top_c = 0.880 if not is_dec else 0.840
            lat = 215.0 if not is_dec else 325.0
            margin = 0.790 if not is_dec else 0.720
            sec_res = "other"
        else:
            top_c = 0.960 if not is_dec else 0.910
            lat = 205.0 if not is_dec else 310.0
            margin = 0.930 if not is_dec else 0.840
            sec_res = "technical"

        return PredictionResult(
            model_id=self.model_id,
            display_name=self.display_name,
            prediction=first_exp,
            confidence=top_c,
            second_prediction=sec_res,
            margin=margin,
            probabilities_summary=f"{first_exp}:{top_c:.3f} | {sec_res}:{(top_c-margin):.3f}",
            latency_ms=lat,
            is_correct=True,
            error=None,
        )
