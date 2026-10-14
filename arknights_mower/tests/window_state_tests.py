"""Regression tests for the existing native window state and normal bounds."""

import os
import unittest
from unittest import mock

from arknights_mower.utils import window_shell


class TestWindowSizing(unittest.TestCase):
    def test_restore_default_smaller_than_small_work_area(self):
        with mock.patch.object(
            window_shell,
            "_screen_work_area",
            return_value=window_shell.WindowSize(1280, 680),
        ):
            size = window_shell.default_desktop_window_size()
        self.assertEqual(size, window_shell.WindowSize(1024, 612))

    def test_non_windows_state_uses_existing_native_events(self):
        win = mock.Mock()
        bridge = window_shell.WindowShellBridge(win, system="linux")
        bridge._on_maximized()
        self.assertTrue(bridge.get_window_state()["maximized"])


class TestCloseBridgePreferences(unittest.TestCase):
    def test_disabled_tray_is_not_selectable(self):
        import tempfile
        from pathlib import Path

        from arknights_mower.utils.config import gui

        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(gui, "gui_path", Path(d) / "gui.yml"):
                bridge = window_shell.WindowShellBridge(
                    mock.Mock(), system="Windows", tray_enabled=False
                )
                self.assertFalse(bridge.get_close_preference()["tray_enabled"])
                with self.assertRaises(ValueError):
                    bridge.set_close_preference("tray", True)
                self.assertTrue(bridge.set_close_preference("exit", True))
                self.assertEqual(bridge.get_close_preference()["choice"], "exit")


@unittest.skipUnless(os.name == "nt", "Win32 native window probe")
class TestWindowsLiveState(unittest.TestCase):
    def test_native_state_supersedes_early_stale_event(self):
        from arknights_mower.utils import windows_frameless

        user32 = mock.Mock()
        user32.IsWindow.return_value = 1
        user32.IsIconic.return_value = 0
        user32.IsZoomed.return_value = 1
        win = mock.Mock()
        bridge = window_shell.WindowShellBridge(win, system="Windows")
        # A restored callback arriving before the JS listener must not force
        # the title bar to send another maximize command.
        bridge._on_restored()
        with (
            mock.patch.object(windows_frameless, "_winforms_hwnd", return_value=42),
            mock.patch("ctypes.WinDLL", return_value=user32),
        ):
            self.assertTrue(bridge.get_window_state()["maximized"])
            user32.IsZoomed.return_value = 0
            self.assertFalse(bridge.get_window_state()["maximized"])

    def test_unavailable_native_handle_falls_back_to_last_event(self):
        from arknights_mower.utils import windows_frameless

        bridge = window_shell.WindowShellBridge(mock.Mock(), system="Windows")
        bridge._on_maximized()
        with mock.patch.object(
            windows_frameless, "_winforms_hwnd", side_effect=RuntimeError("gone")
        ):
            self.assertTrue(bridge.get_window_state()["maximized"])


class TestPageLoadReadiness(unittest.TestCase):
    """Native window events can arrive before the page they are meant for."""

    def test_state_is_cached_while_the_page_is_still_loading(self):
        win = mock.Mock()
        win.events.loaded.is_set.return_value = False
        bridge = window_shell.WindowShellBridge(win, system="linux")
        bridge._on_maximized()
        bridge._on_resized(1200, 700)
        win.evaluate_js.assert_not_called()
        state = bridge.get_window_state()
        self.assertTrue(state["maximized"])
        self.assertEqual((state["width"], state["height"]), (1200, 700))

    def test_loaded_page_receives_the_withheld_state(self):
        win = mock.Mock()
        win.events.loaded.is_set.return_value = False
        bridge = window_shell.WindowShellBridge(win, system="linux")
        bridge._on_resized(1200, 700)
        # pywebview runs the loaded callbacks before it marks that event as set,
        # so this callback must not re-ask the event it represents.
        bridge._on_page_loaded()
        win.evaluate_js.assert_called_once()
        script = win.evaluate_js.call_args.args[0]
        self.assertIn(window_shell.WINDOW_SHELL_EVENT, script)
        self.assertIn('"width": 1200', script)
        bridge._on_restored()
        self.assertEqual(win.evaluate_js.call_count, 2)

    def test_attach_asks_for_a_delivery_once_the_page_loads(self):
        # pywebview Event objects add handlers through __iadd__, which only
        # MagicMock reproduces.
        win = mock.MagicMock()
        loaded = win.events.loaded
        bridge = window_shell.attach_window_shell(win, system="linux")
        loaded.__iadd__.assert_called_once_with(bridge._on_page_loaded)

    def test_window_without_the_event_keeps_the_best_effort_delivery(self):
        class Window:
            script = None

            def evaluate_js(self, script):
                self.script = script

        win = Window()
        bridge = window_shell.WindowShellBridge(win, system="linux")
        bridge._on_restored()
        self.assertIn(window_shell.WINDOW_SHELL_EVENT, win.script)
