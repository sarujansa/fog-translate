"""Updating the installed .exe from this repository's GitHub releases – standard library only, only on click.

The job ``release`` (.github/workflows/build.yml) publishes ``v<version>`` with ``FogTranslate-Setup-<version>.exe``
and ``….exe.sha256``. Three clicks, nothing before the first:
1. "Check for updates" reads ``API`` (the latest release of this repository, nothing else).
2. "Download update" fetches the setup – only from ``DOWNLOAD_PREFIX``, at most ``MAX_BYTES``, kept only when its
   SHA-256 is the one the release states (the ``.sha256`` file and, when GitHub lists one, the asset's digest).
3. "Install and restart" checks the file once more, starts it (``install_args``) and ends the program; the setup
   waits for the program to end (installer/fogtranslate.iss) and starts the new version.
Nothing is sent but these requests: no account, no token, nothing about the user. Redirects only to https.
(The setup installs for the user only, without administrator rights – the download folder and the program folder
belong to the same user, so there is no boundary between them to defend.)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .update import version_tuple

REPO = "senisinx/fog-translate"
API = "https://api.github.com/repos/%s/releases/latest" % REPO
DOWNLOAD_PREFIX = "https://github.com/%s/releases/download/" % REPO
TAG = re.compile(r"^v(\d{1,4}(?:\.\d{1,5}){1,3})$")
SETUP = re.compile(r"^FogTranslate-Setup-(\d{1,4}(?:\.\d{1,5}){1,3})\.exe$")
UPDATE_DIR = "update"
MUTEX_NAME = "Local\\FogTranslate.Running"      # installer/fogtranslate.iss waits for it to go
MAX_BYTES = 400 * 1024 * 1024                    # the setup is about 60 MB
MAX_JSON = 2 * 1024 * 1024
TIMEOUT_S = 30
CHUNK = 1024 * 1024
USER_AGENT = "FogTranslate-updater"
TRANSIENT_HTTP = frozenset({500, 502, 503, 504})
RETRY_WAITS_S = (3, 10)                          # waits before the 2nd and 3rd try
SLEEP = time.sleep                               # the tests replace it


@dataclass
class Release:
    version: str
    tag: str
    setup_name: str
    setup_url: str
    size: int
    sha_url: str
    digest: str = ""                 # GitHub's own SHA-256 of the asset, when listed
    sha256: str = ""                 # the checked SHA-256 after download()


def parse_release(data) -> Release:
    """The parts of a release that matter, checked; ValueError when anything is not as the workflow makes it."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        raise ValueError("not a published release")
    m = TAG.match(str(data.get("tag_name", "")))
    if not m:
        raise ValueError("unknown tag")
    tag, version = m.group(0), m.group(1)
    assets = {a.get("name"): a for a in data.get("assets") or [] if isinstance(a, dict)}
    name = "FogTranslate-Setup-%s.exe" % version
    setup, sha = assets.get(name), assets.get(name + ".sha256")
    if not setup or not sha or not SETUP.match(name):
        raise ValueError("setup or checksum missing")
    base = DOWNLOAD_PREFIX + tag + "/"
    for asset, n in ((setup, name), (sha, name + ".sha256")):
        if asset.get("browser_download_url") != base + n:
            raise ValueError("download address is not this program's")
    size = int(setup.get("size") or 0)
    if not 0 < size <= MAX_BYTES:
        raise ValueError("unexpected size")
    digest = str(setup.get("digest") or "")
    digest = digest[len("sha256:"):] if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) else ""
    return Release(version, tag, name, base + name, size, base + name + ".sha256", digest)


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    """GitHub sends a release download on to its storage host – followed only to https."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not str(newurl).lower().startswith("https://"):
            raise urllib.error.URLError("redirect without https refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener():
    return urllib.request.build_opener(_HttpsOnly)


def transient(e: BaseException) -> bool:
    """A failure that may be gone in a few seconds (GitHub answers 502/503/504 now and then) – never a refusal
    (403, 404) or a wrong file."""
    if isinstance(e, urllib.error.HTTPError):
        return e.code in TRANSIENT_HTTP
    if isinstance(e, urllib.error.URLError):
        return isinstance(e.reason, (TimeoutError, ConnectionError))
    return isinstance(e, (TimeoutError, ConnectionError))


def _retrying(fn):
    total = len(RETRY_WAITS_S) + 1
    for n, wait in enumerate((0,) + tuple(RETRY_WAITS_S), start=1):
        if wait:
            SLEEP(wait)
        try:
            return fn()
        except Exception as e:
            if n == total or not transient(e):
                raise


def _get(url: str, opener, limit: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})

    def once():
        with opener.open(req, timeout=TIMEOUT_S) as r:
            return r.read(limit + 1)
    data = _retrying(once)
    if len(data) > limit:
        raise ValueError("answer too large")
    return data


def latest(opener=None) -> Release:
    return parse_release(json.loads(_get(API, opener or _opener(), MAX_JSON).decode("utf-8")))


def check(own_version: str, opener=None):
    """("current" | "available" | "error", Release or None, detail) – one read of GitHub, nothing else."""
    try:
        rel = latest(opener)
    except (OSError, ValueError) as e:
        return "error", None, type(e).__name__
    if version_tuple(rel.version) <= version_tuple(own_version):
        return "current", None, rel.version
    return "available", rel, rel.version


def expected_sha(rel: Release, opener=None) -> str:
    """The SHA-256 the release states: its .sha256 file (first word), equal to GitHub's digest when listed."""
    text = _get(rel.sha_url, opener or _opener(), 4096).decode("ascii", "replace").strip()
    word = (text.split() or [""])[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", word):
        raise ValueError("checksum file unreadable")
    if rel.digest and rel.digest != word:
        raise ValueError("checksums of GitHub and the release differ")
    return word


def update_folder(data_dir: str) -> str:
    return os.path.join(data_dir, UPDATE_DIR)


def _ours(name: str) -> bool:
    return bool(SETUP.match(name) or (name.endswith(".part") and SETUP.match(name[:-len(".part")])))


def download(rel: Release, data_dir: str, opener=None, progress=None) -> str:
    """Fetch the setup into ``data_dir/update``, check size and SHA-256; returns its path. A failed or wrong
    download leaves nothing behind; older setups there are removed."""
    opener = opener or _opener()
    want = expected_sha(rel, opener)
    folder = update_folder(data_dir)
    os.makedirs(folder, exist_ok=True)
    final = os.path.join(folder, rel.setup_name)
    tmp = final + ".part"
    req = urllib.request.Request(rel.setup_url, headers={"User-Agent": USER_AGENT})

    def once() -> str:
        h, got = hashlib.sha256(), 0
        with opener.open(req, timeout=TIMEOUT_S) as r, open(tmp, "wb") as fh:
            while True:
                block = r.read(CHUNK)
                if not block:
                    break
                got += len(block)
                if got > rel.size:
                    raise ValueError("download larger than announced")
                h.update(block)
                fh.write(block)
                if progress:
                    progress(got, rel.size)
        if got != rel.size:
            raise ValueError("download incomplete")
        return h.hexdigest()
    try:
        if _retrying(once) != want:
            raise ValueError("checksum does not match")
        if os.path.exists(final):
            os.remove(final)
        os.rename(tmp, final)
        rel.sha256 = want
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    for name in os.listdir(folder):                 # older setups and leftovers: only our own names
        if name != rel.setup_name and _ours(name):
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass
    return final


def clean_update_folder(data_dir: str) -> int:
    """At the start of the installed program: a setup still lying there was installed (this is the new version)
    or not wanted. Only our own names go. Returns how many."""
    folder, gone = update_folder(data_dir), 0
    try:
        names = os.listdir(folder)
    except OSError:
        return 0
    for name in names:
        if _ours(name):
            try:
                os.remove(os.path.join(folder, name))
                gone += 1
            except OSError:
                pass
    return gone


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def setup_still_ours(path: str, sha256: str, data_dir: str) -> bool:
    """Right before the start: our own setup name, in our update folder, and still the file that was checked."""
    path = os.path.abspath(path)
    if (os.path.normcase(os.path.dirname(path)) != os.path.normcase(os.path.abspath(update_folder(data_dir)))
            or not SETUP.match(os.path.basename(path))):
        return False
    try:
        return len(sha256) == 64 and os.path.isfile(path) and _file_sha256(path) == sha256.lower()
    except OSError:
        return False


def install_args() -> list[str]:
    """Progress only, no questions; ``/update=1`` makes the setup wait for the program to end and start the new
    version afterwards (installer/fogtranslate.iss)."""
    return ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/update=1"]


def child_env(env) -> dict:
    """The environment for the setup (and through it for the new version): without PyInstaller's own variables,
    which would make the new program look for the old one's files."""
    out = {k: v for k, v in env.items() if not k.upper().startswith("_PYI_") and k.upper() != "_MEIPASS2"}
    out["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return out


def start_setup(path: str, sha256: str, data_dir: str, popen=subprocess.Popen) -> bool:
    """Check the setup again and start it. True when it runs – the caller then ends the program."""
    if not setup_still_ours(path, sha256, data_dir):
        return False
    k32 = None
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
        k32.SetDllDirectoryW("")             # the setup gets Windows' own DLL search, not the bundle's folder
    try:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        popen([path, *install_args()], cwd=os.path.dirname(path), env=child_env(os.environ),
              creationflags=flags, close_fds=True)
        return True
    except OSError:
        return False
    finally:
        if k32 is not None:
            k32.SetDllDirectoryW(getattr(sys, "_MEIPASS", None))


_mutex = None


def claim_mutex() -> None:
    """Windows: hold ``MUTEX_NAME`` while the program runs, so the setup can wait for it to end. More than one
    copy may hold it."""
    global _mutex
    if sys.platform != "win32" or _mutex is not None:
        return
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    k32.CreateMutexW.restype = wintypes.HANDLE
    _mutex = k32.CreateMutexW(None, False, MUTEX_NAME)
