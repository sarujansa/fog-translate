"""Rules that keep the program safe next to Dead by Daylight (see CLAUDE.md)."""
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fogtranslate")

FORBIDDEN = [
    # input to the game
    "SendInput", "keybd_event", "mouse_event", "PostMessage", "SendMessage", "SetWindowsHookEx",
    "RegisterRawInputDevices", "GetAsyncKeyState", "GetKeyboardState",
    # the game process
    "OpenProcess", "ReadProcessMemory", "WriteProcessMemory", "CreateRemoteThread", "GetWindowThreadProcessId",
    "PrintWindow", "EnumProcessModules",
    # may send the window a message (and block while the game is busy)
    "GetWindowTextLength", "GetWindowTextLengthW",
]


def _sources():
    for name in sorted(os.listdir(ROOT)):
        if name.endswith(".py"):
            with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
                yield name, fh.read()


def test_no_input_or_process_apis():
    for name, text in _sources():
        for word in FORBIDDEN:
            assert not re.search(r"\b" + word + r"\b", text), (name, word)


NETWORK = {"claude.py", "gemini.py", "ollama.py", "http.py",     # the services and their HTTP helper
           "update.py", "relupdate.py"}                         # GitHub, only on the user's click


def test_only_the_services_talk_to_the_network():
    for name, text in _sources():
        if name in NETWORK:
            continue
        assert not re.search(r"^\s*(import|from)\s+(anthropic|urllib|http|socket|requests)\b", text, re.M), name
        assert not re.search(r"^\s*from\s+\.\s+import\s+.*\bhttp\b", text, re.M), name


def test_each_service_reaches_only_its_own_host():
    import fogtranslate.gemini as gemini
    import fogtranslate.ollama as ollama
    assert gemini.HOST == "https://generativelanguage.googleapis.com"
    assert ollama.HOST == "127.0.0.1"
    assert ollama.base_url(99999) == "http://127.0.0.1:11434"


def test_the_key_never_goes_to_the_log():
    for name, text in _sources():
        # an API key: "api_key", "…_key" or the word "key" – not "hotkey" (a key combination, no secret)
        assert not re.search(r"log\w*\.\w+\(.*(api_key|_key\b|\bkey\b)", text.replace("hide_hotkey", "")), name


def test_every_package_is_listed_in_third_party():
    root = os.path.dirname(ROOT)
    with open(os.path.join(root, "requirements.txt"), encoding="utf-8") as fh:
        names = [re.split(r"==", line)[0].strip() for line in fh if re.match(r"^[A-Za-z]", line)]
    with open(os.path.join(root, "THIRD_PARTY.md"), encoding="utf-8") as fh:
        listed = fh.read().lower().replace("_", "-")
    missing = [n for n in names if n.lower().replace("_", "-") not in listed]
    assert not missing, missing


def test_the_license_keeps_modifying_behind_permission():
    root = os.path.dirname(ROOT)
    with open(os.path.join(root, "LICENSE"), encoding="utf-8") as fh:
        text = fh.read()
    assert "written permission" in text and "schriftlicher Erlaubnis" in text


WORKFLOWS = os.path.join(os.path.dirname(ROOT), ".github", "workflows")


def _workflow(name):
    with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as fh:
        return fh.read()


def test_every_action_is_pinned_to_a_full_commit_sha():
    for name in sorted(os.listdir(WORKFLOWS)):
        if not name.endswith((".yml", ".yaml")):
            continue
        uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)(.*)$", _workflow(name), re.M)
        assert uses, name
        for ref, comment in uses:
            assert re.fullmatch(r"actions/[\w.-]+@[0-9a-f]{40}", ref), (name, ref)   # only GitHub's own actions
            assert re.search(r"#\s*v\d", comment), (name, ref, "the tag belongs in the comment")


def test_only_the_release_job_may_write_and_attest():
    wf = _workflow("build.yml")
    head, release = wf[:wf.index("\njobs:")], wf[wf.index("\n  release:"):]
    assert "permissions:\n  contents: read" in head and "permissions:\n  contents: read" in _workflow("tests.yml")
    assert "if: github.event_name == 'push' && github.ref == 'refs/heads/main'" in release
    for right in ("contents: write", "id-token: write", "attestations: write"):
        assert len(re.findall(r"^ +%s\b" % right, wf, re.M)) == 1 and right in release, right
    assert "actions/attest-build-provenance@" in release
    assert release.index("attest-build-provenance") < release.index("gh release create")


def test_the_updater_reaches_only_this_repository_on_github():
    import fogtranslate.relupdate as r
    assert r.API == "https://api.github.com/repos/senisinx/fog-translate/releases/latest"
    assert r.DOWNLOAD_PREFIX == "https://github.com/senisinx/fog-translate/releases/download/"
    with open(os.path.join(ROOT, "relupdate.py"), encoding="utf-8") as fh:
        text = fh.read()
    assert set(re.findall(r"https://[^\s\"']+", text)) <= {r.API.replace(r.REPO, "%s"), r.DOWNLOAD_PREFIX.replace(r.REPO, "%s")}


def test_the_setup_waits_for_the_program_by_the_same_mutex_name():
    import fogtranslate.relupdate as r
    with open(os.path.join(os.path.dirname(ROOT), "installer", "fogtranslate.iss"), encoding="utf-8") as fh:
        iss = fh.read()
    assert "MutexName = '%s';" % r.MUTEX_NAME in iss
    assert "Check: IsUpdate" in iss and "/update=1" in r.install_args()
    for lang in ("Italian", "Russian", "ChineseSimplified", "Japanese", "Korean"):
        assert "compiler:Languages\\%s.isl" % lang in iss
