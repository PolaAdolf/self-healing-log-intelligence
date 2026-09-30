import tempfile
import unittest
from pathlib import Path

from raw_log_service import aggregate_raw


class RawLogTests(unittest.TestCase):
    def test_original_apache_format_to_complete_utc_window(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = root / "raw"
            raw.mkdir()
            (raw / "access.log").write_text(
                '127.0.0.1 - - [01/Jan/2026:03:00:00 +0300] "GET / HTTP/1.1" 200 12\n'
                '127.0.0.1 - - [01/Jan/2026:03:02:00 +0300] "GET / HTTP/1.1" 500 10\n'
                '127.0.0.1 - - [01/Jan/2026:03:05:01 +0300] "GET / HTTP/1.1" 200 12\n', encoding="utf-8")
            frame, summary = aggregate_raw("apache", raw, root / "out")
            self.assertEqual(summary["parsed_records"], 3)
            self.assertEqual(len(frame), 1)
            self.assertEqual(frame.iloc[0]["apache_5xx_count"], 1)
            self.assertEqual(frame.iloc[0]["window_start_utc"], "2026-01-01T00:00:00Z")

    def test_wrong_format_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = root / "raw"
            raw.mkdir()
            (raw / "bad.log").write_text("not an Apache record", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "No matching records"):
                aggregate_raw("apache", raw, root / "out")


if __name__ == "__main__":
    unittest.main()
