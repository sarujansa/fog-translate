"""Marking the region (offscreen Qt): a new box can be drawn anywhere, also inside the old one."""
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fogtranslate import geometry  # noqa: E402
from fogtranslate.picker import RegionPicker  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _drag(w, a, b):
    QTest.mousePress(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*a))
    QTest.mouseMove(w, QPoint(*b))
    QTest.mouseRelease(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*b))


def test_a_new_box_replaces_the_old_one_even_when_started_inside_it(app):
    got = []
    old = (0.02, 0.6, 0.08, 0.2)                       # Saru's narrow box
    picker = RegionPicker((0, 0, 1920, 1080), got.append, old)
    picker.start()
    ox, oy, ow, oh = geometry.from_relative(old, picker.view)
    _drag(picker, (ox + 10, oy + 10), (ox + 600, oy + 300))   # starts inside the old box
    assert len(got) == 1 and got[0][2] > old[2] * 3
    assert not picker.isVisible()


def test_no_pixel_of_the_picker_is_fully_transparent(app):
    picker = RegionPicker((0, 0, 400, 300), lambda rel: None, (0.1, 0.1, 0.5, 0.5))
    picker.resize(400, 300)
    img = picker.grab().toImage()
    for x, y in ((5, 5), (200, 150), (100, 100), (395, 295)):
        assert img.pixelColor(x, y).alpha() > 0, (x, y)


def test_escape_cancels(app):
    got = []
    picker = RegionPicker((0, 0, 800, 600), got.append)
    picker.start()
    QTest.keyClick(picker, Qt.Key.Key_Escape)
    assert got == [None]
