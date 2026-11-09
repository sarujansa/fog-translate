"""Marking the region (offscreen Qt): a new box can be drawn anywhere, also inside the old one."""
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import numpy as np  # noqa: E402

from fogtranslate import geometry  # noqa: E402
from fogtranslate.picker import RegionPicker  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _drag(w, a, b):
    QTest.mousePress(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*a))
    QTest.mouseMove(w, QPoint(*b))
    QTest.mouseRelease(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*b))


def _picture(w=3440, h=1440):
    return np.zeros((h, w, 3), np.uint8)


def test_the_box_is_marked_in_picture_pixels_even_when_the_picture_is_shown_smaller(app):
    """Saru's screen: 3440 × 1440 picture shown at a quarter size – the saved area is the dragged part of the
    picture, i.e. of the screen."""
    got = []
    picker = RegionPicker(_picture(), got.append)
    picker.canvas.resize(860, 360)                     # exactly 1/4
    assert not picker.save_btn.isEnabled()
    _drag(picker.canvas, (125, 250), (275, 325))       # picture 500..1100 × 1000..1300
    assert picker.save_btn.isEnabled()
    picker.save()
    view = geometry.viewport(3440, 1440)
    assert geometry.from_relative(got[0], view) == (500, 1000, 600, 300)


def test_marking_again_replaces_the_old_box_wherever_the_new_one_starts(app):
    got = []
    old = (0.02, 0.6, 0.08, 0.2)
    picker = RegionPicker(_picture(1920, 1080), got.append, old)
    picker.canvas.resize(1920, 1080)
    ox, oy, _, _ = geometry.from_relative(old, picker.view)
    _drag(picker.canvas, (ox + 10, oy + 10), (ox + 600, oy + 300))
    QTest.keyClick(picker, Qt.Key.Key_Return)
    assert len(got) == 1 and got[0][2] > old[2] * 3


def test_cancel_escape_and_closing_return_nothing_once(app):
    for how in ("cancel", "esc", "close"):
        got = []
        picker = RegionPicker(_picture(800, 450), got.append, (0.1, 0.1, 0.3, 0.3))
        picker.show()
        if how == "cancel":
            picker.cancel()
        elif how == "esc":
            QTest.keyClick(picker, Qt.Key.Key_Escape)
        else:
            picker.close()
        assert got == [None], how


def test_marking_needs_the_game_window(app):
    from fogtranslate.app import MainWindow
    from fogtranslate.config import Settings
    win = MainWindow(Settings())
    win.pick_region()                                  # no DBD here
    assert "Open Dead by Daylight" in win.status.text() and win.picker is None
    win.close()


def test_the_overlay_is_placed_and_blacked_out_in_screen_pixels(app, monkeypatch):
    from fogtranslate import qtgeom
    from fogtranslate.lines import ChatLine
    from fogtranslate.overlay import TranslationOverlay
    monkeypatch.setattr(qtgeom, "ratio", lambda: 1.25)
    o = TranslationOverlay(18)
    seen = []

    def spot(size):
        seen.append(size)
        return (1000, 500)

    o.show_lines([ChatLine("Meg", "привет", "ru", "hallo", True)], spot)
    w, h = o.width(), o.height()
    assert seen[0] == (round(w * 1.25), round(h * 1.25))
    assert (o.x(), o.y()) == (800, 400)
    assert o.rect_on_screen == (1000, 500, round(w * 1.25), round(h * 1.25))
    o.close()


def test_the_picker_opens_on_a_picture_of_the_game_window(app, monkeypatch):
    from types import SimpleNamespace
    from fogtranslate import grab
    from fogtranslate.app import MainWindow
    from fogtranslate.config import Settings

    boxes = []

    class FakeGrabber:
        def grab(self, box):
            boxes.append(box)
            return _picture(box[2], box[3])

        def close(self):
            pass

    monkeypatch.setattr(grab, "Grabber", FakeGrabber)
    win = MainWindow(Settings())
    win._open_picker(SimpleNamespace(client=(100, 50, 3440, 1440), minimized=False))
    assert boxes == [(100, 50, 3440, 1440)]
    assert (win.picker.canvas.pic_w, win.picker.canvas.pic_h) == (3440, 1440)
    picker = win.picker
    from PySide6.QtCore import QRect
    picker.canvas.box = QRect(500, 1000, 600, 300)
    picker.save()
    assert geometry.from_relative(win.settings["region"], geometry.viewport(3440, 1440)) == (500, 1000, 600, 300)
    assert win.picker is None
    win.close()
