"""What every translation service shares: the instruction, the answer format, parsing and the request thread.

A service (``claude``, ``gemini``, ``ollama``) reads the chat picture and translates it in one step. Sent: the
picture of the marked region only (PNG in memory, never a file), the target language and the fixed instruction
``SYSTEM``. Answer: JSON in the form ``SCHEMA``, turned into ``ChatLine``s; answers are only shown as plain text.
"""
from __future__ import annotations

import io
import logging
import threading
import time
from dataclasses import dataclass

from .i18n import N_
from .lines import ChatLine

log = logging.getLogger(__name__)

MAX_SIDE = 1568                  # longest side of the picture sent
MAX_LINES = 30
MAX_TOKENS_DEFAULT = 4096
MAX_FIELD = 500

# the English names go to the service ("Target language: German."); the window shows them through tr()
LANGUAGES = {"de": N_("German"), "en": N_("English"), "fr": N_("French"), "es": N_("Spanish"), "it": N_("Italian"),
             "pt": N_("Portuguese"), "pl": N_("Polish"), "ru": N_("Russian"), "tr": N_("Turkish"),
             "nl": N_("Dutch"), "zh": N_("Chinese (Simplified)"), "ja": N_("Japanese"), "ko": N_("Korean")}

SYSTEM = (
    "You read a cropped screenshot of the text chat of the video game Dead by Daylight (lobby or end-of-match "
    "screen). A chat message starts with the sender's name followed by a colon ('Name: text'). Names can be in "
    "any colour (also white like the text) and in any script (Latin, Chinese, Cyrillic, Korean …). Every line "
    "that begins with 'Name:' starts a new message. A line WITHOUT 'Name:' at its start continues the message "
    "above it (long messages wrap) - join it to that message. Lines like '----- Joined Match -----' are system "
    "messages without a sender. The picture can be several snapshots of the same chat stacked top to bottom "
    "(older first, separated by a dark band; many snapshots fill several columns - the left column first): the "
    "same message can then appear more than once - return it once. "
    "Skip a message whose first line is cut off at the top edge of a snapshot. Add "
    "'…' only where a word is visibly cut by the right edge of a snapshot. Return every message top to bottom, "
    "exactly as written (any script or language): the sender (empty for system messages), the whole message text, "
    "its language as an ISO 639-1 code ('und' if unclear) and a natural translation of the whole message into the "
    "target language that keeps gamer slang and its tone (e.g. 'gg', 'ez', 'xdd', 'tbag', 'camping', "
    "'tunneling' may stay as they are). Set translate to false when the message already is in the target "
    "language, is a system message, or has nothing to translate (only a name, emoji, numbers, code, 'gg'); "
    "then leave translation empty. "
    "Never invent messages; if no chat is visible, return an empty list."
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
    seconds: float = 0.0             # how long the service took (set by the caller that timed it)


def png_bytes(img) -> bytes:
    """BGR numpy picture → PNG bytes, longest side ≤ MAX_SIDE (Pillow, in memory). ``compress_level=1``: a
    700×600 chat in 7 ms instead of 36 ms with ``optimize=True``, for 38 instead of 33 KB (measured 14.11.2026)."""
    from PIL import Image
    import numpy as np
    a = np.asarray(img)
    if a.ndim == 3:
        a = a[..., 2::-1]                       # BGR → RGB
    pic = Image.fromarray(np.ascontiguousarray(a))
    if max(pic.size) > MAX_SIDE:
        pic.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    pic.save(buf, "PNG", compress_level=1)
    return buf.getvalue()


def sample_picture():
    """A small made-up chat (no real player) for "Test service": dark panel, light text, two languages."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    pic = Image.new("RGB", (520, 110), (14, 14, 16))
    d = ImageDraw.Draw(pic)
    try:
        font = ImageFont.load_default(size=22)
    except TypeError:                                # old Pillow
        font = ImageFont.load_default()
    d.text((14, 14), "Meg: hola, buena partida", fill=(235, 235, 235), font=font)
    d.text((14, 48), "Ace: merci pour le heal", fill=(235, 235, 235), font=font)
    d.text((14, 82), "Bill: gg", fill=(235, 235, 235), font=font)
    return np.asarray(pic)[..., ::-1].copy()


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
                t0 = time.monotonic()
                result = self.translator.request(img)
                result.seconds = time.monotonic() - t0
                self._done(result)
            except TranslateError as e:
                self._done(e)
            except Exception as e:                   # never let the thread die silently
                log.exception("Übersetzung fehlgeschlagen")
                self._done(TranslateError("other", type(e).__name__))
            finally:
                self._busy.release()

        threading.Thread(target=run, name="translate", daemon=True).start()
        return True
