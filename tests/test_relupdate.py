"""Updating the installed .exe from the GitHub releases (relupdate.py) – with a fake GitHub, nothing is fetched."""
import hashlib
import io
import json
import os
import urllib.error

import pytest

from fogtranslate import relupdate as r

SETUP = b"MZ" + bytes(range(256)) * 40
SHA = hashlib.sha256(SETUP).hexdigest()


def _release(version="1.2.3", **over):
    name = "FogTranslate-Setup-%s.exe" % version
    base = r.DOWNLOAD_PREFIX + "v%s/" % version
    data = {"tag_name": "v" + version, "draft": False, "prerelease": False, "assets": [
        {"name": name, "size": len(SETUP), "browser_download_url": base + name, "digest": "sha256:" + SHA},
        {"name": name + ".sha256", "size": 80, "browser_download_url": base + name + ".sha256"}]}
    data.update(over)
    return data


class FakeGitHub:
    """An opener: answers by address; ``fail`` = exceptions raised first, one per request."""

    def __init__(self, release=None, setup=SETUP, sha=None, fail=()):
        self.release = release or _release()
        self.setup, self.sha, self.fail, self.asked = setup, sha or SHA, list(fail), []

    def open(self, req, timeout=None):
        url = req.full_url
        self.asked.append(url)
        if self.fail:
            raise self.fail.pop(0)
        if url == r.API:
            return io.BytesIO(json.dumps(self.release).encode())
        if url.endswith(".sha256"):
            return io.BytesIO(("%s  setup.exe\n" % self.sha).encode())
        assert url.startswith(r.DOWNLOAD_PREFIX)
        return io.BytesIO(self.setup)


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    monkeypatch.setattr(r, "SLEEP", lambda s: None)


def test_a_newer_release_is_offered_and_an_older_or_equal_one_is_not():
    state, rel, _ = r.check("1.2.2", FakeGitHub())
    assert state == "available" and rel.version == "1.2.3" and rel.setup_url.startswith(r.DOWNLOAD_PREFIX)
    assert r.check("1.2.3", FakeGitHub())[0] == "current"
    assert r.check("1.10", FakeGitHub())[0] == "current"                 # 1.10 > 1.2.3: numbers, not text
    assert r.check("0.9", FakeGitHub(fail=[urllib.error.HTTPError(r.API, 404, "x", {}, None)]))[0] == "error"


@pytest.mark.parametrize("change", [
    {"draft": True}, {"prerelease": True}, {"tag_name": "build-7"}, {"tag_name": "v1.2.3-rc1"}, {"assets": []},
])
def test_only_a_release_as_the_workflow_makes_it_counts(change):
    with pytest.raises(ValueError):
        r.parse_release(_release(**change))


def test_a_download_address_outside_this_repository_is_refused():
    for i, bad in ((0, "https://github.com/someone/else/releases/download/v1.2.3/FogTranslate-Setup-1.2.3.exe"),
                   (0, "http://github.com/senisinx/fog-translate/releases/download/v1.2.3/FogTranslate-Setup-1.2.3.exe"),
                   (1, "https://example.com/FogTranslate-Setup-1.2.3.exe.sha256")):
        data = _release()
        data["assets"][i]["browser_download_url"] = bad
        with pytest.raises(ValueError):
            r.parse_release(data)
    data = _release()
    data["assets"][0]["size"] = r.MAX_BYTES + 1
    with pytest.raises(ValueError):
        r.parse_release(data)


def test_the_setup_is_kept_only_with_the_checksum_the_release_states(tmp_path):
    data = str(tmp_path)
    rel = r.parse_release(_release())
    path = r.download(rel, data, FakeGitHub())
    assert os.path.basename(path) == rel.setup_name and open(path, "rb").read() == SETUP and rel.sha256 == SHA
    assert r.setup_still_ours(path, rel.sha256, data)
    for fake in (FakeGitHub(setup=SETUP[:-1] + b"x"),                    # other content, same size
                 FakeGitHub(setup=SETUP + b"more"), FakeGitHub(setup=SETUP[:100]),
                 FakeGitHub(sha="0" * 64),                               # the .sha256 file and GitHub's digest differ
                 FakeGitHub(sha="not a checksum")):
        folder = str(tmp_path / str(id(fake)))
        with pytest.raises(ValueError):
            r.download(r.parse_release(_release()), folder, fake)
        assert not os.path.isdir(r.update_folder(folder)) or os.listdir(r.update_folder(folder)) == []


def test_a_busy_github_is_asked_again_but_a_refusal_is_not(tmp_path):
    busy = urllib.error.HTTPError(r.API, 503, "busy", {}, None)
    fake = FakeGitHub(fail=[busy, TimeoutError()])
    assert r.check("1.0", fake)[0] == "available" and len(fake.asked) == 3
    fake = FakeGitHub(fail=[urllib.error.HTTPError(r.API, 403, "rate limit", {}, None)])
    assert r.check("1.0", fake)[0] == "error" and len(fake.asked) == 1


def test_a_redirect_is_followed_only_to_https():
    h = r._HttpsOnly()
    req = r.urllib.request.Request(r.DOWNLOAD_PREFIX + "v1/x.exe")
    with pytest.raises(urllib.error.URLError):
        h.redirect_request(req, None, 302, "Found", {}, "http://objects.example/x.exe")
    assert h.redirect_request(req, None, 302, "Found", {}, "https://objects.example/x.exe") is not None


def test_only_the_checked_setup_in_our_folder_is_started(tmp_path):
    data = str(tmp_path)
    rel = r.parse_release(_release())
    path = r.download(rel, data, FakeGitHub())
    started = []
    popen = lambda args, **kw: started.append((args, kw))                 # noqa: E731
    assert r.start_setup(path, rel.sha256, data, popen) and len(started) == 1
    args, kw = started[0]
    assert args == [path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/update=1"]
    assert not any(k.upper().startswith("_PYI_") for k in kw["env"]) and kw["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    other = tmp_path / "elsewhere"
    other.mkdir()
    copy = other / rel.setup_name
    copy.write_bytes(SETUP)
    assert not r.start_setup(str(copy), rel.sha256, data, popen)          # same file, wrong folder
    renamed = os.path.join(r.update_folder(data), "setup.exe")
    os.rename(path, renamed)
    assert not r.start_setup(renamed, rel.sha256, data, popen)            # not our setup's name
    os.rename(renamed, path)
    with open(path, "ab") as fh:
        fh.write(b"!")
    assert not r.start_setup(path, rel.sha256, data, popen)               # changed since it was checked
    assert len(started) == 1

    def refuses(args, **kw):
        raise OSError("blocked")
    with open(path, "wb") as fh:
        fh.write(SETUP)
    assert r.start_setup(path, rel.sha256, data, refuses) is False


def test_old_setups_are_cleared_and_nothing_else(tmp_path):
    folder = r.update_folder(str(tmp_path))
    os.makedirs(folder)
    for name in ("FogTranslate-Setup-0.9.exe", "FogTranslate-Setup-1.0.exe.part", "notes.txt", "other.exe"):
        open(os.path.join(folder, name), "wb").close()
    assert r.clean_update_folder(str(tmp_path)) == 2
    assert sorted(os.listdir(folder)) == ["notes.txt", "other.exe"]
    assert r.clean_update_folder(str(tmp_path / "missing")) == 0
