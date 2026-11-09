"""A local model in Ollama (https://ollama.com) – nothing leaves the PC.

Only ever ``http://127.0.0.1:<port>`` (``HOST`` fixed, never configurable; the port is a setting). The model must
read pictures (a vision model such as qwen2.5vl or gemma3); the user pulls it with ``ollama pull``.
"""
from __future__ import annotations

import base64

from . import http
from .translate import SCHEMA, SYSTEM, Result, TranslateError, answer_lines, instruction, png_bytes

NAME = "ollama"
HOST = "127.0.0.1"
DEFAULT_PORT = 11434
DEFAULT_MODEL = "qwen2.5vl:7b"
SUGGESTED = ("qwen2.5vl:7b", "gemma3:12b", "qwen2.5vl:3b", "gemma3:4b")
TIMEOUT_S = 180.0                 # the first request loads the model
_MODEL_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-._:/")


def valid_model(name: str) -> bool:
    return bool(name) and len(name) <= 100 and set(name.lower()) <= _MODEL_CHARS and ".." not in name


def base_url(port: int) -> str:
    port = int(port)
    if not 1 <= port <= 65535:
        port = DEFAULT_PORT
    return "http://%s:%d" % (HOST, port)


def installed_models(port: int = DEFAULT_PORT, get=http.request) -> list[str]:
    """Names of the models pulled in the local Ollama; [] if it does not run."""
    try:
        status, data = get("GET", base_url(port) + "/api/tags", None, None, 5.0)
    except http.NetError:
        return []
    if status != 200:
        return []
    names = [m.get("name", "") for m in data.get("models", []) if isinstance(m, dict)]
    return sorted(n for n in names if valid_model(n))


class Translator:
    def __init__(self, model: str = DEFAULT_MODEL, target: str = "de", port: int = DEFAULT_PORT,
                 post=http.request):
        self.model = model if valid_model(model) else DEFAULT_MODEL
        self.target = target
        self.url = base_url(port) + "/api/chat"
        self._post = post

    def request(self, img) -> Result:
        picture = base64.standard_b64encode(png_bytes(img)).decode("ascii")
        body = {
            "model": self.model,
            "stream": False,
            "format": SCHEMA,
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": instruction(self.target), "images": [picture]},
            ],
        }
        try:
            status, data = self._post("POST", self.url, None, body, TIMEOUT_S)
        except http.NetError as e:
            raise TranslateError("server", str(e)) from None
        if status == 404:
            raise TranslateError("model", self.model)
        if status != 200:
            raise TranslateError("other", str(status))
        text = (data.get("message") or {}).get("content", "")
        return Result(answer_lines(text), 0.0)
