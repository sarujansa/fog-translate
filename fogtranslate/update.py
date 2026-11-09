"""Updates – only when the user clicks.

* Installed with ``git clone``: ``git fetch`` of ``main`` from GitHub, then a fast-forward only (never with own
  changes, another branch or own commits) and a restart through ``start.bat``, which installs changed packages
  (``deps.py``).
* Installed from a ZIP: reads the version from GitHub (``raw.githubusercontent.com``) and offers the download page.
Nothing is sent about the user; no account, no token.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

from . import __version__

REPO_URL = "https://github.com/sarujansa/fog-translate"
RELEASES_URL = REPO_URL + "/releases/latest"
VERSION_URL = "https://raw.githubusercontent.com/sarujansa/fog-translate/main/fogtranslate/__init__.py"
BRANCH = "main"
GIT_TIMEOUT_S = 60
MAX_BYTES = 64 * 1024
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0        # CREATE_NO_WINDOW


@dataclass
class Check:
    state: str              # current | behind | ahead | dirty | branch | newer (ZIP) | error
    behind: int = 0
    remote_version: str = ""
    detail: str = ""


def version_tuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4])


def frozen() -> bool:
    """The installed .exe (PyInstaller) – updated by downloading the new setup from the release page."""
    return bool(getattr(sys, "frozen", False))


def download_page() -> str:
    return RELEASES_URL if frozen() else REPO_URL


def is_git_checkout(root: str = ROOT) -> bool:
    if frozen():
        return False
    return os.path.isdir(os.path.join(root, ".git")) and shutil.which("git") is not None


def _git(root: str, *args: str) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    out = subprocess.run(["git", "-c", "core.hooksPath=", "-C", root, *args], capture_output=True, text=True,
                         timeout=GIT_TIMEOUT_S, env=env, creationflags=_NO_WINDOW)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip().splitlines()[-1:] or ["git"])
    return out.stdout.strip()


def check(root: str = ROOT, git=None, fetch_version=None) -> Check:
    """What an update would do now (network: one git fetch, or one small HTTPS read)."""
    if git is None:
        if not is_git_checkout(root):
            return _check_zip(fetch_version)
        git = lambda *a: _git(root, *a)                 # noqa: E731
    try:
        if git("rev-parse", "--abbrev-ref", "HEAD") != BRANCH:
            return Check("branch")
        if git("status", "--porcelain", "--untracked-files=no"):
            return Check("dirty")
        git("fetch", "--quiet", "origin", BRANCH)
        ahead = int(git("rev-list", "--count", "origin/%s..HEAD" % BRANCH) or 0)
        behind = int(git("rev-list", "--count", "HEAD..origin/%s" % BRANCH) or 0)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as e:
        return Check("error", detail=type(e).__name__)
    if ahead:
        return Check("ahead")
    return Check("behind", behind) if behind else Check("current")


def apply(root: str = ROOT, git=None) -> bool:
    """Fast-forward to origin/main; False when that is not possible (nothing is changed then)."""
    git = git or (lambda *a: _git(root, *a))
    try:
        git("merge", "--ff-only", "--quiet", "origin/" + BRANCH)
        return True
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return False


def _fetch_version_text() -> str:
    import urllib.request
    with urllib.request.urlopen(VERSION_URL, timeout=15) as r:        # fixed https host, read only
        return r.read(MAX_BYTES).decode("utf-8", "replace")


def _check_zip(fetch_version=None) -> Check:
    try:
        text = (fetch_version or _fetch_version_text)()
    except (OSError, ValueError) as e:
        return Check("error", detail=type(e).__name__)
    m = re.search(r'__version__\s*=\s*"([0-9][0-9.]*)"', text)
    if not m:
        return Check("error", detail="version")
    remote = m.group(1)
    if version_tuple(remote) > version_tuple(__version__):
        return Check("newer", remote_version=remote)
    return Check("current", remote_version=remote)


def restart(root: str = ROOT) -> bool:
    """Start the program again through start.bat (it installs changed packages first). Windows only."""
    bat = os.path.join(root, "start.bat")
    if sys.platform != "win32" or not os.path.isfile(bat):
        return False
    os.startfile(bat)                                    # noqa: S606 – our own start.bat, absolute path
    return True
