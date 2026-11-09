"""Claude reads the chat picture and translates it – one request per settled change of the region.

Sent: the picture of the marked region only (PNG in memory, never a file), the target language and a fixed
instruction. The picture can show player names – that is said in the UI before the user turns it on.
Answer: structured JSON (``SCHEMA``), turned into ``ChatLine``s; Claude's texts are only ever shown as plain text.
"""
from __future__ import annotations

import base64
import io
import logging
import threading
from dataclasses import dataclass

from .lines import ChatLine

log = logging.getLogger(__name__)

MODELS = {                       # id → (label, $ per 1M input, $ per 1M output)
    "claude-opus-5-5": ("Claude Opus 5.5 (beste Qualität)", 4.00, 20.00),
    "claude-sonnet-5-5": ("Claude Sonnet 5.5", 2.00, 10.00),
    "claude-haiku-5-5": ("Claude Haiku 5.5 (am günstigsten)", 0.10, 0.50),
}
DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5")   # models that take the server-side fallbacks
MAX_SIDE = 1568                  # longest side of the picture sent
MAX_TOKENS = 4096
MAX_LINES = 30
MAX_FIELD = 500
TIMEOUT_S = 60.0

LANGUAGES = {"de": "German", "en": "English", "fr": "French", "es": "Spanish", "it": "Italian",
             "pt": "Portuguese", "pl": "Polish", "ru": "Russian", "tr": "Turkish", "nl": "Dutch"}

SYSTEM = (
    "You read a cropped screenshot of the text chat of the video game Dead by Daylight (lobby or end-of-match "
    "screen). Each chat line usually has the form 'PlayerName: message'; system lines have no name. Read every "
    "chat line you can see, top to bottom, exactly as written (any script or language). For each line give the "
    "sender (empty for system lines), the message text, its language as an ISO 639-1 code ('und' if unclear) "
    "and a natural translation into the target language that keeps gamer slang and its tone (e.g. 'gg', 'ez', "
    "'tbag', 'camping', 'tunneling' may stay as they are). Set translate to false when the message already is in "
    "the target language or has nothing to translate (only a name, emoji, numbers, 'gg'). Never invent lines; "
    "if no chat is visible, return an empty list."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sender": {"type": "string"},
                    "text": {"type": "string"},
                    "language": {"type": "string"},
                    "translation": {"type": "string"},
                    "translate": {"type": "boolean"},
                },
                "required": ["sender", "text", "language", "translation", "translate"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["lines"],
    "additionalProperties": False,
}


class TranslateError(Exception):
    """kind: key (no/invalid key), quota (rate limit or no credit), net (connection), refused, answer, other."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(kind)
        self.kind = kind
        self.detail = detail


@dataclass
class Result:
    lines: list[ChatLine]
    cost_usd: float


def png_bytes(img) -> bytes:
    """BGR numpy picture → PNG bytes, longest side ≤ MAX_SIDE (Pillow, in memory)."""
    from PIL import Image
    import numpy as np
    a = np.asarray(img)
    if a.ndim == 3:
        a = a[..., 2::-1]                       # BGR → RGB
    pic = Image.fromarray(np.ascontiguousarray(a))
    if max(pic.size) > MAX_SIDE:
        pic.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    pic.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _clip(v) -> str:
    s = str(v if v is not None else "")
    s = "".join(" " if (ord(c) < 32 or 0x202A <= ord(c) <= 0x202E or 0x2066 <= ord(c) <= 0x2069) else c for c in s)
    return s.strip()[:MAX_FIELD]


def parse(data) -> list[ChatLine]:
    """The structured answer → ChatLines; anything malformed is dropped, never raised."""
    out = []
    items = data.get("lines") if isinstance(data, dict) else None
    for item in (items if isinstance(items, list) else [])[:MAX_LINES]:
        if not isinstance(item, dict):
            continue
        text = _clip(item.get("text"))
        if not text:
            continue
        out.append(ChatLine(sender=_clip(item.get("sender")), text=text,
                            language=_clip(item.get("language"))[:8].lower() or "und",
                            translation=_clip(item.get("translation")) or text,
                            translate=bool(item.get("translate"))))
    return out


def cost_usd(model: str, usage) -> float:
    _, p_in, p_out = MODELS.get(model, MODELS[DEFAULT_MODEL])
    n_in = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * 1.25
    n_in += (getattr(usage, "cache_read_input_tokens", 0) or 0) * 0.1
    return (n_in * p_in + (getattr(usage, "output_tokens", 0) or 0) * p_out) / 1_000_000


class Translator:
    """One request at a time; ``client`` is injectable for tests (anything with ``beta.messages.create``)."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, target: str = "de", client=None):
        self.model = model if model in MODELS else DEFAULT_MODEL
        self.target = target if target in LANGUAGES else "de"
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_S, max_retries=1)
        self._client = client

    def request(self, img) -> Result:
        import json
        picture = base64.standard_b64encode(png_bytes(img)).decode("ascii")
        kwargs = dict(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": picture}},
                {"type": "text", "text": "Target language: " + LANGUAGES[self.target] + "."},
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
        try:
            data = json.loads(text)
        except ValueError:
            raise TranslateError("answer") from None
        return Result(parse(data), cost_usd(self.model, getattr(response, "usage", None)))


def _error(e: Exception) -> TranslateError:
    try:
        import anthropic
    except ImportError:                              # pragma: no cover
        return TranslateError("other", type(e).__name__)
    if isinstance(e, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return TranslateError("key", type(e).__name__)
    if isinstance(e, anthropic.RateLimitError):
        return TranslateError("quota", type(e).__name__)
    if isinstance(e, anthropic.APIConnectionError):
        return TranslateError("net", type(e).__name__)
    if isinstance(e, anthropic.BadRequestError) and "credit" in str(e).lower():
        return TranslateError("quota", "credit")
    return TranslateError("other", type(e).__name__)


class Worker:
    """Runs one request in a thread; ``done(result_or_error)`` is called in that thread."""

    def __init__(self, translator: Translator, done):
        self.translator = translator
        self._done = done
        self._busy = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._busy.locked()

    def submit(self, img) -> bool:
        if not self._busy.acquire(blocking=False):
            return False

        def run():
            try:
                self._done(self.translator.request(img))
            except TranslateError as e:
                self._done(e)
            except Exception as e:                   # never let the thread die silently
                log.exception("Übersetzung fehlgeschlagen")
                self._done(TranslateError("other", type(e).__name__))
            finally:
                self._busy.release()

        threading.Thread(target=run, name="translate", daemon=True).start()
        return True
