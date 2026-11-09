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


def test_only_the_translator_talks_to_the_internet():
    for name, text in _sources():
        if name == "translate.py":
            continue
        assert not re.search(r"^\s*(import|from)\s+(anthropic|urllib|http|socket|requests)\b", text, re.M), name


def test_the_key_never_goes_to_the_log():
    for name, text in _sources():
        assert not re.search(r"log\w*\.\w+\(.*(api_key|key\b)", text), name
