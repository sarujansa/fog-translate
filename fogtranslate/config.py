"""Settings in the user's data folder (``settings.json``); written atomically."""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile

from . import geometry, translate

log = logging.getLogger(__name__)
APP_DIR = "FogTranslate"
ENV = "FOGTRANSLATE_DATA_DIR"            # tests

DEFAULTS = {
    "region": None,                  # [x, y, w, h] relative to the 16:9 viewport
    "target": "de",
    "model": translate.DEFAULT_MODEL,
    "api_key": "",                   # "dpapi:…" only
    "accepted": False,               # the user has read that pictures go to Anthropic
    "look_s": 1.0,                   # seconds between looks at the region
    "min_gap_s": 3.0,                # at least this long between two requests
    "daily_cap": 300,                # requests per day at most
    "show_s": 25.0,                  # how long new translations stay on screen
    "show_all": False,               # also show lines already in the target language
    "font_px": 18,
    "spent": {},                     # "YYYY-MM" → estimated USD
    "requests": {},                  # "YYYY-MM-DD" → count
}


def data_dir() -> str:
    forced = os.environ.get(ENV)
    if forced:
        return forced
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, APP_DIR)


class Settings:
    def __init__(self, folder: str | None = None):
        self.folder = folder or data_dir()
        self.path = os.path.join(self.folder, "settings.json")
        self.values = dict(DEFAULTS)
        self.session_key = ""        # key kept only for this run (no DPAPI)
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            log.warning("Einstellungen nicht lesbar (%s) – Standardwerte", type(e).__name__)
            return
        if isinstance(data, dict):
            for k, v in data.items():
                if k in DEFAULTS and (DEFAULTS[k] is None or isinstance(v, type(DEFAULTS[k]))
                                      or (isinstance(DEFAULTS[k], float) and isinstance(v, int))):
                    self.values[k] = v
        if self.values["region"] is not None and not geometry.valid_region(self.values["region"]):
            self.values["region"] = None
        if self.values["target"] not in translate.LANGUAGES:
            self.values["target"] = "de"
        if self.values["model"] not in translate.MODELS:
            self.values["model"] = translate.DEFAULT_MODEL

    def __getitem__(self, key):
        return self.values[key]

    def __setitem__(self, key, value):
        if key not in DEFAULTS:
            raise KeyError(key)
        self.values[key] = value

    def save(self):
        os.makedirs(self.folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=self.folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.values, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ---- key
    def api_key(self) -> str:
        from . import secret
        return self.session_key or secret.unprotect(self.values["api_key"]) or os.environ.get("ANTHROPIC_API_KEY", "")

    def set_api_key(self, key: str) -> bool:
        """True = stored encrypted; False = kept for this session only."""
        from . import secret
        key = key.strip()
        try:
            self.values["api_key"] = secret.protect(key)
            self.session_key = ""
            self.save()
            return True
        except secret.CannotProtect:
            self.values["api_key"] = ""
            self.session_key = key
            return False

    # ---- counters
    def count_request(self, day: str, month: str, usd: float):
        req = {k: v for k, v in self.values["requests"].items() if k >= day[:8]}   # keep this month only
        req[day] = int(req.get(day, 0)) + 1
        self.values["requests"] = req
        spent = dict(self.values["spent"])
        spent[month] = round(float(spent.get(month, 0.0)) + usd, 6)
        self.values["spent"] = {k: spent[k] for k in sorted(spent)[-12:]}

    def requests_today(self, day: str) -> int:
        return int(self.values["requests"].get(day, 0))
