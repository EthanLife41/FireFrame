"""Action dispatch and timer-notification input sanitizing."""
import subprocess

import backend.actions as actions
from backend.config_loader import SHORTCUT_ACTIONS


def test_unknown_action_is_refused():
    res = actions.handle_action("definitely-not-a-real-action", {})
    assert res["success"] is False
    assert "Unknown action" in res["message"]


def test_every_shipped_action_has_a_supported_handler(monkeypatch):
    # stub handlers so dispatch never touches the OS
    for name in ("run_shortcut", "run_open_command", "run_open_url",
                 "_open_app_or_url", "toggle_mute", "sleep_mac", "run_prepare"):
        monkeypatch.setattr(actions, name, lambda *a, **k: {"success": True, "message": "ok"})

    for key in SHORTCUT_ACTIONS:
        res = actions.handle_action(key, {})
        assert "unsupported type" not in res["message"], f"{key} has an unsupported type"


def test_dispatch_routes_to_the_right_handler(monkeypatch):
    calls = []

    def record(name):
        return lambda *a, **k: calls.append(name) or {"success": True, "message": name}

    monkeypatch.setattr(actions, "run_shortcut", record("shortcut"))
    monkeypatch.setattr(actions, "toggle_mute", record("mute"))
    monkeypatch.setattr(actions, "sleep_mac", record("sleep"))

    actions.handle_action("dnd", {})
    actions.handle_action("mute", {})
    actions.handle_action("sleep_mac", {})
    assert calls == ["shortcut", "mute", "sleep"]


# --- command-injection sanitizing ---

def _capture_subprocess(monkeypatch):
    """Record subprocess.run calls instead of running them."""
    captured = []

    class _Done:
        returncode = 0
        stdout = ""

    def fake_run(*args, **kwargs):
        captured.append((args, kwargs))
        return _Done()

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured


def test_timer_notification_never_uses_a_shell(monkeypatch):
    captured = _capture_subprocess(monkeypatch)
    actions.notify_timer_done(25, "Focus")
    (args, kwargs) = captured[0]
    assert kwargs.get("shell", False) is False
    assert isinstance(args[0], list)          # argv, not a shell string
    assert args[0][0] == "osascript"


def test_malicious_timer_label_is_stripped_to_safe_characters(monkeypatch):
    captured = _capture_subprocess(monkeypatch)
    actions.notify_timer_done(10, '"; rm -rf / #$(whoami)`id`')
    argv = captured[0][0][0]
    body = argv[3]                            # argv = [osascript, -e, script, body, title]
    # only letters/digits/spaces survive _LABEL_RE
    assert all(c.isalnum() or c == " " for c in body)
    assert "rm -rf" not in body
    assert '"' not in body and ";" not in body and "$" not in body and "`" not in body


def test_timer_minutes_are_clamped(monkeypatch):
    captured = _capture_subprocess(monkeypatch)
    actions.notify_timer_done(99999, "")
    body = captured[0][0][0][3]
    assert body == "1440-minute timer finished"   # clamped to 24h

    captured.clear()
    actions.notify_timer_done("not-a-number", "")
    body = captured[0][0][0][3]
    assert body == "1-minute timer finished"       # non-int -> clamped up to 1


def test_sound_name_is_sanitized(monkeypatch):
    # TIMER_SOUND is interpolated into the script, so it's filtered
    monkeypatch.setattr(actions, "TIMER_SOUND", 'Glass"; do shell script "evil')
    captured = _capture_subprocess(monkeypatch)
    actions.notify_timer_done(5, "x")
    script = captured[0][0][0][2]
    # _SOUND_RE strips non-alphanumerics, collapsing the payload to an inert token
    assert 'sound name "Glassdoshellscriptevil"' in script
    assert ';' not in script
    assert 'do shell script' not in script
