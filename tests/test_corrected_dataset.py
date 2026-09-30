import csv
import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from build_corrected_dataset import (
    DIAGNOSTIC_FIELDS,
    FAILURE_FIELDS,
    LINEAGE_FIELDS,
    BuildState,
    ASSUMED_UTC_STATUS,
    export_known_features,
    parse_apache_access,
    parse_event_csv,
    parse_iis,
)


def make_state():
    lineage_io = io.StringIO()
    diagnostic_io = io.StringIO()
    failure_io = io.StringIO()
    return (
        BuildState(
            "5min",
            csv.DictWriter(lineage_io, fieldnames=LINEAGE_FIELDS),
            csv.DictWriter(diagnostic_io, fieldnames=DIAGNOSTIC_FIELDS),
            csv.DictWriter(failure_io, fieldnames=FAILURE_FIELDS),
        ),
        lineage_io,
        diagnostic_io,
        failure_io,
    )


class CorrectedDatasetTests(unittest.TestCase):
    def test_apache_embedded_offset_is_converted_to_utc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_dir = root / "Apache httpd"
            log_dir.mkdir()
            path = log_dir / "access.log"
            path.write_text(
                '10.0.0.1 - - [19/Aug/2026:00:00:00 +0300] '
                '"GET / HTTP/1.1" 200 12 [ROUTE=-] 0.25\n',
                encoding="utf-8",
            )
            state, lineage, _, _ = make_state()
            parse_apache_access([path], state, root, "Apache")

            key = next(iter(state.known_rows))
            self.assertEqual(str(key), "2026-08-18 21:00:00+00:00")
            self.assertNotIn("apache_response_ms_sum", state.known_rows[key])
            self.assertIn("unknown_excluded_from_features", lineage.getvalue())

    def test_iis_time_is_utc_and_latency_is_milliseconds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_dir = root / "IIS Logs"
            log_dir.mkdir()
            path = log_dir / "u_ex.log"
            path.write_text(
                "#Fields: date time sc-status time-taken\n"
                "2026-08-31 00:00:05 500 16\n",
                encoding="utf-8",
            )
            state, lineage, _, _ = make_state()
            parse_iis([path], state, root)

            key = next(iter(state.known_rows))
            self.assertEqual(str(key), "2026-08-31 00:00:00+00:00")
            self.assertEqual(state.known_rows[key]["iis_response_ms_sum"], 16)
            self.assertIn("verified_milliseconds", lineage.getvalue())

    def test_event_sixth_column_is_preserved_as_message(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_dir = root / "Event Viewer" / "output_sanitized"
            log_dir.mkdir(parents=True)
            path = log_dir / "System.csv"
            path.write_text(
                "Level,Date and Time,Source,Event ID,Task Category\n"
                'Error,9/8/2026 2:53:02 PM,Service Control Manager,7036,None,'
                '"Service stopped, unexpectedly"\n',
                encoding="utf-8",
            )
            state, lineage, diagnostics, _ = make_state()
            parse_event_csv([path], state, root)

            self.assertIn("Service stopped, unexpectedly", diagnostics.getvalue())
            key = next(iter(state.assumed_utc_rows))
            self.assertEqual(key[0], "windows_eventviewer")
            self.assertEqual(str(key[1]), "2026-09-08 14:50:00+00:00")
            self.assertIn("2026-09-08T14:53:02.000000Z", lineage.getvalue())
            self.assertIn(ASSUMED_UTC_STATUS, lineage.getvalue())
            self.assertEqual(state.profiles[0].parsed_records, 1)

    def test_blank_event_rows_are_not_parse_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_dir = root / "Event Viewer" / "output_sanitized"
            log_dir.mkdir(parents=True)
            path = log_dir / "System.csv"
            path.write_text(
                "Level,Date and Time,Source,Event ID,Task Category\n\n",
                encoding="utf-8",
            )
            state, _, _, failures = make_state()
            parse_event_csv([path], state, root)

            self.assertEqual(state.profiles[0].failed_records, 0)
            self.assertEqual(failures.getvalue(), "")

    def test_missing_source_is_not_exported_as_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            state, _, _, _ = make_state()
            timestamp = pd.Timestamp("2026-08-18 21:00:00", tz="UTC")
            state.add_known(timestamp, "apache_request_count", 4)
            state.coverage["apache"].append((timestamp, timestamp))
            result = export_known_features(state, Path(directory))

            self.assertEqual(result.loc[0, "apache_request_count"], 4)
            self.assertTrue(pd.isna(result.loc[0, "iis_request_count"]))
            self.assertEqual(result.loc[0, "iis_coverage_inferred"], 0)
            self.assertEqual(result.loc[0, "apache_window_complete"], 0)


if __name__ == "__main__":
    unittest.main()
