"""Write the --hash lines of every pinned package in a requirements file (maintainer tool, needs the internet).

    python tools/hash_requirements.py requirements.txt [more files …]

Each line ``name==version [; marker]  # comment`` gets the SHA-256 of every wheel PyPI lists for exactly that
version (all platforms – pip only needs one of them to match). The comment moves to its own line above. Run it
after raising a version; the guard test_every_package_is_pinned_to_a_tested_version checks every line has hashes.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request

LINE = re.compile(r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-+!]+)\s*(;[^#\\]*)?\s*(#.*)?$")


def wheel_hashes(name: str, version: str) -> list[str]:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as r:        # fixed host, read-only
        data = json.load(r)
    out = sorted({f["digests"]["sha256"] for f in data.get("urls", []) if f.get("packagetype") == "bdist_wheel"})
    if not out:
        raise SystemExit(f"{name}=={version}: PyPI lists no wheels")
    return out


def rewrite(text: str) -> str:
    lines, out = text.splitlines(), []
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        while line.rstrip().endswith("\\") and i < len(lines):  # a continued (already hashed) entry: one line
            line = line.rstrip()[:-1] + " " + lines[i].strip()
            i += 1
        line = re.sub(r"\s*--hash=\S+", "", line)
        m = LINE.match(line.strip())
        if not m:
            out.append(line)
            continue
        name, version, marker, comment = m.groups()
        if comment:
            out.append(comment)
        head = f"{name}=={version}" + (f" {marker.strip()}" if marker else "")
        hashes = wheel_hashes(name, version)
        out.append(head + " \\")
        out.extend(f"    --hash=sha256:{h}" + (" \\" if k < len(hashes) - 1 else "") for k, h in enumerate(hashes))
    return "\n".join(out) + "\n"


def main(argv) -> int:
    for path in argv[1:]:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        new = rewrite(text)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
        print(path, "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
