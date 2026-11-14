import json

import numpy as np
import pytest

from fogtranslate import gemini, http, ollama, services
from fogtranslate.config import Settings
from fogtranslate.translate import SCHEMA, TranslateError

ANSWER = {"lines": [{"sender": "Ana", "text": "oi", "language": "pt", "translation": "hallo", "translate": True}]}


def _img():
    img = np.zeros((120, 400, 3), np.uint8)
    img[::10] = 200
    return img


class FakePost:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body, timeout))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def _gemini_ok(answer=ANSWER):
    return 200, {"candidates": [{"finishReason": "STOP",
                                 "content": {"parts": [{"text": json.dumps(answer)}]}}]}


# ---------------------------------------------------------------- Gemini
def test_gemini_sends_the_key_in_a_header_and_the_picture_inline():
    post = FakePost(_gemini_ok())
    res = gemini.Translator("AIza-test", "gemini-flash-latest", "de", post=post).request(_img())
    assert [ln.translation for ln in res.lines] == ["hallo"]
    method, url, headers, body, _ = post.calls[0]
    assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
    assert "AIza-test" not in url and headers == {"x-goog-api-key": "AIza-test"}
    parts = body["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "image/png" and parts[1]["text"] == "Target language: German."
    assert body["generationConfig"]["responseJsonSchema"] == SCHEMA


def test_gemini_falls_back_to_the_older_schema_field_once():
    refused = (400, {"error": {"message": "Unknown name \"responseJsonSchema\" at 'generation_config'"}})
    post = FakePost(refused, _gemini_ok())
    gemini.Translator("k", post=post).request(_img())
    second = post.calls[1][3]["generationConfig"]
    assert "responseJsonSchema" not in second
    assert "additionalProperties" not in json.dumps(second["responseSchema"])


@pytest.mark.parametrize("answer,kind", [
    ((400, {"error": {"details": [{"reason": "API_KEY_INVALID"}]}}), "key"),
    ((403, {}), "key"),
    ((429, {}), "quota"),
    ((404, {}), "model"),
    ((200, {"promptFeedback": {"blockReason": "SAFETY"}}), "refused"),
    ((200, {"candidates": [{"finishReason": "SAFETY"}]}), "refused"),
    ((200, {"candidates": [{"content": {"parts": [{"text": "kein json"}]}}]}), "answer"),
    (http.NetError("timeout"), "net"),
])
def test_gemini_errors_become_kinds(answer, kind):
    with pytest.raises(TranslateError) as e:
        gemini.Translator("k", post=FakePost(answer)).request(_img())
    assert e.value.kind == kind


def test_gemini_ignores_thought_parts_and_rejects_odd_model_names():
    ok = (200, {"candidates": [{"content": {"parts": [{"text": "…", "thought": True},
                                                      {"text": json.dumps(ANSWER)}]}}]})
    assert len(gemini.Translator("k", post=FakePost(ok)).request(_img()).lines) == 1
    assert gemini.Translator("k", "../evil?key=x", post=FakePost()).model == gemini.DEFAULT_MODEL
    with pytest.raises(TranslateError):
        gemini.Translator("")


# ---------------------------------------------------------------- Ollama
def test_ollama_talks_only_to_the_local_port_and_asks_for_the_schema():
    post = FakePost((200, {"message": {"content": json.dumps(ANSWER)}}))
    res = ollama.Translator("qwen2.5vl:7b", "de", 11434, post=post).request(_img())
    assert res.cost_usd == 0 and res.lines[0].translation == "hallo"
    method, url, headers, body, _ = post.calls[0]
    assert url == "http://127.0.0.1:11434/api/chat" and headers is None
    assert body["format"] == SCHEMA and body["stream"] is False
    assert body["messages"][1]["images"] and body["model"] == "qwen2.5vl:7b"


@pytest.mark.parametrize("answer,kind", [((404, {}), "model"), (http.NetError("refused"), "server"),
                                         ((500, {}), "other"), ((200, {"message": {"content": "x"}}), "answer")])
def test_ollama_errors_become_kinds(answer, kind):
    with pytest.raises(TranslateError) as e:
        ollama.Translator(post=FakePost(answer)).request(_img())
    assert e.value.kind == kind


def test_ollama_lists_installed_models_and_copes_with_no_server():
    get = FakePost((200, {"models": [{"name": "qwen2.5vl:7b"}, {"name": "gemma3:4b"}, {"name": "bad name!"}]}))
    assert ollama.installed_models(11434, get=get) == ["gemma3:4b", "qwen2.5vl:7b"]
    assert get.calls[0][1] == "http://127.0.0.1:11434/api/tags"
    assert ollama.installed_models(get=FakePost(http.NetError("x"))) == []


# ---------------------------------------------------------------- choosing + settings
def test_the_chosen_service_is_built_from_the_settings():
    s = Settings()
    s["service"] = "ollama"
    s["ollama_port"] = 12000
    t = services.make(s)
    assert isinstance(t, ollama.Translator) and t.url == "http://127.0.0.1:12000/api/chat"
    s["service"] = "gemini"
    with pytest.raises(TranslateError) as e:
        services.make(s)                          # no key yet
    assert e.value.kind == "key"


def test_only_cloud_services_need_the_notice():
    s = Settings()
    assert s.accepted("ollama") and not s.accepted("gemini")
    s.set_accepted("gemini", True)
    assert s.accepted("gemini") and not s.accepted("claude")


def test_settings_of_version_0_1_are_taken_over(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps(
        {"api_key": "dpapi:abc", "model": "claude-haiku-5-5", "accepted": True}), encoding="utf-8")
    s = Settings(str(tmp_path))
    assert s["claude_key"] == "dpapi:abc" and s["claude_model"] == "claude-haiku-5-5"
    assert s["accepted"] == ["claude"] and s["service"] == "claude"


def test_keys_are_kept_per_service(monkeypatch):
    s = Settings()
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    s.set_api_key("claude", "sk-ant-1")
    assert s.api_key("claude") == "sk-ant-1"
    assert s.api_key("gemini") == "from-env" and s.api_key("ollama") == ""


def test_claude_needs_no_sdk():
    """0.12: one POST through http.py instead of the anthropic SDK (pydantic, httpx …, seconds to import)."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "fogtranslate", "claude.py"), encoding="utf-8") as fh:
        assert "import anthropic" not in fh.read()
    with open(os.path.join(root, "requirements.txt"), encoding="utf-8") as fh:
        assert "anthropic==" not in fh.read()
