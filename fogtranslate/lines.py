"""Pure: which chat lines are new. Claude reads the whole region every time; lines already shown are skipped."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
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


RECENT = 30              # a new reading is compared with this many latest messages
MIN_PART = 8             # a fragment must have at least this many letters to be matched inside a message
SIMILAR = 0.8            # SequenceMatcher ratio above which two readings are the same message


def _same_sender(a: ChatLine, b: ChatLine) -> bool:
    x, y = normal(a.sender), normal(b.sender)
    return x == y or not x or not y


def same_message(a: ChatLine, b: ChatLine) -> bool:
    """Two readings of one chat message: equal, one a part of the other (a wrapped line read on its own, or text
    cut at the edge), or nearly equal (a letter read differently)."""
    if not _same_sender(a, b):
        return False
    x, y = normal(a.text), normal(b.text)
    if not x or not y:
        return False
    if x == y:
        return True
    short, long_ = (x, y) if len(x) <= len(y) else (y, x)
    if len(short) >= MIN_PART and short in long_:
        return True
    return SequenceMatcher(None, x, y, autojunk=False).ratio() >= SIMILAR


class Transcript:
    """All messages read so far, each once. A better reading of a message (longer: wrapped lines joined, less cut
    off) replaces the earlier one(s) in place instead of adding a duplicate."""

    def __init__(self, keep: int = KEEP):
        self.keep = keep
        self.entries: list[ChatLine] = []

    def clear(self):
        self.entries.clear()

    def add(self, lines) -> tuple[list[ChatLine], dict[str, ChatLine]]:
        """(new messages, {key of a replaced or merged-away message: the message that now stands for it})."""
        added: list[ChatLine] = []
        replaced: dict[str, ChatLine] = {}
        for line in lines:
            if not normal(line.text):
                continue
            start = max(0, len(self.entries) - RECENT)
            hits = [i for i in range(start, len(self.entries)) if same_message(self.entries[i], line)]
            if not hits:
                self.entries.append(line)
                added.append(line)
                continue
            longest = max(hits, key=lambda i: len(normal(self.entries[i].text)))
            if len(normal(line.text)) <= len(normal(self.entries[longest].text)) and len(hits) == 1:
                continue                                    # nothing better than what is shown
            keep = line if len(normal(line.text)) >= len(normal(self.entries[longest].text)) else self.entries[longest]
            if keep.sender == "" and self.entries[hits[0]].sender:
                keep = ChatLine(self.entries[hits[0]].sender, keep.text, keep.language, keep.translation,
                                keep.translate)
            for i in hits:
                replaced[self.entries[i].key()] = keep
            first = hits[0]
            self.entries[first] = keep
            for i in reversed(hits[1:]):
                del self.entries[i]
        del self.entries[:-self.keep]
        return added, replaced
