"""The update button of the control window: check → (download → install | update and restart), each on its own
click, never by itself (hard rule in CLAUDE.md). Git/ZIP installations use ``update.py``, the installed .exe
``relupdate.py``. A mix-in of ``app.MainWindow``: it uses the window's ``results`` queue, ``update_btn``, ``_say``,
``running``/``toggle`` and ``quit``."""
from __future__ import annotations

import logging
import sys
import time

from PySide6.QtWidgets import QApplication

from . import __version__
from .i18n import N_, tr

log = logging.getLogger(__name__)


class UpdateFlow:
    def _init_update_state(self):
        self._update = None          # last update.Check (git / ZIP installation)
        self._release = None         # installed .exe: the release found, then (path, sha256) once downloaded
        self._setup_file = None
        self._downloading = False
        self._update_note = ("", 0.0)    # the check's result on the button itself, until then (where the click was)

    UPDATE_TEXT = {
        "current": N_("Fog Translate is up to date."),
        "dirty": N_("Cannot update: files in the program folder were changed."),
        "branch": N_("Cannot update: not on the \"main\" branch."),
        "ahead": N_("Cannot update: the program folder has its own commits."),
        "error": N_("Update check failed (no connection to GitHub?)."),
    }

    def _update_button(self):
        """The button says what the next click does."""
        c, text, on = self._update, tr("Check for updates"), True
        if self._downloading:
            text, on = tr("Downloading …"), False
        elif self._setup_file is not None:
            text = tr("Install and restart")
        elif self._release is not None:
            text = tr("Download update")
        elif c is not None and c.state == "behind":
            text = tr("Update and restart")
        elif c is not None and c.state == "newer":
            text = tr("Open download page")
        elif self._update_note[1] > time.monotonic():
            text = self._update_note[0]
        self.update_btn.setText(text)
        self.update_btn.setEnabled(on)

    def _self_updating(self) -> bool:
        """The installed .exe on Windows updates itself from the releases (relupdate.py)."""
        from . import update
        return update.frozen() and sys.platform == "win32"

    def update_clicked(self):
        from . import update
        if self._setup_file is not None:
            self._release_install()
            return
        if self._release is not None:
            self._release_download()
            return
        c = self._update
        if c is not None and c.state == "behind":
            self._update_apply()
            return
        if c is not None and c.state == "newer":
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(update.download_page()))
            return
        self.update_btn.setEnabled(False)
        self.update_btn.setText(tr("Checking …"))
        import threading
        if self._self_updating():
            from . import relupdate
            work = lambda: self.results.put(("release", relupdate.check(__version__)))      # noqa: E731
        else:
            work = lambda: self.results.put(("update", update.check()))                    # noqa: E731
        threading.Thread(target=work, name="update", daemon=True).start()

    def _update_checked(self, c):
        self._update = c
        if c.state == "behind":
            self._say(tr("Update available (%d changes).") % c.behind)
        elif c.state == "newer":
            self._say(tr("Version %s is available (installed: %s).") % (c.remote_version, __version__))
        else:
            self._say(tr(self.UPDATE_TEXT.get(c.state, c.state)))
            self._note_update(c.state)
        self._update_button()
        log.info("Update-Prüfung: %s", c.state)

    def _note_update(self, state: str, seconds: float = 6.0):
        """Nothing to install: say so on the button too – the status line is at the other end of the window, and
        the button only flickering looked as if nothing had happened (Saru, 11.11.2026)."""
        text = {"current": tr("Up to date"), "error": tr("Check failed")}.get(state)
        if text:
            self._update_note = (text, time.monotonic() + seconds)

    # the installed .exe: check → download → install, each on its own click
    def _release_checked(self, value):
        state, rel, detail = value
        self._release = rel
        if state == "available":
            self._say(tr("Version %s is available (installed: %s).") % (rel.version, __version__))
        else:
            state = "current" if state == "current" else "error"
            self._say(tr(self.UPDATE_TEXT[state]))
            self._note_update(state)
        self._update_button()
        log.info("Update-Prüfung: %s %s", state, detail)

    def _release_download(self):
        from . import relupdate
        from .config import data_dir
        rel, put, folder = self._release, self.results.put, data_dir()
        self._downloading = True
        self._update_button()
        self._say(tr("Downloading version %s …") % rel.version, 600)

        def work():
            try:
                put(("downloaded", (relupdate.download(rel, folder), rel.sha256)))
            except (OSError, ValueError) as e:
                log.warning("Update: Download fehlgeschlagen (%s: %s)", type(e).__name__, e)
                put(("downloaded", None))

        import threading
        threading.Thread(target=work, name="update", daemon=True).start()

    def _release_downloaded(self, value):
        self._downloading = False
        self._setup_file = value
        if value is None:
            self._say(tr("Download failed or the file did not match its checksum – nothing was installed."))
        else:
            self._say(tr("Version %s is downloaded and checked. Click “Install and restart”.")
                      % self._release.version, 600)
        self._update_button()

    def _release_install(self):
        """Start the checked setup and end the program; the setup waits for that and starts the new version."""
        from . import relupdate
        from .config import data_dir
        path, sha = self._setup_file
        if self.running:
            self.toggle()
        if not relupdate.start_setup(path, sha, data_dir()):
            self._setup_file = None
            self._say(tr("Update failed (see log)."))
            self._update_button()
            log.warning("Update: Setup nicht gestartet")
            return
        log.info("Update: Setup gestartet, Programm endet")
        self.quit()

    def _update_apply(self):
        from . import update
        if self.running:
            self.toggle()
        if not update.apply():
            self._update = None
            self._update_button()
            self._say(tr("Update failed (see log)."))
            log.warning("Update: Fast-Forward nicht möglich")
            return
        log.info("Update installiert, Neustart")
        if update.restart():
            self.close()
            QApplication.quit()
        else:
            self._say(tr("Update installed – please restart Fog Translate."))
