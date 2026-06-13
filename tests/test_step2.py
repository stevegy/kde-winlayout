import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import time

# Add the parent directory to sys.path so we can import kdewin
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import kdewin as kdp

class TestStep2(unittest.TestCase):
    @patch('kdewin.collect_windows')
    def test_wait_for_window_found(self, mock_collect):
        # Simulate window appearing on the second call
        mock_collect.side_effect = [
            [], # 1st call: no windows
            [{"uuid": "123", "class": "Alacritty", "name": "Terminal"}], # 2nd call: window found
        ]

        # We use a short timeout for the test
        uuid = kdp.wait_for_window("Alacritty", "Terminal", timeout=2)

        self.assertEqual(uuid, "123")
        self.assertEqual(mock_collect.call_count, 2)

    @patch('kdewin.collect_windows')
    def test_wait_for_window_timeout(self, mock_collect):
        # Simulate window never appearing
        mock_collect.return_value = []

        start_time = time.time()
        uuid = kdp.wait_for_window("Alacritty", timeout=1)
        end_time = time.time()

        self.assertIsNone(uuid)
        self.assertGreaterEqual(end_time - start_time, 1.0)

    @patch('kdewin.collect_windows')
    def test_wait_for_window_class_only(self, mock_collect):
        # Test matching by class only
        mock_collect.side_effect = [
            [],
            [{"uuid": "456", "class": "Alacritty", "name": "Something Else"}],
        ]

        uuid = kdp.wait_for_window("Alacritty", timeout=2)
        self.assertEqual(uuid, "456")

if __name__ == '__main__':
    unittest.main()
