"""火山方舟 OpenAI 兼容 endpoint（豆包 1.8 vision）。"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class TokenUsage:
    """累计 token 消耗（按 provider 实例累加）。"""
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, *, prompt: int, completion: int, total: int) -> None:
        self.calls += 1
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += total

    def snapshot(self) -> "TokenUsage":
        """返回当前累计值的独立副本，供在某段区间前后取差值（如 per-case 归属）。"""
        return TokenUsage(
            calls=self.calls,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.total_tokens,
        )

    def __sub__(self, other: "TokenUsage") -> "TokenUsage":
        """两个快照相减，得到区间内的增量消耗。"""
        return TokenUsage(
            calls=self.calls - other.calls,
            prompt_tokens=self.prompt_tokens - other.prompt_tokens,
            completion_tokens=self.completion_tokens - other.completion_tokens,
            total_tokens=self.total_tokens - other.total_tokens,
        )


class ArkDoubaoProvider:
    name = "ark_doubao"

    def __init__(self, base_url: str, api_key: str, model: str,
                 *, temperature: float = 0.0, timeout_sec: float = 60.0,
                 max_retries: int = 2, retry_backoff_sec: float = 1.0):
        if not api_key:
            raise ValueError("ArkDoubaoProvider 需要 api_key（请设置 ARK_API_KEY）")
        if not model:
            raise ValueError("ArkDoubaoProvider 需要 model（请设置 ARK_MODEL）")
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout_sec = timeout_sec
        # 网络/瞬时错误的额外重试次数与退避基数（指数退避）；仅对可重试类生效
        self.max_retries = max_retries
        self.retry_backoff_sec = retry_backoff_sec
        self._client = None
        self.usage = TokenUsage()

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key,
                                  timeout=self.timeout_sec)
        return self._client

    def chat(self, messages: list[dict], **kwargs: Any) -> str:
        resp = self._create_with_retry(messages, kwargs)
        self._record_usage(resp)
        return (resp.choices[0].message.content or "").strip()

    def _create_with_retry(self, messages: list[dict], kwargs: dict) -> Any:
        """带指数退避的调用：仅对网络/限流/5xx 等瞬时错误重试；
        认证/参数等业务错误立即抛出，不做无谓重试。"""
        from openai import (APIConnectionError, InternalServerError,
                            RateLimitError)
        retryable = (APIConnectionError, RateLimitError, InternalServerError)

        attempt = 0
        while True:
            try:
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=kwargs.get("temperature", self.temperature),
                    max_tokens=kwargs.get("max_tokens", 512),
                )
            except retryable as e:
                if attempt >= self.max_retries:
                    raise
                delay = self.retry_backoff_sec * (2 ** attempt)
                attempt += 1
                print(f"  ⚠️ LLM 调用瞬时失败（{type(e).__name__}），"
                      f"{delay:.1f}s 后重试（{attempt}/{self.max_retries}）")
                time.sleep(delay)

    def _record_usage(self, resp: Any) -> None:
        u = getattr(resp, "usage", None)
        if u is None:
            return
        self.usage.add(
            prompt=getattr(u, "prompt_tokens", 0) or 0,
            completion=getattr(u, "completion_tokens", 0) or 0,
            total=getattr(u, "total_tokens", 0) or 0,
        )

    @staticmethod
    def user_message_with_image(text: str, image_b64: str) -> dict:
        """组装一条带截图的 user 消息（OpenAI 多模态格式）。"""
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            ],
        }

    @staticmethod
    def user_message_with_images(text: str, images_b64: list[str]) -> dict:
        """组装一条带多张截图的 user 消息（顺序即传入顺序）。"""
        content: list[dict] = [{"type": "text", "text": text}]
        for b64 in images_b64:
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"}})
        return {"role": "user", "content": content}
