"""The translation services the user can choose, and building the chosen one from the settings."""
from __future__ import annotations

from . import claude, gemini, ollama
from .i18n import N_

SERVICES = {                     # id → (label, sends to the internet)
    "claude": ("Claude (Anthropic)", True),
    "gemini": (N_("Gemini (Google, free tier available)"), True),
    "ollama": (N_("Ollama (local, offline)"), False),
}
DEFAULT = "claude"
KEY_SETTING = {"claude": "claude_key", "gemini": "gemini_key"}
MODEL_SETTING = {"claude": "claude_model", "gemini": "gemini_model", "ollama": "ollama_model"}
DEFAULT_MODEL = {"claude": claude.DEFAULT_MODEL, "gemini": gemini.DEFAULT_MODEL, "ollama": ollama.DEFAULT_MODEL}
KEY_URL = {"claude": "https://console.anthropic.com/settings/keys", "gemini": "https://aistudio.google.com/apikey"}


ERRORS = {
    "key": N_("API key missing or invalid."),
    "quota": N_("Rate limit, quota or credit of the service reached."),
    "net": N_("No connection to the service."),
    "refused": N_("The service declined this request."),
    "answer": N_("Could not read the service's answer."),
    "model": N_("Model not found – check the name (Ollama: \"ollama pull <model>\")."),
    "server": N_("Ollama is not running (or a different port is set)."),
    "other": N_("Unexpected error (see log)."),
}
NOTICES = {
    "claude": N_("The picture of the marked area (it can show player names and other players' messages) is sent to "
               "Anthropic for translation – with your own API key, at your own cost."),
    "gemini": N_("The picture of the marked area (it can show player names and other players' messages) is sent to "
               "Google for translation. On the free tier Google may use the data to improve its products, and "
               "humans may read it."),
    "ollama": N_("Ollama runs on your PC – the picture never leaves it. Install Ollama (ollama.com) and pull a vision "
               "model, e.g. \"ollama pull qwen2.5vl:7b\" (about 6 GB, needs a GPU with 8 GB or more) or "
               "\"gemma3:4b\" for smaller cards."),
}


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


def test_request(settings, make_translator=None):
    """"Test service": one request with the made-up ``translate.sample_picture`` (never the screen) → ``Result``
    with ``seconds`` set, or ``TranslateError``. Blocking – call it from a thread. One implementation for the
    window and the setup assistant (0.12: the assistant's copy did not count the request)."""
    import logging
    import time
    from . import translate
    t0 = time.monotonic()
    try:
        result = (make_translator or make)(settings).request(translate.sample_picture())
        result.seconds = time.monotonic() - t0
        return result
    except translate.TranslateError as e:
        return e
    except Exception as e:
        logging.getLogger(__name__).exception("Test failed")
        return translate.TranslateError("other", type(e).__name__)


def count_test(settings, outcome, now=None) -> None:
    """A test is a request (CLAUDE.md): counted like one – an answer with its cost, and an error the service
    charged for (``engine.BILLED_ERRORS``) – and saved."""
    from datetime import datetime
    from .engine import BILLED_ERRORS
    from .translate import TranslateError
    if isinstance(outcome, TranslateError):
        if outcome.kind not in BILLED_ERRORS:
            return
        usd = 0.0
    else:
        usd = outcome.cost_usd
    now = now or datetime.now()
    settings.count_request(now.strftime("%Y-%m-%d"), now.strftime("%Y-%m"), usd)
    settings.save()
