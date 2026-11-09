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


def test_with_display_scaling_the_marked_area_is_returned_in_screen_pixels(app):
    """Windows at 125 %: Qt pixels = screen pixels / 1.25. The marked box must come back as the same part of the
    game picture, not shrunk towards the top left (Saru's cut-off lines)."""
    got = []
    client = (0, 0, 3440, 1440)                         # Saru's screen, physical
    picker = RegionPicker(client, got.append, scale=1.25)
    assert (picker.width(), picker.height()) == (2752, 1152)
    picker.start()
    # in Qt pixels: 400..880 × 800..1040  →  physical 500..1100 × 1000..1300
    _drag(picker, (400, 800), (880, 1040))
    view = geometry.viewport(3440, 1440)
    assert geometry.from_relative(got[0], view) == (500, 1000, 600, 300)


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
