"""Settings in the user's data folder (``settings.json``); written atomically."""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile

from . import geometry, services, translate

log = logging.getLogger(__name__)
APP_DIR = "FogTranslate"
ENV = "FOGTRANSLATE_DATA_DIR"            # tests

DEFAULTS = {
    "region": None,                  # [x, y, w, h] relative to the whole game window (client area)
    "region_space": "",              # "window" – a region saved before 0.7.1 (16:9 space, clipped) is dropped
    "target": "de",
    "service": services.DEFAULT,     # claude | gemini | ollama
    "claude_model": services.DEFAULT_MODEL["claude"],
    "gemini_model": services.DEFAULT_MODEL["gemini"],
    "ollama_model": services.DEFAULT_MODEL["ollama"],
    "ollama_port": 11434,
    "claude_key": "",                # "dpapi:…" only
    "gemini_key": "",                # "dpapi:…" only
    "accepted": [],                  # cloud services whose notice the user confirmed
    "look_s": 0.5,                   # seconds between looks at the region (a look costs ~16 ms)
    "min_gap_s": 2.0,                # at least this long between two requests
    "daily_cap": 300,                # requests per day at most
    "show_s": 25.0,                  # how long new translations stay on screen
    "show_all": False,               # also show lines already in the target language
    "hide_in_captures": False,       # True: the overlay is left out of screenshots/recordings (Windows)
    "read_background": True,         # also read with DBD behind another window – only if nothing covers the chat
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
        self.session_keys: dict[str, str] = {}      # keys kept only for this run (no DPAPI)
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
            # 0.1 had one service: "api_key"/"model" were Claude's, "accepted" a bool
            if "api_key" in data and "claude_key" not in data:
                data["claude_key"] = data["api_key"]
            if "model" in data and "claude_model" not in data:
                data["claude_model"] = data["model"]
            if isinstance(data.get("accepted"), bool):
                data["accepted"] = ["claude"] if data["accepted"] else []
            for k, v in data.items():
                if k in DEFAULTS and (DEFAULTS[k] is None or isinstance(v, type(DEFAULTS[k]))
                                      or (isinstance(DEFAULTS[k], float) and isinstance(v, int))):
                    self.values[k] = v
        if self.values["region"] is not None and (self.values["region_space"] != "window"
                                                  or not geometry.valid_region(self.values["region"])):
            self.values["region"] = None            # also: marked before 0.7.1 → mark again
        self.values["region_space"] = "window"
        if self.values["target"] not in translate.LANGUAGES:
            self.values["target"] = "de"
        if self.values["service"] not in services.SERVICES:
            self.values["service"] = services.DEFAULT
        for service, key in services.MODEL_SETTING.items():
            if not services.valid_model(service, self.values[key]):
                self.values[key] = services.DEFAULT_MODEL[service]
        self.values["accepted"] = [x for x in self.values["accepted"] if x in services.SERVICES]
        # 0.8.2: faster defaults – values still at the old defaults (saved by earlier versions) move along
        if float(self.values["look_s"]) == 1.0:
            self.values["look_s"] = DEFAULTS["look_s"]
        if float(self.values["min_gap_s"]) == 3.0:
            self.values["min_gap_s"] = DEFAULTS["min_gap_s"]
        if not 10 <= int(self.values["daily_cap"]) <= 5000:
            self.values["daily_cap"] = DEFAULTS["daily_cap"]
        if not 1 <= int(self.values["ollama_port"]) <= 65535:
            self.values["ollama_port"] = 11434

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

    # ---- keys
    ENV_KEYS = {"claude": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}

    def api_key(self, service: str) -> str:
        from . import secret
        setting = services.KEY_SETTING.get(service)
        if setting is None:
            return ""
        return (self.session_keys.get(service) or secret.unprotect(self.values[setting])
                or os.environ.get(self.ENV_KEYS[service], ""))

    def has_stored_key(self, service: str) -> bool:
        setting = services.KEY_SETTING.get(service)
        return bool(setting and (self.values[setting] or self.session_keys.get(service)))

    def set_api_key(self, service: str, key: str) -> bool:
        """True = stored encrypted; False = kept for this session only."""
        from . import secret
        setting = services.KEY_SETTING[service]
        key = key.strip()
        try:
            self.values[setting] = secret.protect(key)
            self.session_keys.pop(service, None)
            self.save()
            return True
        except secret.CannotProtect:
            self.values[setting] = ""
            self.session_keys[service] = key
            return False

    def accepted(self, service: str) -> bool:
        return not services.is_cloud(service) or service in self.values["accepted"]

    def set_accepted(self, service: str, yes: bool):
        rest = [x for x in self.values["accepted"] if x != service]
        self.values["accepted"] = rest + ([service] if yes else [])

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
