"""The one small HTTP helper for the services without an SDK (Gemini, Ollama) – standard library only.

Redirects are refused (the services never need one, and a redirect could carry the key elsewhere); answers are
capped at ``MAX_BYTES``.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

MAX_BYTES = 4 * 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener():
    return urllib.request.build_opener(_NoRedirect)


class NetError(Exception):
    """No answer at all (connection refused, DNS, timeout)."""


def request(method: str, url: str, headers: dict | None = None, body=None, timeout: float = 60.0,
            opener=None) -> tuple[int, dict]:
    """(status, parsed JSON or {}) – HTTP errors are returned, not raised; no connection raises NetError."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with (opener or _opener()).open(req, timeout=timeout) as r:
            status, raw = r.status, r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        status, raw = e.code, (e.read(MAX_BYTES + 1) if e.fp else b"")
    except (urllib.error.URLError, OSError) as e:
        raise NetError(type(e).__name__) from None
    if len(raw) > MAX_BYTES:
        raise NetError("too large")
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        parsed = {}
    return status, parsed if isinstance(parsed, dict) else {}
