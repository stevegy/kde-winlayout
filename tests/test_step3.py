import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the parent directory to sys.path so we can import kdewin
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import kdewin as kdp


class TestStep3(unittest.TestCase):
    @patch('kdewin.kdotool')
    @patch('kdewin.wait_for_window')
    @patch('kdewin.launch_app')
    @patch('kdewin.collect_windows')
    @patch('kdewin._set_window_geometry')
    def test_restore_windows_with_launch(
        self, mock_geom, mock_collect, mock_launch, mock_wait, mock_kdotool
    ):
        # Scenario:
        # 1. Existing window (Alacritty)
        # 2. Missing window with cmdline (Firefox)
        # 3. Missing window without cmdline (Unknown)
        # 4. Skipped window (plasmashell)

        saved = [
            {"class": "Alacritty", "name": "Terminal", "x": 100, "y": 100,
             "width": 800, "height": 600, "desktop": 1, "sticky": False,
             "cmdline": ""},
            {"class": "firefox", "name": "Web", "x": 200, "y": 200,
             "width": 1024, "height": 768, "desktop": 1, "sticky": False,
             "cmdline": "firefox"},
            {"class": "Unknown", "name": "Ghost", "x": 0, "y": 0,
             "width": 10, "height": 10, "desktop": 1, "sticky": False,
             "cmdline": ""},
            {"class": "plasmashell", "name": "Panel", "x": 0, "y": 0,
             "width": 1920, "height": 40, "desktop": 1, "sticky": False,
             "cmdline": ""},
        ]

        # Initial state: only Alacritty is running
        mock_collect.return_value = [
            {"uuid": "uuid-alacritty", "class": "Alacritty", "name": "Terminal",
             "x": 100, "y": 100, "width": 800, "height": 600, "desktop": 1,
             "cmdline": ""}
        ]

        # Firefox appears after launch
        mock_wait.return_value = "uuid-firefox"

        # Run restoration with v2 profile
        kdp._restore_windows(saved, {"version": 2})

        # 1. Verify launch_app was called for Firefox
        mock_launch.assert_called_once_with("firefox")

        # 2. Verify wait_for_window was called for Firefox
        mock_wait.assert_called_once_with("firefox", "Web", timeout=10)

        # 3. Verify geometry was set for Alacritty and Firefox
        self.assertEqual(mock_geom.call_count, 2)
        geom_calls = mock_geom.call_args_list
        uuids = {call[0][0] for call in geom_calls}
        self.assertIn("uuid-alacritty", uuids)
        self.assertIn("uuid-firefox", uuids)

        # 4. Verify set_desktop_for_window was called for both windows
        # (desktop=1 in v2 → desk+1=2 for kdotool)
        desktop_calls = [
            call for call in mock_kdotool.call_args_list
            if call[0][0] == "set_desktop_for_window"
        ]
        self.assertEqual(len(desktop_calls), 2)

        # 5. Verify results
        # 2 restored (Alacritty, Firefox), 1 missing (Unknown), 1 skipped (plasmashell)
        self.assertEqual(mock_geom.call_count, 2)


if __name__ == '__main__':
    unittest.main()
