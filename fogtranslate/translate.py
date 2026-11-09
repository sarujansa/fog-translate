"""What every translation service shares: the instruction, the answer format, parsing and the request thread.

A service (``claude``, ``gemini``, ``ollama``) reads the chat picture and translates it in one step. Sent: the
picture of the marked region only (PNG in memory, never a file), the target language and the fixed instruction
``SYSTEM``. Answer: JSON in the form ``SCHEMA``, turned into ``ChatLine``s; answers are only shown as plain text.
"""
from __future__ import annotations

import io
import logging
import threading
from dataclasses import dataclass

from .lines import ChatLine

log = logging.getLogger(__name__)

MAX_SIDE = 1568                  # longest side of the picture sent
MAX_LINES = 30
MAX_TOKENS_DEFAULT = 4096
MAX_FIELD = 500

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
    """kind: key (no/invalid key), quota (rate limit or no credit), net (connection), refused, answer,
    model (unknown model), server (local service not running), other."""

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


def instruction(target: str) -> str:
    return "Target language: " + LANGUAGES.get(target, "German") + "."


def answer_lines(text: str) -> list[ChatLine]:
    """The JSON text of an answer → ChatLines; not JSON → TranslateError("answer")."""
    import json
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        raise TranslateError("answer") from None
    return parse(data)


class Worker:
    """Runs one request in a thread; ``done(result_or_error)`` is called in that thread."""

    def __init__(self, translator, done):
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
