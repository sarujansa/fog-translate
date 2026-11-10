"""Google Gemini over its REST API (``generativelanguage.googleapis.com``) – standard library only.

The key goes in the ``x-goog-api-key`` header (never in the URL, so it is in no log or proxy line). With the
free tier Google may use what is sent to improve its products – the UI says so before the first start.
"""
from __future__ import annotations

import base64

from . import http
from .i18n import N_
from .translate import SCHEMA, SYSTEM, Result, TranslateError, answer_lines, instruction, png_bytes

NAME = "gemini"
HOST = "https://generativelanguage.googleapis.com"
MODELS = {
    "gemini-flash-latest": N_("Gemini Flash (recommended)"),
    "gemini-flash-lite-latest": N_("Gemini Flash-Lite (fastest, weaker)"),
    "gemini-pro-latest": N_("Gemini Pro (best quality, small free quota)"),
}
DEFAULT_MODEL = "gemini-flash-latest"
TIMEOUT_S = 60.0
_MODEL_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-.")


def valid_model(name: str) -> bool:
    return bool(name) and len(name) <= 64 and set(name) <= _MODEL_CHARS


def _openapi(schema):
    """JSON Schema → the OpenAPI subset of the older ``responseSchema`` field (no additionalProperties)."""
    if isinstance(schema, dict):
        return {k: _openapi(v) for k, v in schema.items() if k != "additionalProperties"}
    if isinstance(schema, list):
        return [_openapi(v) for v in schema]
    return schema


class Translator:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, target: str = "de", post=http.request):
        if not api_key:
            raise TranslateError("key")
        self._key = api_key
        self.model = model if valid_model(model) else DEFAULT_MODEL
        self.target = target
        self._post = post
        self._json_schema = True          # newer field; falls back once to responseSchema if refused

    def _body(self, picture: str) -> dict:
        config = {"responseMimeType": "application/json", "temperature": 0.2}
        if self._json_schema:
            config["responseJsonSchema"] = SCHEMA
        else:
            config["responseSchema"] = _openapi(SCHEMA)
        return {
            "systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [
                {"inlineData": {"mimeType": "image/png", "data": picture}},
                {"text": instruction(self.target)},
            ]}],
            "generationConfig": config,
        }

    def request(self, img) -> Result:
        picture = base64.standard_b64encode(png_bytes(img)).decode("ascii")
        url = HOST + "/v1beta/models/" + self.model + ":generateContent"
        for _ in range(2):
            try:
                status, data = self._post("POST", url, {"x-goog-api-key": self._key}, self._body(picture),
                                          TIMEOUT_S)
            except http.NetError as e:
                raise TranslateError("net", str(e)) from None
            if status == 400 and self._json_schema and "responseJsonSchema" in _message(data):
                self._json_schema = False
                continue
            break
        if status != 200:
            raise _error(status, data)
        feedback = data.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            raise TranslateError("refused")
        candidates = data.get("candidates") or []
        if not candidates:
            raise TranslateError("answer")
        cand = candidates[0] if isinstance(candidates[0], dict) else {}
        if cand.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"):
            raise TranslateError("refused")
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
        return Result(answer_lines(text), 0.0)


def _message(data: dict) -> str:
    err = data.get("error") if isinstance(data, dict) else None
    return str(err.get("message", "")) if isinstance(err, dict) else ""


def _error(status: int, data: dict) -> TranslateError:
    err = data.get("error") if isinstance(data.get("error"), dict) else {}
    reasons = {str(d.get("reason", "")) for d in err.get("details", []) if isinstance(d, dict)}
    if status in (401, 403) or "API_KEY_INVALID" in reasons:
        return TranslateError("key", str(status))
    if status == 429:
        return TranslateError("quota", str(status))
    if status == 404:
        return TranslateError("model", str(status))
    return TranslateError("other", str(status))
