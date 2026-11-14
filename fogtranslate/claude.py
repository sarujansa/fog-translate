"""Anthropic Claude over its REST API (``api.anthropic.com``) – standard library only, through ``http.py``.

Until 0.12 this went through the official SDK (``anthropic``), which pulled in pydantic, httpx and more, took
seconds to import on Windows and needed an import lock – for a single POST. The request is the one the SDK 2.7.0
sent (same path, body and API headers, checked against the SDK); its one retry is kept (``_retry_wait``). The key
goes only in the ``Authorization`` header, as the SDK sent it.
"""
from __future__ import annotations

import base64
import random
import time

from . import http
from .i18n import N_
from .translate import MAX_TOKENS_DEFAULT, SCHEMA, SYSTEM, Result, TranslateError, answer_lines, instruction, png_bytes

NAME = "claude"
HOST = "https://api.anthropic.com"
URL = HOST + "/v1/messages"
API_VERSION = "2026-10-21"              # the ``anthropic-version`` header the SDK 2.7.0 sent
MODELS = {                       # id → (label, $ per 1M input, $ per 1M output)
    "claude-opus-5-5": (N_("Claude Opus 5.5 (best quality)"), 4.00, 20.00),
    "claude-sonnet-5-5": (N_("Claude Sonnet 5.5 (faster)"), 2.00, 10.00),
    "claude-haiku-5-5": (N_("Claude Haiku 5.5 (recommended: fastest, cheapest)"), 0.10, 0.50),
}
DEFAULT_MODEL = "claude-haiku-5-5"      # fast and cheap – a chat should not wait (Saru, 10.11.2026)
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5")   # models that take the server-side fallbacks
TIMEOUT_S = 60.0
RETRY_STATUS = (408, 409, 429)          # … and every 5xx – what the SDK retried
RETRY_WAIT_S = 0.5                      # the SDK's first back-off (with up to 25 % jitter)
MAX_RETRY_AFTER_S = 8.0                 # a longer "retry-after" is not waited for: the engine pauses instead


def cost_usd(model: str, usage) -> float:
    _, p_in, p_out = MODELS.get(model, MODELS[DEFAULT_MODEL])
    u = usage if isinstance(usage, dict) else {}
    n_in = (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) * 1.25
    n_in += (u.get("cache_read_input_tokens") or 0) * 0.1
    return (n_in * p_in + (u.get("output_tokens") or 0) * p_out) / 1_000_000


class Translator:
    """``post`` (like ``http.exchange``) and ``sleep`` are injectable for tests."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, target: str = "de", post=None, sleep=time.sleep):
        if not api_key:
            raise TranslateError("key")
        self._key = api_key
        self.model = model if model in MODELS else DEFAULT_MODEL
        self.target = target
        self._post = post or http.exchange
        self._sleep = sleep

    def body(self, picture: str) -> dict:
        body = {
            "max_tokens": MAX_TOKENS_DEFAULT,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": picture}},
                {"type": "text", "text": instruction(self.target)},
            ]}],
            "model": self.model,
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        }
        if self.model in FALLBACK_MODELS:
            body["fallbacks"] = "default"
        return body

    def headers(self) -> dict:
        headers = {"Authorization": "Bearer " + self._key, "anthropic-version": API_VERSION, "Accept": "application/json"}
        if self.model in FALLBACK_MODELS:
            headers["anthropic-beta"] = FALLBACK_BETA
        return headers

    def request(self, img) -> Result:
        picture = base64.standard_b64encode(png_bytes(img)).decode("ascii")
        body, headers = self.body(picture), self.headers()
        for attempt in range(2):                     # one retry, like the SDK with max_retries=1
            try:
                status, data, answer_headers = self._post("POST", URL, headers, body, TIMEOUT_S)
            except http.NetError as e:
                if attempt == 0:
                    self._sleep(_retry_wait({}))
                    continue
                raise TranslateError("net", str(e)) from None
            if status != 200 and attempt == 0:
                wait = _retry_wait(answer_headers) if _should_retry(status, answer_headers) else None
                if wait is not None:
                    self._sleep(wait)
                    continue
            break
        if status != 200:
            raise _error(status, data)
        if data.get("stop_reason") == "refusal":
            raise TranslateError("refused")
        content = data.get("content") if isinstance(data.get("content"), list) else []
        text = next((b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"), "")
        return Result(answer_lines(text if isinstance(text, str) else ""), cost_usd(self.model, data.get("usage")))


def _should_retry(status: int, headers: dict) -> bool:
    flag = headers.get("x-should-retry")
    if flag in ("true", "false"):                   # the server says so – obeyed, as by the SDK
        return flag == "true"
    return status in RETRY_STATUS or status >= 500


def _retry_wait(headers: dict) -> float | None:
    """Seconds before the retry: the server's ``retry-after-ms``/``retry-after`` (None = longer than
    ``MAX_RETRY_AFTER_S``, no retry), else the SDK's first back-off."""
    for name, scale in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        try:
            wait = float(headers[name]) * scale
        except (KeyError, TypeError, ValueError):
            continue
        if wait > 0:
            return wait if wait <= MAX_RETRY_AFTER_S else None
    return RETRY_WAIT_S * (1 - 0.25 * random.random())


def _message(data: dict) -> str:
    err = data.get("error") if isinstance(data, dict) else None
    return str(err.get("message", "")) if isinstance(err, dict) else ""


def _error(status: int, data: dict) -> TranslateError:
    """HTTP status → kind, as the SDK's exception classes were mapped; the key never reaches the log."""
    if status in (401, 403):
        return TranslateError("key", str(status))
    if status == 429:
        return TranslateError("quota", str(status))
    if status == 404:
        return TranslateError("model", str(status))
    if status == 400 and "credit" in _message(data).lower():
        return TranslateError("quota", "credit")
    return TranslateError("other", str(status))
