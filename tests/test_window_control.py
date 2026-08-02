"""
Tests for desktop window control (focus/minimize/maximize/restore by
window title fragment). Windows-only in real use (pywin32), but these
tests fake out win32gui/win32con so the logic itself -- title matching,
command parsing, graceful fallback when not on Windows or pywin32 is
missing -- is verified on any platform, including CI on Linux.
"""
import sys
import types

import pytest


class FakeWin32Con:
    SW_MINIMIZE = 6
    SW_MAXIMIZE = 3
    SW_RESTORE = 9


class FakeWin32Gui:
    """Stand-in for win32gui with a couple of fake open windows."""

    windows = {
        1001: "PCBWay - Google Chrome",
        1002: "Untitled - Notepad",
    }
    iconic = set()
    foreground_calls = []
    show_calls = []

    @classmethod
    def reset(cls):
        cls.iconic = set()
        cls.foreground_calls = []
        cls.show_calls = []

    @classmethod
    def EnumWindows(cls, callback, extra):
        for hwnd, title in cls.windows.items():
            callback(hwnd, extra)

    @classmethod
    def IsWindowVisible(cls, hwnd):
        return hwnd in cls.windows

    @classmethod
    def GetWindowText(cls, hwnd):
        return cls.windows.get(hwnd, "")

    @classmethod
    def IsIconic(cls, hwnd):
        return hwnd in cls.iconic

    @classmethod
    def SetForegroundWindow(cls, hwnd):
        cls.foreground_calls.append(hwnd)

    @classmethod
    def ShowWindow(cls, hwnd, flag):
        cls.show_calls.append((hwnd, flag))


@pytest.fixture(autouse=True)
def fake_pywin32(monkeypatch):
    """Installs fake win32gui/win32con modules for the duration of each
    test in this file, so `import win32gui` inside control_window /
    list_windows resolves to our fakes instead of failing on non-Windows
    test runners."""
    FakeWin32Gui.reset()
    monkeypatch.setitem(sys.modules, "win32gui", FakeWin32Gui)
    monkeypatch.setitem(sys.modules, "win32con", FakeWin32Con)
    yield


@pytest.fixture
def windows_engine(engine, monkeypatch):
    monkeypatch.setattr(engine, "is_windows", lambda: True)
    return engine


def test_list_windows_returns_empty_when_not_windows(engine, monkeypatch):
    monkeypatch.setattr(engine, "is_windows", lambda: False)
    assert engine.list_windows() == []


def test_list_windows_returns_visible_titles(windows_engine):
    titles = [title for _, title in windows_engine.list_windows()]
    assert "PCBWay - Google Chrome" in titles
    assert "Untitled - Notepad" in titles


def test_focus_window_matches_substring_and_sets_foreground(windows_engine):
    result = windows_engine.control_window("focus", "chrome")
    assert result.ok is True
    assert FakeWin32Gui.foreground_calls == [1001]


def test_focus_restores_before_focusing_if_minimized(windows_engine):
    FakeWin32Gui.iconic.add(1001)
    windows_engine.control_window("focus", "chrome")
    assert (1001, FakeWin32Con.SW_RESTORE) in FakeWin32Gui.show_calls
    assert FakeWin32Gui.foreground_calls == [1001]


def test_minimize_window_sends_minimize_flag(windows_engine):
    result = windows_engine.control_window("minimize", "notepad")
    assert result.ok is True
    assert (1002, FakeWin32Con.SW_MINIMIZE) in FakeWin32Gui.show_calls


def test_maximize_window_sends_maximize_flag(windows_engine):
    result = windows_engine.control_window("maximize", "chrome")
    assert result.ok is True
    assert (1001, FakeWin32Con.SW_MAXIMIZE) in FakeWin32Gui.show_calls


def test_no_matching_window_reports_failure_without_raising(windows_engine):
    result = windows_engine.control_window("focus", "some app that is not open")
    assert result.ok is False


def test_control_window_refuses_on_non_windows(engine, monkeypatch):
    monkeypatch.setattr(engine, "is_windows", lambda: False)
    result = engine.control_window("focus", "chrome")
    assert result.ok is False
    assert "windows" in result.message.lower()


def test_voice_command_focus_is_parsed_and_dispatched(windows_engine):
    result = windows_engine.run_command("focus chrome")
    assert result.ok is True
    assert FakeWin32Gui.foreground_calls == [1001]


def test_voice_command_minimize_is_parsed_and_dispatched(windows_engine):
    result = windows_engine.run_command("minimize notepad")
    assert result.ok is True
    assert (1002, FakeWin32Con.SW_MINIMIZE) in FakeWin32Gui.show_calls
