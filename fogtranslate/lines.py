"""Pure: which chat lines are new. Claude reads the whole region every time; lines already shown are skipped."""
from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass

KEEP = 200               # remembered lines
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ChatLine:
    sender: str
    text: str
    language: str
    translation: str
    translate: bool          # False: already in the target language, or nothing to translate (gg, emoji, numbers)

    def key(self) -> str:
        return normal(self.sender) + "\x1f" + normal(self.text)


def normal(text: str) -> str:
    """Case, accents, spaces and punctuation do not make a line new (Claude reads them slightly differently)."""
    t = unicodedata.normalize("NFKD", str(text or "")).casefold()
    t = "".join(c for c in t if not unicodedata.combining(c) and (c.isalnum() or c.isspace()))
    return _SPACE.sub(" ", t).strip()


class SeenLines:
    def __init__(self, keep: int = KEEP):
        self.keep = keep
        self._seen: OrderedDict[str, None] = OrderedDict()

    def clear(self):
        self._seen.clear()

    def new(self, lines) -> list[ChatLine]:
        """The lines not seen before, in order; all of them are remembered."""
        out = []
        for line in lines:
            k = line.key()
            if not normal(line.text):
                continue
            if k in self._seen:
                self._seen.move_to_end(k)
                continue
            self._seen[k] = None
            out.append(line)
        while len(self._seen) > self.keep:
            self._seen.popitem(last=False)
        return out
