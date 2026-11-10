"""Anthropic Claude via the official SDK (``anthropic``)."""
from __future__ import annotations

import base64
import threading

from .translate import MAX_TOKENS_DEFAULT, SCHEMA, SYSTEM, Result, TranslateError, answer_lines, instruction, png_bytes

NAME = "claude"
MODELS = {                       # id → (label, $ per 1M input, $ per 1M output)
    "claude-opus-5-5": ("Claude Opus 5.5 (best quality)", 4.00, 20.00),
    "claude-sonnet-5-5": ("Claude Sonnet 5.5 (faster)", 2.00, 10.00),
    "claude-haiku-5-5": ("Claude Haiku 5.5 (recommended: fastest, cheapest)", 0.10, 0.50),
}
DEFAULT_MODEL = "claude-haiku-5-5"      # fast and cheap – a chat should not wait (Saru, 10.11.2026)
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5")   # models that take the server-side fallbacks
TIMEOUT_S = 60.0
_IMPORT_LOCK = threading.Lock()


def sdk():
    """The ``anthropic`` package, imported under a lock: two threads importing it for the first time at once
    (a look thread restarted while the old one still starts) hit pydantic's lazy imports half-initialised –
    "cannot import name … from partially initialized module" (seen in CI, 10.11.2026)."""
    with _IMPORT_LOCK:
        import anthropic
    return anthropic


def cost_usd(model: str, usage) -> float:
    _, p_in, p_out = MODELS.get(model, MODELS[DEFAULT_MODEL])
    n_in = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * 1.25
    n_in += (getattr(usage, "cache_read_input_tokens", 0) or 0) * 0.1
    return (n_in * p_in + (getattr(usage, "output_tokens", 0) or 0) * p_out) / 1_000_000


class Translator:
    """``client`` is injectable for tests (anything with ``beta.messages.create``)."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, target: str = "de", client=None):
        if not api_key and client is None:
            raise TranslateError("key")
        self.model = model if model in MODELS else DEFAULT_MODEL
        self.target = target
        if client is None:
            anthropic = sdk()
            client = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_S, max_retries=1)
        self._client = client

    def request(self, img) -> Result:
        picture = base64.standard_b64encode(png_bytes(img)).decode("ascii")
        kwargs = dict(
            model=self.model,
            max_tokens=MAX_TOKENS_DEFAULT,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": picture}},
                {"type": "text", "text": instruction(self.target)},
            ]}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        )
        if self.model in FALLBACK_MODELS:
            kwargs.update(betas=[FALLBACK_BETA], fallbacks="default")
        try:
            response = self._client.beta.messages.create(**kwargs)
        except Exception as e:                       # mapped to a kind; the key never reaches the log
            raise _error(e) from None
        if getattr(response, "stop_reason", None) == "refusal":
            raise TranslateError("refused")
        text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), "")
        return Result(answer_lines(text), cost_usd(self.model, getattr(response, "usage", None)))


def _error(e: Exception) -> TranslateError:
    try:
        anthropic = sdk()
    except ImportError:                              # pragma: no cover
        return TranslateError("other", type(e).__name__)
    if isinstance(e, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return TranslateError("key", type(e).__name__)
    if isinstance(e, anthropic.RateLimitError):
        return TranslateError("quota", type(e).__name__)
    if isinstance(e, anthropic.APIConnectionError):
        return TranslateError("net", type(e).__name__)
    if isinstance(e, anthropic.NotFoundError):
        return TranslateError("model", type(e).__name__)
    if isinstance(e, anthropic.BadRequestError) and "credit" in str(e).lower():
        return TranslateError("quota", "credit")
    return TranslateError("other", type(e).__name__)
