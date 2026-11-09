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


NETWORK = {"claude.py", "gemini.py", "ollama.py", "http.py"}     # the services and their HTTP helper only


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
        assert not re.search(r"log\w*\.\w+\(.*(api_key|key\b)", text), name
