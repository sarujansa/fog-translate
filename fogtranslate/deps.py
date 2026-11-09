"""Called by start.bat before each start: reinstalls the packages when requirements.txt changed (after an
update). Standard library only. The SHA-256 of the installed requirements.txt is kept in .venv."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQ = os.path.join(ROOT, "requirements.txt")
STAMP = os.path.join(ROOT, ".venv", "requirements.sha256")


def digest(path: str = REQ) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def needed(req: str = REQ, stamp: str = STAMP) -> bool:
    try:
        with open(stamp, encoding="ascii") as fh:
            return fh.read().strip() != digest(req)
    except OSError:
        return True


def main() -> int:
    if not needed():
        return 0
    print("Pakete werden aktualisiert ...")
    code = subprocess.call([sys.executable, "-m", "pip", "install", "--isolated", "--index-url",
                            "https://pypi.org/simple", "--require-hashes", "--only-binary=:all:", "-r", REQ])
    if code == 0:
        with open(STAMP, "w", encoding="ascii") as fh:
            fh.write(digest())
    return code


if __name__ == "__main__":
    sys.exit(main())
