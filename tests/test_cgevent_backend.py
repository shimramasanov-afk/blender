from l2_brain.io.actions import CameraRotate, GroundClick, HoldKey, MouseButton
from l2_brain.io.cgevent_backend import CGEventInputBackend, LiveInputNotConfirmed, RecordingPoster
from l2_brain.io.keycodes import MAC_KEYCODES, virtual_keycode
from l2_brain.io.notepad_probe import game_process_present, notepad_present, run_notepad_scenario


class _Clock:
    def __init__(self) -> None:
        self.t = 1_000_000_000

    def __call__(self) -> int:
        return self.t

    def advance_ms(self, ms: int) -> None:
        self.t += ms * 1_000_000


def _backend(**kwargs: object) -> CGEventInputBackend:
    poster = kwargs.pop("poster", RecordingPoster())
    focus = kwargs.pop("focus_probe", lambda: True)
    clock = kwargs.pop("now_ns", None)
    return CGEventInputBackend(
        4242,
        live_confirmed=True,
        live_danger_confirmed=True,
        poster=poster,  # type: ignore[arg-type]
        focus_probe=focus,  # type: ignore[arg-type]
        now_ns=clock,  # type: ignore[arg-type]
    )


def test_construct_without_live_flag_blocked() -> None:
    try:
        CGEventInputBackend(1, live_confirmed=False)
    except LiveInputNotConfirmed:
        return
    raise AssertionError("must require live_confirmed")


def test_construct_requires_danger_flag() -> None:
    try:
        CGEventInputBackend(1, live_confirmed=True, live_danger_confirmed=False)
    except LiveInputNotConfirmed:
        return
    raise AssertionError("must require live_danger_confirmed")


def test_keycode_table() -> None:
    assert virtual_keycode("w") == 0x0D
    for digit in "123456789":
        assert virtual_keycode(digit) == MAC_KEYCODES[digit]
    for name in ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"):
        assert virtual_keycode(name) == MAC_KEYCODES[name]
    assert virtual_keycode("left_arrow") == 0x7B
    assert virtual_keycode("right_arrow") == 0x7C


def test_rmb_drag_posts_five_step_path() -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(poster=poster, now_ns=clock)
    backend.window_origin = (100.0, 40.0)
    backend.window_size = (200.0, 100.0)

    def fake_sleep(seconds: float) -> None:
        clock.advance_ms(int(seconds * 1000))

    event = backend.rmb_drag(150.0, steps=5, step_delay_s=0.01, sleeper=fake_sleep)
    assert event.accepted is True
    assert event.reason == "rmb_drag_steps"
    mice = [c for c in poster.calls if c[0] == "mouse"]
    assert mice[0][:4] == ("mouse", 5, 200.0, 80.0)
    assert mice[1][:4] == ("mouse", 3, 200.0, 80.0)
    dragged = [c for c in mice if c[1] == 7]
    assert len(dragged) == 5
    assert dragged[-1][2] == 350.0
    assert mice[-1][:4] == ("mouse", 4, 350.0, 80.0)
    assert not any(c[0] == "key" for c in poster.calls)


def test_rmb_drag_vertical_changes_y() -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(poster=poster, now_ns=clock)
    backend.window_origin = (100.0, 40.0)
    backend.window_size = (200.0, 100.0)

    def fake_sleep(seconds: float) -> None:
        clock.advance_ms(int(seconds * 1000))

    event = backend.rmb_drag(0.0, dy_pixels=-40.0, steps=4, step_delay_s=0.01, sleeper=fake_sleep)
    assert event.accepted is True
    dragged = [c for c in poster.calls if c[0] == "mouse" and c[1] == 7]
    assert dragged[-1][3] == 40.0


def test_rmb_drag_hold_defers_mouseup() -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(poster=poster, now_ns=clock)
    backend.window_origin = (0.0, 0.0)
    backend.window_size = (200.0, 100.0)

    def fake_sleep(seconds: float) -> None:
        clock.advance_ms(int(seconds * 1000))

    event = backend.rmb_drag(200.0, steps=5, step_delay_s=0.01, sleeper=fake_sleep, release=False)
    assert event.accepted is True
    assert event.reason == "rmb_drag_hold"
    assert backend._rmb_held is not None
    assert not any(c[0] == "mouse" and c[1] == 4 for c in poster.calls)
    backend.rmb_up()
    assert backend._rmb_held is None
    assert any(c[0] == "mouse" and c[1] == 4 for c in poster.calls)


def test_arrow_pulse_ten_discrete_taps() -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(poster=poster, now_ns=clock)

    def fake_sleep(seconds: float) -> None:
        clock.advance_ms(int(seconds * 1000))

    event = backend.arrow_pulse("right_arrow", taps=10, interval_s=0.04, sleeper=fake_sleep)
    assert event.accepted is True
    keys = [c for c in poster.calls if c[0] == "key"]
    downs = [c for c in keys if c == ("key", 0x7C, True, 4242)]
    ups = [c for c in keys if c == ("key", 0x7C, False, 4242)]
    assert len(downs) == 10
    assert len(ups) == 10
    assert not any(c[0] == "mouse" for c in poster.calls)


def test_rotate_camera_keyboard_holds_arrow_without_mouse() -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(poster=poster, now_ns=clock)

    def fake_sleep(seconds: float) -> None:
        clock.advance_ms(int(seconds * 1000))

    event = backend.rotate_camera_keyboard("right", duration_ms=450, sleeper=fake_sleep)
    assert event.accepted is True
    assert event.key == "right_arrow"
    assert backend.watchdog.active_holds == set()
    assert not any(row.reason == "watchdog_timeout" for row in backend.log)
    keys = [c for c in poster.calls if c[0] == "key"]
    assert ("key", 0x7C, True, 4242) in keys
    assert ("key", 0x7C, False, 4242) in keys
    assert not any(c[0] == "mouse" for c in poster.calls)


def test_idle_act_does_not_press_game_keys() -> None:
    poster = RecordingPoster()
    backend = _backend(poster=poster)
    result = backend.idle_act()
    assert result["focused"] is True
    assert result["killed"] is False
    assert result["hid_sent"] is False
    assert poster.calls == []


def test_watchdog_sends_keyup() -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(poster=poster, now_ns=clock)
    backend.send_action(HoldKey(key="w", duration_ms=0, state="down"))
    assert ("key", 0x0D, True, 4242) in poster.calls
    clock.advance_ms(300)
    assert backend.pump()
    assert backend.watchdog.active_holds == set()
    assert ("key", 0x0D, False, 4242) in poster.calls
    assert any(row.reason == "watchdog_timeout" for row in backend.log)


def test_focus_lost_releases_and_blocks() -> None:
    clock = _Clock()
    poster = RecordingPoster()
    focused = True
    backend = _backend(poster=poster, now_ns=clock, focus_probe=lambda: focused)
    backend.send_action(HoldKey(key="w", duration_ms=0, state="down"))
    focused = False
    event = backend.send_action(CameraRotate(4, 0))
    assert event.accepted is False
    assert event.reason == "focus_lost"
    assert event.hid_sent is False
    assert backend.watchdog.active_holds == set()
    assert ("key", 0x0D, False, 4242) in poster.calls


def test_click_uses_window_origin() -> None:
    poster = RecordingPoster()
    backend = _backend(poster=poster)
    backend.window_origin = (100.0, 40.0)
    backend.send_action(GroundClick(x=10, y=5, button=MouseButton.LEFT))
    downs = [c for c in poster.calls if c[0] == "mouse" and c[1] == 1]
    moves = [c for c in poster.calls if c[0] == "mouse" and c[1] == 5]
    assert downs
    assert moves
    assert downs[0][2] == 110.0
    assert downs[0][3] == 45.0
    assert moves[0][2] == 110.0
    assert moves[0][3] == 45.0
    assert downs[0][6] is True
    assert moves[0][6] is True


def test_click_clamped_to_window() -> None:
    poster = RecordingPoster()
    backend = _backend(poster=poster)
    backend.window_origin = (10.0, 20.0)
    backend.window_size = (100.0, 80.0)
    backend.send_action(GroundClick(x=500, y=500, button=MouseButton.LEFT))
    downs = [c for c in poster.calls if c[0] == "mouse" and c[1] == 1]
    assert downs[0][2] == 107.0
    assert downs[0][3] == 97.0


def test_type_text_shift_for_capitals() -> None:
    poster = RecordingPoster()
    backend = _backend(poster=poster)
    backend.type_text("Ng/", sleeper=lambda _s: None, delay_s=0.0)
    keys = [c[1] for c in poster.calls if c[0] == "key"]
    assert 0x38 in keys
    assert 0x2D in keys
    assert 0x05 in keys
    assert 0x2C in keys


def test_game_process_denylist() -> None:
    assert game_process_present("notepad.exe\r\nl2.exe\r\n")
    assert not game_process_present("notepad.exe\r\nexplorer.exe\r\n")


def test_notepad_requires_console_session() -> None:
    listing = "notepad.exe  3644 Services\r\nNotepad.exe  3672 Console\r\n"
    assert notepad_present(listing)
    assert not notepad_present("notepad.exe  3644 Services\r\n")


def test_scenario_watchdog_without_os_hid() -> None:
    clock = _Clock()
    poster = RecordingPoster()
    backend = _backend(poster=poster, now_ns=clock)

    def fake_sleep(seconds: float) -> None:
        clock.advance_ms(int(seconds * 1000))

    payload = run_notepad_scenario(backend, sleeper=fake_sleep, now_ns=clock)
    assert payload["aborted"] is None
    assert payload["watchdog_tripped"] is True
    assert payload["stuck_keys_count"] == 0
    assert payload["hid_sent"] is False
    assert any(row["reason"] == "watchdog_timeout" for row in payload["events"])
    assert any(c == ("key", 0x0D, False, 4242) for c in poster.calls)
