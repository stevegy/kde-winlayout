import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the parent directory to sys.path so we can import kde-win-profile
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import kdewin as kdp

class TestStep1(unittest.TestCase):
    @patch('subprocess.Popen')
    def test_launch_app_success(self, mock_popen):
        # Test successful launch
        cmdline = "/usr/bin/sleep 100"
        kdp.launch_app(cmdline)

        mock_popen.assert_called_once()
        # Check if args were split correctly
        args, kwargs = mock_popen.call_args
        self.assertEqual(args[0], ["/usr/bin/sleep", "100"])
        self.assertTrue(kwargs.get('start_new_session'))
        self.assertEqual(kwargs.get('stdout'), sys.modules['subprocess'].DEVNULL)

    @patch('subprocess.Popen')
    def test_launch_app_empty(self, mock_popen):
        # Test empty cmdline
        kdp.launch_app("")
        mock_popen.assert_not_called()

    @patch('subprocess.Popen')
    def test_launch_app_failure(self, mock_popen):
        # Test exception during launch
        mock_popen.side_effect = Exception("Launch failed")
        cmdline = "/usr/bin/invalid"

        # Now uses logging.error, not print to stderr
        with patch('kdewin.logging') as mock_logging:
            kdp.launch_app(cmdline)
            mock_logging.error.assert_called_once()

if __name__ == '__main__':
    unittest.main()
