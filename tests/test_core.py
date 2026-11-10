import json
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest

from fogtranslate import geometry, secret
from fogtranslate.change import ChangeGate
from fogtranslate.config import Settings
from fogtranslate.engine import Engine
from fogtranslate.lines import ChatLine, Transcript, same_message
from fogtranslate.claude import Translator
from fogtranslate.translate import SCHEMA, Result, TranslateError, parse


# ---------------------------------------------------------------- geometry
def test_viewport_of_the_users_ultrawide_has_bars_of_440():
    assert geometry.viewport(3440, 1440) == (440, 0, 2560, 1440)
    assert geometry.viewport(2560, 1440) == (0, 0, 2560, 1440)
    assert geometry.viewport(1920, 1200) == (0, 60, 1920, 1080)


def test_region_survives_another_window_size():
    rel = geometry.to_relative((860, 1000, 860, 360), geometry.window_space(3440, 1440))
    assert geometry.valid_region(rel)
    assert geometry.from_relative(rel, geometry.window_space(1720, 720)) == (430, 500, 430, 180)


def test_the_chat_right_of_the_16_9_picture_is_not_cut_off():
    """Saru's lobby on 3440 × 1440: the chat sits at x ≈ 2800..3280, right of the 16:9 picture (ends at 3000).
    Until 0.7 the box was clipped there – every marking ended at x = 3000."""
    space = geometry.window_space(3440, 1440)
    rel = geometry.to_relative((2800, 850, 480, 340), space)
    assert geometry.from_relative(rel, space) == (2800, 850, 480, 340)


def test_region_is_clipped_to_the_window_and_tiny_boxes_are_rejected():
    space = geometry.window_space(3440, 1440)
    rel = geometry.to_relative((-50, 1000, 800, 300), space)
    assert rel[0] == 0 and geometry.from_relative(rel, space)[2] == 750
    assert geometry.to_relative((500, 500, 10, 10), space) is None


def test_overlay_goes_above_the_region_or_below_it_when_there_is_no_room():
    screen = (0, 0, 3440, 1440)
    assert geometry.overlay_spot((500, 1000, 600, 300), (400, 100), screen) == (500, 894)
    assert geometry.overlay_spot((500, 20, 600, 300), (400, 100), screen) == (500, 326)
    assert geometry.overlay_spot((3300, 1000, 100, 100), (400, 100), screen)[0] == 3040


# ---------------------------------------------------------------- change gate
def _chat(seed, shape=(200, 600)):
    rng = np.random.default_rng(seed)
    img = np.zeros(shape + (3,), np.uint8)
    img[::20, :, :] = rng.integers(0, 255, (shape[0] // 20 + (shape[0] % 20 > 0), shape[1], 3), dtype=np.uint8)
    return img


def test_a_new_picture_is_sent_once_after_it_settled():
    g = ChangeGate(settle=2)
    a, b = _chat(1), _chat(2)
    assert g.look(a) is False          # first look: not settled yet
    assert g.look(a) is True           # settled → send
    assert g.look(a) is False          # same picture again: nothing new
    assert g.look(b) is False          # changed, not settled
    assert g.look(b) is True


def test_an_empty_region_is_never_sent():
    g = ChangeGate(settle=1)
    assert g.look(np.full((200, 600, 3), 30, np.uint8)) is False


# ---------------------------------------------------------------- lines
def _line(sender, text, translate=True, translation="x"):
    return ChatLine(sender, text, "ru", translation, translate)


def test_lines_already_shown_are_not_shown_again_even_if_read_slightly_differently():
    t = Transcript()
    added, _ = t.add([_line("Meg", "привет всем!"), _line("Dwight", "gg", translate=False)])
    assert len(added) == 2
    added, replaced = t.add([_line("meg", "Привет всем"), _line("Claudette", "камп")])
    assert [ln.sender for ln in added] == ["Claudette"] and not replaced


# Saru's test (09.11.2026): one Russian message, wrapped over four chat lines, was read as fragments first and
# as a whole later – it must end up as ONE message, not five.
FULL = ("Сегодня вечером в Санкт-Галлене холодно и тихо. Я сижу дома, пью чай и читаю книгу. Завтра мне рано "
        "вставать, потому что утром у меня много работы.")


def test_fragments_of_a_wrapped_message_are_merged_into_the_whole_reading():
    t = Transcript()
    t.add([_line("Dwight Fairfield", "Санкт-Галлене х…"), _line("", "сижу дома, пью"),
           _line("", "Завтра мне рано"), _line("", "что утром у меня")])
    assert len(t.entries) == 4
    added, replaced = t.add([_line("Dwight Fairfield", FULL, translation="Heute Abend …")])
    assert not added and len(replaced) == 4
    assert len(t.entries) == 1 and t.entries[0].text == FULL and t.entries[0].sender == "Dwight Fairfield"
    added, replaced = t.add([_line("Dwight Fairfield", FULL[:60] + "…")])       # a worse reading later
    assert not added and not replaced and t.entries[0].text == FULL


def test_different_messages_stay_apart():
    assert not same_message(_line("Meg", "go gens"), _line("Meg", "gg"))
    assert not same_message(_line("Meg", "hello there friend"), _line("Ace", "hello there friend"))
    assert same_message(_line("Meg", "ich bin am generator"), _line("Meg", "ich bin am generatur"))


# ---------------------------------------------------------------- answer parsing
def test_parse_drops_malformed_items_and_strips_control_characters():
    data = {"lines": [
        {"sender": "Meg", "text": "hola‮", "language": "ES", "translation": "hallo", "translate": True},
        {"sender": "x"},                      # no text
        "nonsense",
        {"text": "", "translate": True},
    ]}
    lines = parse(data)
    assert len(lines) == 1
    assert lines[0].text == "hola" and lines[0].language == "es"
    assert parse("garbage") == [] and parse({"lines": 5}) == []


def test_schema_is_strict():
    item = SCHEMA["properties"]["lines"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])


class FakeClient:
    def __init__(self, answer=None, error=None, stop="end_turn"):
        self.calls = []
        self.answer, self.error, self.stop = answer, error, stop
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        usage = SimpleNamespace(input_tokens=1000, output_tokens=100, cache_read_input_tokens=0,
                                cache_creation_input_tokens=0)
        return SimpleNamespace(stop_reason=self.stop, usage=usage,
                               content=[SimpleNamespace(type="text", text=json.dumps(self.answer))])


def test_the_request_sends_only_the_picture_and_the_target_language():
    fake = FakeClient({"lines": [{"sender": "Meg", "text": "oi", "language": "pt", "translation": "hallo",
                                  "translate": True}]})
    res = Translator("k", "claude-opus-5-5", "de", client=fake).request(_chat(3))
    assert [ln.translation for ln in res.lines] == ["hallo"]
    assert res.cost_usd == pytest.approx((1000 * 4 + 100 * 20) / 1e6)
    call = fake.calls[0]
    content = call["messages"][0]["content"]
    assert [c["type"] for c in content] == ["image", "text"]
    assert content[1]["text"] == "Target language: German."
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["fallbacks"] == "default"


def test_a_refusal_and_a_broken_answer_become_errors():
    with pytest.raises(TranslateError) as e:
        Translator("k", client=FakeClient({"lines": []}, stop="refusal")).request(_chat(4))
    assert e.value.kind == "refused"
    fake = FakeClient()
    fake.answer = None
    fake._create = lambda **kw: SimpleNamespace(stop_reason="end_turn", usage=None,
                                                content=[SimpleNamespace(type="text", text="{oops")])
    fake.beta.messages.create = fake._create
    with pytest.raises(TranslateError) as e:
        Translator("k", client=fake).request(_chat(4))
    assert e.value.kind == "answer"


# ---------------------------------------------------------------- engine
class FakeWorker:
    def __init__(self):
        self.busy = False
        self.sent = []

    def submit(self, img):
        self.sent.append(img)
        return True


def _engine(**values):
    s = Settings()
    s["region"] = [0.02, 0.6, 0.3, 0.3]
    for k, v in values.items():
        s[k] = v
    t = [0.0]
    eng = Engine(s, FakeWorker(), clock=lambda: t[0], now=lambda: datetime(2026, 11, 9, 20, 0))
    return eng, t


GAME = SimpleNamespace(client=(0, 0, 3440, 1440), minimized=False)


def test_with_dbd_behind_the_region_is_read_only_while_nothing_covers_it():
    eng, _ = _engine(read_background=False)
    looked = []
    eng.look(GAME, False, lambda box: looked.append(box))
    assert looked == [] and eng.status == "background"

    eng, _ = _engine()                                 # default: read in the background ...
    eng.look(GAME, False, lambda box: looked.append(box), region_free=lambda g, box: False)
    assert looked == [] and eng.status == "covered"    # ... but never a window lying over the chat
    eng.look(GAME, False, lambda box: looked.append(box) or _chat(1))
    assert looked == [] and eng.status == "covered"    # no check given = treated as covered
    eng.look(GAME, False, lambda box: looked.append(box) or _chat(1), region_free=lambda g, box: True)
    assert len(looked) == 1 and eng.status == "watching"


def test_our_own_overlay_is_blacked_out_of_the_picture():
    from fogtranslate.grab import blank
    img = np.full((100, 200, 3), 255, np.uint8)
    blank(img, (1000, 500, 200, 100), [(1150, 550, 300, 300), (0, 0, 10, 10)])
    assert img[60, 160].sum() == 0 and img[10, 10].sum() == 765 and img[60, 140].sum() == 765


def test_window_overlap():
    from fogtranslate.window import overlaps
    assert overlaps((0, 0, 100, 100), [(99, 99, 10, 10)])
    assert not overlaps((0, 0, 100, 100), [(100, 0, 10, 10), (0, 100, 5, 5)])


def test_requests_keep_the_minimum_gap_and_the_daily_cap():
    eng, t = _engine(min_gap_s=3.0, daily_cap=1)
    frames = iter([_chat(1), _chat(1), _chat(2), _chat(2), _chat(2)])
    grab = lambda box: next(frames)
    eng.look(GAME, True, grab)
    eng.look(GAME, True, grab)
    assert len(eng.worker.sent) == 1
    eng.answer(Result([], 0.01))
    t[0] = 1.0
    eng.look(GAME, True, grab)
    eng.look(GAME, True, grab)            # settled, but gap not over
    assert len(eng.worker.sent) == 1
    t[0] = 10.0
    eng.look(GAME, True, grab)            # gap over – but the daily cap (1) is used up
    assert len(eng.worker.sent) == 1 and eng.status == "cap"


def test_only_new_foreign_lines_are_shown_and_they_fade():
    eng, t = _engine(show_s=25.0)
    assert eng.answer(Result([_line("Meg", "привет"), _line("Me", "hallo", translate=False)], 0.0))
    assert [ln.sender for ln in eng.visible()] == ["Meg"]
    assert [ln.sender for ln in eng.messages()] == ["Meg"]
    assert eng.answer(Result([_line("Meg", "привет")], 0.0)) is False
    t[0] = 30.0
    assert eng.visible() == []
    assert len(eng.messages()) == 1                  # the list keeps it


def test_a_better_reading_takes_the_place_of_the_fragments_on_screen():
    eng, t = _engine(show_s=25.0)
    eng.answer(Result([_line("Dwight", "Санкт-Галлене х…"), _line("", "сижу дома, пью")], 0.0))
    t[0] = 5.0
    eng.answer(Result([_line("Dwight", FULL)], 0.0))
    assert [ln.text for ln in eng.visible()] == [FULL]


def test_the_region_follows_the_game_window():
    eng, _ = _engine()
    x, y, w, h = eng.region_on_screen(SimpleNamespace(client=(100, 50, 3440, 1440), minimized=False))
    assert x == 100 + round(0.02 * 3440) and y == 50 + round(0.6 * 1440)


# ---------------------------------------------------------------- settings + key
def test_the_key_is_never_stored_in_clear_text(tmp_path):
    s = Settings(str(tmp_path))
    assert s.set_api_key("claude", "sk-ant-secret") is (secret.CIPHER is not None)
    s.save()
    assert "sk-ant-secret" not in (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert s.api_key("claude") == "sk-ant-secret"


def test_dpapi_round_trip_with_a_stand_in_cipher():
    flip = lambda data, enc: bytes(b ^ 0x5A for b in data)
    stored = secret.protect("abc", cipher=flip)
    assert stored.startswith("dpapi:") and secret.unprotect(stored, cipher=flip) == "abc"
    assert secret.unprotect("plain:YWJj", cipher=flip) == ""


def test_broken_settings_fall_back_to_defaults(tmp_path):
    (tmp_path / "settings.json").write_text('{"region": [5, 5, 0, 0], "region_space": "window", "target": "xx", "model": "gpt", '
                                            '"service": "x", "ollama_port": 0, "accepted": ["x", "gemini"]}',
                                            encoding="utf-8")
    s = Settings(str(tmp_path))
    assert s["region"] is None and s["target"] == "de" and s["claude_model"] == "claude-opus-5-5"
    assert s["service"] == "claude" and s["ollama_port"] == 11434 and s["accepted"] == ["gemini"]


def test_after_a_limit_answer_and_for_gemini_the_requests_wait_longer():
    eng, t = _engine(min_gap_s=3.0, service="gemini")
    frames = iter([_chat(1), _chat(1), _chat(2), _chat(2), _chat(2)])
    grab = lambda box: next(frames)
    eng.look(GAME, True, grab)
    eng.look(GAME, True, grab)
    assert len(eng.worker.sent) == 1
    eng.answer(TranslateError("quota"))
    t[0] = 30.0
    eng.look(GAME, True, grab)
    eng.look(GAME, True, grab)
    assert len(eng.worker.sent) == 1          # still waiting after the limit
    t[0] = 61.0
    eng.look(GAME, True, grab)
    assert len(eng.worker.sent) == 2


# ---------------------------------------------------------------- look thread
def test_the_look_thread_builds_the_translator_and_looks_without_the_window():
    import queue
    import time as _time
    from fogtranslate.looper import Looper

    eng, _ = _engine()
    q = queue.Queue()

    class Grabber:
        def grab(self, box):
            return _chat(1)

        def close(self):
            pass

    def slow_make():
        _time.sleep(0.2)                          # like importing the SDK
        return object()

    loop = Looper(eng, slow_make, q.put, 0.2, grabber_factory=Grabber, find_game=lambda: GAME,
                  in_front=lambda g: True)
    started = _time.monotonic()
    loop.start()
    assert _time.monotonic() - started < 0.1     # start() does not wait for the translator
    kinds = []
    while "tick" not in kinds and _time.monotonic() - started < 5:
        kinds.append(q.get(timeout=5)[0])
    loop.stop()
    loop.join(2)
    assert kinds[0] == "started" and not loop.is_alive()


def test_a_failing_start_is_reported_not_raised():
    import queue
    from fogtranslate.looper import Looper

    eng, _ = _engine()
    q = queue.Queue()

    def no_key():
        raise TranslateError("key")

    loop = Looper(eng, no_key, q.put, 0.2)
    loop.start()
    loop.join(2)
    kind, err = q.get(timeout=1)
    assert kind == "start_failed" and err.kind == "key"


def test_a_screen_grabber_that_cannot_start_is_reported():
    import queue
    from fogtranslate.looper import Looper

    eng, _ = _engine()
    q = queue.Queue()

    def broken():
        raise OSError("no display")

    loop = Looper(eng, lambda: object(), q.put, 0.2, grabber_factory=broken)
    loop.start()
    loop.join(2)
    kinds = [q.get(timeout=1)[0], q.get(timeout=1)[0]]
    assert kinds == ["started", "start_failed"] and not loop.is_alive()


def test_the_instruction_tells_white_and_foreign_names_apart_from_wrapped_lines():
    from fogtranslate.translate import SYSTEM
    for words in ("any colour", "any script", "Chinese", "begins with 'Name:' starts a new message",
                  "WITHOUT 'Name:'", "Joined Match"):
        assert words in SYSTEM, words


def test_a_region_marked_before_0_7_1_is_dropped_so_it_gets_marked_again(tmp_path):
    (tmp_path / "settings.json").write_text('{"region": [0.9, 0.6, 0.1, 0.2]}', encoding="utf-8")
    s = Settings(str(tmp_path))
    assert s["region"] is None
    s["region"] = [0.8, 0.6, 0.15, 0.25]
    s.save()
    assert Settings(str(tmp_path))["region"] == [0.8, 0.6, 0.15, 0.25]


# ---------------------------------------------------------------- the lobby moves behind the chat
def _lobby(lines, t):
    """Like the DBD lobby: flickering fire light, a softly lit figure moving, and the chat's translucent dark panel
    (the flicker shows through it) with light text."""
    from PIL import Image, ImageDraw
    w, h = 480, 260
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    light = 130 + 60 * np.sin(xx / 40.0 + t) * np.cos(yy / 30.0 - t)                 # fire light
    figure = 70 * np.exp(-((xx - (60 + 6 * t)) ** 2 / 300 + (yy - 120) ** 2 / 2000))   # soft, moving
    bg = np.clip(light + figure, 0, 255)
    pic = np.stack([bg * 0.5, bg * 0.6, bg], axis=-1)
    pic[20:240, 110:470] *= 0.12                                                       # translucent panel
    img = Image.fromarray(pic.astype(np.uint8))
    d = ImageDraw.Draw(img)
    for i, text in enumerate(lines):
        d.text((118, 30 + 18 * i), text, fill=(235, 235, 235))
    return np.asarray(img)[..., ::-1].copy()


def test_a_moving_lobby_behind_the_chat_does_not_block_or_repeat_requests():
    """Saru, 09.11.2026: messages in the chat, nothing recognised – the box reached past the chat panel and the
    moving lobby never let the picture settle."""
    g = ChangeGate()
    chat = ["Meg: hello", "Dwight: privet vsem kak dela", "Ace: gg"]
    sent = [g.look(_lobby(chat, t)) for t in range(10)]
    assert sent.count(True) == 1                     # sent once, although the background never stood still
    chat2 = chat + ["Nea: kto kempit"]
    sent = [g.look(_lobby(chat2, t)) for t in range(10, 16)]
    assert sent.count(True) == 1                     # the new line is sent once


def test_changing_text_is_sent_even_if_the_box_never_settles():
    g = ChangeGate(settle=2, max_wait=4)
    results = [g.look(_lobby(["line %d %s" % (i, "x" * i)], i)) for i in range(1, 9)]
    assert any(results)                              # waits at most max_wait looks
    assert results.count(True) <= 3                  # but does not fire on every look


def test_an_area_without_text_is_never_sent():
    g = ChangeGate(settle=1)
    assert not any(g.look(_lobby([], t)) for t in range(6))


def test_earlier_translations_stay_on_screen_while_the_chat_is_active():
    """Saru, 09.11.2026: Snoggles' Chinese lines were gone from the overlay when faery wrote 20 s later."""
    eng, t = _engine(show_s=25.0, show_all=False)
    eng.answer(Result([ChatLine("Snoggles", "被迫让一个天平", "zh", "Forced into a balance", True)], 0.0))
    t[0] = 20.0
    eng.answer(Result([ChatLine("Snoggles", "被迫让一个天平", "zh", "Forced into a balance", True),
                       ChatLine("Meg", "привет", "ru", "hallo", True)], 0.0))
    t[0] = 40.0                                      # 40 s after the Chinese line, 20 s after the last new one
    assert [ln.sender for ln in eng.visible()] == ["Snoggles", "Meg"]
    t[0] = 46.0                                      # nothing new for more than 25 s
    assert eng.visible() == []
    assert eng.last_counts == {"read": 2, "foreign": 2, "new": 1, "replaced": 0}


def test_a_doubled_misreading_does_not_replace_the_message():
    t = Transcript()
    t.add([_line("Dwight", "what language do people write in dbd chat")])
    added, replaced = t.add([_line("Dwight", "what language do people write in dbd chat around people write in "
                                             "dbd chat what language do people write in dbd chat")])
    assert not added and not replaced
    assert t.entries[0].text == "what language do people write in dbd chat"


def test_an_odd_daily_limit_in_the_file_falls_back(tmp_path):
    (tmp_path / "settings.json").write_text('{"daily_cap": 0}', encoding="utf-8")
    assert Settings(str(tmp_path))["daily_cap"] == 300


# ---------------------------------------------------------------- only the new lines are sent
def _chat_lines(lines, size=(480, 260), line_h=22):
    """The DBD chat panel: newest line at the bottom, older ones pushed up."""
    from PIL import Image, ImageDraw, ImageFont
    w, h = size
    pic = Image.new("RGB", size, (14, 14, 16))
    d = ImageDraw.Draw(pic)
    try:
        font = ImageFont.load_default(size=16)
    except TypeError:                                # old Pillow
        font = ImageFont.load_default()
    y = h - 8 - line_h
    for text in reversed(lines):
        d.text((10, y), text, fill=(235, 235, 235), font=font)
        y -= line_h
    return np.asarray(pic)[..., ::-1].copy()


CHAT = ["Meg: hello all", "Dwight: who has a medkit", "Ace: gg ez", "Claudette: on the gen left",
        "Nea: privet vsem", "Jake: brb", "Feng: lol nice save", "Kate: whats your build",
        "Bill: camping hook again", "Quentin: im so tired", "Yui: last game for me"]


def test_when_the_chat_scrolls_only_the_new_line_is_sent():
    from fogtranslate.change import new_rows, text_mask
    old = list(CHAT)
    new = old[1:] + ["Nea: kto kempit na hukah"]
    a, b = text_mask(_chat_lines(old)), text_mask(_chat_lines(new))
    top = new_rows(a, b)
    assert 260 - 22 - 8 - 25 <= top <= 260 - 22 - 8        # just above the newest line
    crop = _chat_lines(new)[top:]
    assert text_mask(crop).sum() < text_mask(_chat_lines(new)).sum() / 5


def test_when_the_chat_is_not_full_yet_only_the_new_line_is_sent():
    from fogtranslate.change import new_rows, text_mask
    old = ["Meg: hello", "Ace: gg"]
    a = text_mask(_chat_lines(old))
    b = text_mask(_chat_lines(old + ["Nea: privet"]))
    top = new_rows(a, b)
    assert 150 <= top <= 260 - 22 - 8


def test_the_whole_area_is_sent_first_and_when_nothing_lines_up():
    from fogtranslate.change import new_rows, text_mask
    b = text_mask(_chat_lines(["Meg: hello"]))
    assert new_rows(None, b) == 0
    other = text_mask(_chat_lines(["Completely %d different" % i for i in range(11)]))
    assert new_rows(other, b) == 0


def test_the_engine_sends_the_crop_of_new_lines():
    eng, t = _engine(min_gap_s=0.0)
    old = list(CHAT)
    new = old[1:] + ["Nea: kto kempit na hukah"]
    for frame in (old, old):
        eng.look(GAME, True, lambda box, f=frame: _chat_lines(f))
    assert eng.worker.sent[-1].shape[0] == 260           # first time: everything
    eng.worker.busy = False
    for frame in (new, new):
        eng.look(GAME, True, lambda box, f=frame: _chat_lines(f))
    assert len(eng.worker.sent) == 2 and eng.worker.sent[-1].shape[0] < 80


def test_saved_old_speed_settings_move_to_the_faster_defaults(tmp_path):
    (tmp_path / "settings.json").write_text('{"look_s": 1.0, "min_gap_s": 3.0}', encoding="utf-8")
    s = Settings(str(tmp_path))
    assert s["look_s"] == 0.5 and s["min_gap_s"] == 2.0
    (tmp_path / "settings.json").write_text('{"look_s": 2.0, "min_gap_s": 5.0}', encoding="utf-8")
    s = Settings(str(tmp_path))
    assert s["look_s"] == 2.0 and s["min_gap_s"] == 5.0     # own values stay


def test_a_line_that_could_not_be_sent_yet_is_not_lost_when_the_next_one_comes():
    """Two messages inside the minimum gap: the second crop must not replace the unsent first one."""
    eng, t = _engine(min_gap_s=5.0)
    base = list(CHAT)
    one = base[1:] + ["Nea: kto kempit na hukah"]
    two = one[1:] + ["Ace: ya idu na generator"]
    for frame in (base, base):
        eng.look(GAME, True, lambda box, f=frame: _chat_lines(f))
    assert len(eng.worker.sent) == 1                       # whole chat sent, gap starts
    eng.worker.busy = False
    for frame in (one, one, two, two):                     # both arrive inside the gap
        eng.look(GAME, True, lambda box, f=frame: _chat_lines(f))
    assert len(eng.worker.sent) == 1
    t[0] = 6.0
    eng.look(GAME, True, lambda box: _chat_lines(two))
    assert len(eng.worker.sent) == 2
    assert eng.worker.sent[-1].shape[0] == 260             # the whole area: both new lines are in it


def test_after_a_failed_request_the_chat_is_sent_again():
    eng, t = _engine(min_gap_s=0.0)
    base = list(CHAT)
    one = base[1:] + ["Nea: kto kempit na hukah"]
    for frame in (base, base):
        eng.look(GAME, True, lambda box, f=frame: _chat_lines(f))
    eng.answer(Result([], 0.0))
    for frame in (one, one):
        eng.look(GAME, True, lambda box, f=frame: _chat_lines(f))
    assert len(eng.worker.sent) == 2 and eng.worker.sent[-1].shape[0] < 80
    eng.answer(TranslateError("net"))                      # that crop never arrived
    t[0] = 5.0
    eng.look(GAME, True, lambda box: _chat_lines(one))
    eng.look(GAME, True, lambda box: _chat_lines(one))
    assert len(eng.worker.sent) == 2                       # short wait after an error, no hammering
    t[0] = 20.0
    eng.look(GAME, True, lambda box: _chat_lines(one))
    eng.look(GAME, True, lambda box: _chat_lines(one))
    assert len(eng.worker.sent) == 3 and eng.worker.sent[-1].shape[0] == 260   # everything again
