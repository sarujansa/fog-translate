import hashlib
import shutil

import pytest

from fogtranslate import deps, update


class FakeGit:
    def __init__(self, branch="main", dirty="", ahead="0", behind="0", fail=None):
        self.answers = {"rev-parse": branch, "status": dirty, "fetch": ""}
        self.counts = {"origin/main..HEAD": ahead, "HEAD..origin/main": behind}
        self.fail = fail
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if self.fail and args[0] == self.fail:
            raise RuntimeError("no network")
        if args[0] == "rev-list":
            return self.counts[args[-1]]
        return self.answers.get(args[0], "")


def test_an_update_is_offered_only_on_a_clean_main():
    assert update.check(git=FakeGit(behind="3")).state == "behind"
    assert update.check(git=FakeGit(behind="3")).behind == 3
    assert update.check(git=FakeGit()).state == "current"
    assert update.check(git=FakeGit(branch="dev")).state == "branch"
    assert update.check(git=FakeGit(dirty=" M fogtranslate/app.py")).state == "dirty"
    assert update.check(git=FakeGit(ahead="1", behind="2")).state == "ahead"
    assert update.check(git=FakeGit(fail="fetch")).state == "error"


def test_nothing_is_fetched_before_branch_and_changes_are_checked():
    g = FakeGit(dirty=" M x")
    update.check(git=g)
    assert ("fetch", "--quiet", "origin", "main") not in g.calls


def test_a_clone_from_the_old_account_is_moved_to_the_new_address(tmp_path):
    """0.9.4: an origin under the old GitHub name is set to REPO_URL before the fetch – real git, temp folder."""
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    repo = str(tmp_path)
    git = lambda *a: update._git(repo, *a)                                   # noqa: E731
    git("init", "-q")
    for old in ("https://github.com/{}/fog-translate.git", "https://github.com/{}/Fog-Translate",
                "git@github.com:{}/fog-translate.git"):
        git("remote", "add", "origin", old.format(update.OLD_OWNER))
        assert update.move_origin(git) is True
        assert git("config", "--get", "remote.origin.url") == update.REPO_URL + ".git"
        git("remote", "remove", "origin")
    for other in ("https://github.com/someone/fog-translate.git", "https://example.com/{}/fog-translate.git",
                  "https://github.com/{}/fog-translate.git.evil"):
        git("remote", "add", "origin", other.format(update.OLD_OWNER))
        assert update.move_origin(git) is False
        assert git("config", "--get", "remote.origin.url") == other.format(update.OLD_OWNER)
        git("remote", "remove", "origin")
    assert update.move_origin(git) is False                                  # no origin at all


def test_the_check_moves_the_origin_before_it_fetches():
    g = FakeGit()
    g.answers["config"] = "https://github.com/%s/fog-translate.git" % update.OLD_OWNER
    update.check(git=g)
    names = [c[0] for c in g.calls]
    assert names.index("remote") < names.index("fetch")
    assert ("remote", "set-url", "origin", update.REPO_URL + ".git") in g.calls


def test_applying_is_fast_forward_only():
    g = FakeGit()
    assert update.apply(git=g) is True
    assert g.calls == [("merge", "--ff-only", "--quiet", "origin/main")]
    assert update.apply(git=FakeGit(fail="merge")) is False


def test_a_zip_install_compares_the_version_on_github(monkeypatch):
    monkeypatch.setattr(update, "__version__", "0.3")
    c = update._check_zip(lambda: '__version__ = "0.10"\n')
    assert c.state == "newer" and c.remote_version == "0.10"           # 0.10 > 0.3, not a string compare
    assert update._check_zip(lambda: '__version__ = "0.3"').state == "current"
    assert update._check_zip(lambda: "<html>").state == "error"


def test_packages_are_reinstalled_only_when_requirements_changed(tmp_path):
    req = tmp_path / "requirements.txt"
    stamp = tmp_path / "stamp"
    req.write_bytes(b"a==1\n")                                         # bytes: no \r\n on Windows
    assert deps.needed(str(req), str(stamp))                           # first start
    stamp.write_text(hashlib.sha256(b"a==1\n").hexdigest())
    assert not deps.needed(str(req), str(stamp))
    req.write_bytes(b"a==2\n")                                           # after an update
    assert deps.needed(str(req), str(stamp))


def test_the_installed_exe_never_uses_git_and_points_to_the_releases(monkeypatch):
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert update.frozen() and not update.is_git_checkout()
    assert update.download_page() == "https://github.com/senisinx/fog-translate/releases/latest"
    c = update.check(fetch_version=lambda: '__version__ = "99.0"')
    assert c.state == "newer"
