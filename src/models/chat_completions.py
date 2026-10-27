"""
Chat Completions (GPT-5 / GPT-5-mini) アダプタ (src/models/chat_completions.py)
一般的な生成LLM（System 2）による意図分類を制御します。
"""

import json
import os
import re
from typing import Any, Dict, Optional

from src.client import send_post_request
from src.config import LLM_SYSTEM_PROMPT, TASK_OPTIONS, normalize_chat_endpoint
from src.models.base import BaseModelAdapter, PredictionResult

class ChatCompletionsAdapter(BaseModelAdapter):
    """OpenAI / Azure Foundry Chat Completions 専用アダプタ"""

    def __init__(
        self,
        model_id: str,
        display_name: str,
        env_url_key: str,
        env_api_key: str,
        env_deployment_key: str,
        default_deployment_name: str,
    ):
        super().__init__(model_id, display_name)
        raw_url = os.getenv(env_url_key, "")
        self.deployment_name = os.getenv(env_deployment_key, default_deployment_name).strip()
        self.endpoint_url = normalize_chat_endpoint(raw_url, self.deployment_name)
        self.api_key = os.getenv(env_api_key, "").strip()

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
            "api-key": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
        }

        # temperature は指定せずデフォルト（1）を採用（GPT-5仕様準拠）
        payload = {
            "model": self.deployment_name,
            "messages": [
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": f"問い合わせ内容:\n{input_text}"},
            ],
            "response_format": {"type": "json_object"},
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

        try:
            content = data["choices"][0]["message"]["content"].strip()
            parsed = json.loads(content)
            intent = parsed.get("intent", "").strip().lower()

            valid_intents = set(TASK_OPTIONS.keys())
            if intent not in valid_intents:
                return PredictionResult(
                    model_id=self.model_id,
                    display_name=self.display_name,
                    prediction=intent or "SCHEMA_ERROR",
                    latency_ms=latency_ms or 0.0,
                    error=f"Invalid intent returned: '{intent}'",
                )

            is_correct = self._check_is_correct(intent, expected)

            return PredictionResult(
                model_id=self.model_id,
                display_name=self.display_name,
                prediction=intent,
                confidence=None,  # Chat Completions では確率分布は出力されない
                second_prediction=None,
                margin=None,
                probabilities_summary="N/A (System 2 LLM)",
                latency_ms=latency_ms or 0.0,
                is_correct=is_correct,
                error=None,
            )

        except Exception as e:
            return PredictionResult(
                model_id=self.model_id,
                display_name=self.display_name,
                prediction="PARSE_ERROR",
                latency_ms=latency_ms or 0.0,
                error=f"JSONDecodeError: {str(e)}",
            )

    def _check_is_correct(self, prediction: str, expected: str) -> bool:
        pred = (prediction or "").strip().lower()
        if not pred:
            return False
        tokens = [t.strip().lower() for t in re.split(r'\s+or\s+|\s*,\s*|\s*または\s*', expected) if t.strip()]
        return any(pred == t for t in tokens)

    def get_mock_prediction(self, category: str, expected: str) -> PredictionResult:
        first_exp = [t.strip() for t in re.split(r'\s+or\s+|\s*,\s*|\s*または\s*', expected.lower()) if t.strip()][0]
        is_mini = "mini" in self.model_id.lower()
        lat = 850.0 if is_mini else 1650.0

        return PredictionResult(
            model_id=self.model_id,
            display_name=self.display_name,
            prediction=first_exp,
            confidence=None,
            second_prediction=None,
            margin=None,
            probabilities_summary="N/A (System 2 LLM)",
            latency_ms=lat,
            is_correct=True,
            error=None,
        )
