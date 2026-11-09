"""The translation services the user can choose, and building the chosen one from the settings."""
from __future__ import annotations

from . import claude, gemini, ollama

SERVICES = {                     # id → (label, sends to the internet)
    "claude": ("Claude (Anthropic)", True),
    "gemini": ("Gemini (Google, kostenlos möglich)", True),
    "ollama": ("Ollama (lokal, offline)", False),
}
DEFAULT = "claude"
KEY_SETTING = {"claude": "claude_key", "gemini": "gemini_key"}
MODEL_SETTING = {"claude": "claude_model", "gemini": "gemini_model", "ollama": "ollama_model"}
DEFAULT_MODEL = {"claude": claude.DEFAULT_MODEL, "gemini": gemini.DEFAULT_MODEL, "ollama": ollama.DEFAULT_MODEL}
KEY_URL = {"claude": "https://console.anthropic.com/settings/keys", "gemini": "https://aistudio.google.com/apikey"}


def is_cloud(service: str) -> bool:
    return SERVICES.get(service, SERVICES[DEFAULT])[1]


def model_choices(service: str) -> list[tuple[str, str]]:
    """(id, label) offered in the model list (Ollama: filled from the local installation by the window)."""
    if service == "claude":
        return [(m, v[0]) for m, v in claude.MODELS.items()]
    if service == "gemini":
        return list(gemini.MODELS.items())
    return [(m, m) for m in ollama.SUGGESTED]


def valid_model(service: str, model: str) -> bool:
    if service == "claude":
        return model in claude.MODELS
    if service == "gemini":
        return gemini.valid_model(model)
    return ollama.valid_model(model)


def make(settings):
    """The translator for the chosen service (raises TranslateError("key") without a key)."""
    service = settings["service"]
    model = settings[MODEL_SETTING[service]]
    target = settings["target"]
    if service == "claude":
        return claude.Translator(settings.api_key("claude"), model, target)
    if service == "gemini":
        return gemini.Translator(settings.api_key("gemini"), model, target)
    return ollama.Translator(model, target, int(settings["ollama_port"]))
