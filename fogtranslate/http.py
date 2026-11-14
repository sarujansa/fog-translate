"""The one small HTTP helper for all services (Claude, Gemini, Ollama) – standard library only.

Redirects are refused (the services never need one, and a redirect could carry the key elsewhere); answers are
capped at ``MAX_BYTES``. Requests to this PC (Ollama) never go through a proxy: the picture must not leave the PC.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

MAX_BYTES = 4 * 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


def _opener(url: str = ""):
    if urllib.parse.urlsplit(url).hostname in LOCAL_HOSTS:
        # an empty ProxyHandler replaces the default one, which would use http_proxy / the Windows proxy
        return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    return urllib.request.build_opener(_NoRedirect)


class NetError(Exception):
    """No answer at all (connection refused, DNS, timeout)."""


def request(method: str, url: str, headers: dict | None = None, body=None, timeout: float = 60.0,
            opener=None) -> tuple[int, dict]:
    """(status, parsed JSON or {}) – HTTP errors are returned, not raised; no connection raises NetError."""
    status, parsed, _headers = exchange(method, url, headers, body, timeout, opener)
    return status, parsed


def exchange(method: str, url: str, headers: dict | None = None, body=None, timeout: float = 60.0,
             opener=None) -> tuple[int, dict, dict]:
    """Like ``request``, plus the answer's headers (lower-case names) – Claude reads ``retry-after`` from them."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with (opener or _opener(url)).open(req, timeout=timeout) as r:
            status, raw, got = r.status, r.read(MAX_BYTES + 1), r.headers
    except urllib.error.HTTPError as e:
        status, raw, got = e.code, (e.read(MAX_BYTES + 1) if e.fp else b""), e.headers
    except (urllib.error.URLError, OSError) as e:
        raise NetError(type(e).__name__) from None
    if len(raw) > MAX_BYTES:
        raise NetError("too large")
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        parsed = {}
    names = {k.lower(): v for k, v in (got.items() if got is not None else [])}
    return status, parsed if isinstance(parsed, dict) else {}, names
