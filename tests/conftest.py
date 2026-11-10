import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import pytest


@pytest.fixture(autouse=True)
def _own_data_dir(tmp_path, monkeypatch):
    """Never the real settings folder; never a real key from the environment."""
    monkeypatch.setenv("FOGTRANSLATE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _english_window():
    """Every test starts and ends with the English texts, whatever a test before switched to."""
    from fogtranslate import i18n
    i18n.set_language("en")
    yield
    i18n.set_language("en")
