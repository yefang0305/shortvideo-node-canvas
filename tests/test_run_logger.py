import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runtime.run_logger import RunLogger


class RunLoggerTests(unittest.TestCase):
    def test_appends_messages_to_log_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = RunLogger(Path(tmp))
            logger.write("hello")
            logger.write("world")

            text = logger.path.read_text(encoding="utf-8")

        self.assertIn("hello", text)
        self.assertIn("world", text)
        self.assertTrue(logger.path.name.startswith("run_"))


if __name__ == "__main__":
    unittest.main()

