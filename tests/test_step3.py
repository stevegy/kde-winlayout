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
    def test_restore_windows_with_launch(self, mock_collect, mock_launch, mock_wait, mock_kdotool):
        # Scenario:
        # 1. Existing window (Alacritty)
        # 2. Missing window with cmdline (Firefox)
        # 3. Missing window without cmdline (Unknown)
        # 4. Skipped window (plasmashell)

        saved = [
            {"class": "Alacritty", "name": "Terminal", "x": 100, "y": 100, "width": 800, "height": 600, "desktop": 1, "cmdline": ""},
            {"class": "firefox", "name": "Web", "x": 200, "y": 200, "width": 1024, "height": 768, "desktop": 1, "cmdline": "firefox"},
            {"class": "Unknown", "name": "Ghost", "x": 0, "y": 0, "width": 10, "height": 10, "desktop": 1, "cmdline": ""},
            {"class": "plasmashell", "name": "Panel", "x": 0, "y": 0, "width": 1920, "height": 40, "desktop": 1, "cmdline": ""},
        ]

        # Initial state: only Alacritty is running
        mock_collect.return_value = [
            {"uuid": "uuid-alacritty", "class": "Alacritty", "name": "Terminal", "x": 100, "y": 100, "width": 800, "height": 600, "desktop": 1, "cmdline": ""}
        ]

        # Firefox appears after launch
        mock_wait.return_value = "uuid-firefox"

        # Run restoration
        kdp._restore_windows(saved)

        # Verifications
        # 1. Verify launch_app was called for Firefox
        mock_launch.assert_called_once_with("firefox")

        # 2. Verify kdotool was called for Alacritty and Firefox
        # Alacritty: windowsize, windowmove, set_desktop
        # Firefox: windowsize, windowmove, set_desktop
        self.assertGreaterEqual(mock_kdotool.call_count, 6)

        # 3. Verify results (we'll check if it doesn't crash and prints something)
        # In a real test we'd capture stdout, but let's just ensure it finishes.

if __name__ == '__main__':
    unittest.main()
