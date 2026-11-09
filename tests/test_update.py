import hashlib

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
    assert update.download_page() == "https://github.com/sarujansa/fog-translate/releases/latest"
    c = update.check(fetch_version=lambda: '__version__ = "99.0"')
    assert c.state == "newer"
