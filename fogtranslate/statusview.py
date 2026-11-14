"""Pure: what the control window's head shows – the status line, the coloured dot, the hint for the one thing to do
next and the step "Show me" leads to. ``view`` decides, ``MainWindow._refresh`` only writes widgets (0.12: the logic
was mixed with the widget writes and testable only through the whole window)."""
from __future__ import annotations

from dataclasses import dataclass

from .i18n import N_

STATUS = {
    "idle": N_("Stopped."),
    "no_region": N_("No chat area marked yet."),
    "no_game": N_("Dead by Daylight not found – waiting."),
    "background": N_("DBD is not in the foreground – paused."),
    "covered": N_("A window covers the chat – paused until it is visible again."),
    "starting": N_("Starting …"),
    "watching": N_("Watching the chat …"),
    "no_chat": N_("Waiting for the chat … no text found in the marked area (never there? mark it again)"),
    "asking": N_("Translating …"),
    "cap": N_("Daily request limit reached – paused until tomorrow."),
    "error": N_("Error"),
    "unconfirmed": N_("Stopped: please confirm the notice below for this service, then press Start."),
}

# the line under the status: the one thing to do next
HINTS = {
    "notice": N_("Next: confirm the notice for this service."),
    "key": N_("Next: paste your API key."),
    "region": N_("Next: open Dead by Daylight with the chat visible, then mark the chat area."),
    "ready": N_("Everything is set up – press Start."),
    "no_game": N_("Open Dead by Daylight – the translation goes on by itself."),
    "bad_key": N_("Check the API key on the “Service” tab."),
    "cap": N_("You can raise the daily limit on the “Service” tab."),
    "running": N_("Translations appear above the chat."),
}


@dataclass(frozen=True)
class View:
    status: str          # key of STATUS (ignored when ``error``)
    error: bool          # show the engine's error text instead
    look: str            # dot: off / on / wait / bad
    hint: str            # key of HINTS, "" = none
    goal: str            # step "Show me" leads to, "" = no button
    step: str            # what Start still needs (notice / key / region / "")


def view(status: str, error: str, running: bool, step: str, no_text: bool) -> View:
    """``status``/``error`` of the engine, ``step`` = ``MainWindow.next_step()`` while stopped (else ""),
    ``no_text`` = the last look found no chat text."""
    shown = status if running or status not in ("watching", "starting") else "idle"
    if not running and step == "region":
        shown = "no_region"
    no_chat = False
    if status != "error" and running and status == "watching" and no_text:
        shown, no_chat = "no_chat", True
    look, hint, goal = "off", "", ""
    if status == "error":
        look = "bad"
        if error == "key" and not step:
            hint, goal = "bad_key", "key"
    elif running:
        look = "wait"
        if status == "cap":
            hint, goal = "cap", "cap"
        elif status == "no_game":
            hint = "no_game"
        elif status in ("watching", "asking") and not no_chat:
            look, hint = "on", "running"
    elif status == "unconfirmed":
        look = "bad"
    if step:
        hint, goal = step, step if step != "region" else ""
    elif not running and status != "error":
        hint = "ready"
    return View(shown, status == "error", look, hint, goal, step)
