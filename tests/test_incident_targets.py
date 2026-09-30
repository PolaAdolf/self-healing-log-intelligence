import unittest

import pandas as pd

from build_incident_targets import build_targets


def feature_frame() -> pd.DataFrame:
    starts = pd.date_range("2026-09-01T09:55:00Z", periods=4, freq="5min")
    return pd.DataFrame(
        {
            "window_start_utc": starts,
            "window_end_utc": starts + pd.Timedelta(5 * 60, unit="s"),
            "apache_window_complete": [1, 1, 1, 1],
            "apache_request_count": [100, 100, 100, 100],
            "apache_2xx_count": [95, 95, 95, 95],
            "apache_bytes_sent": [1000, 1000, 1000, 1000],
            "apache_4xx_count": [4, 4, 4, 4],
            "apache_5xx_count": [1, 1, 1, 1],
            "apache_3xx_count": [0, 0, 0, 0],
        }
    )


class IncidentTargetTests(unittest.TestCase):
    def test_future_onset_boundaries_and_active_windows(self) -> None:
        incident = {
            "_start": pd.Timestamp("2026-09-01T10:10:00Z"),
            "_end": pd.Timestamp("2026-09-01T10:20:00Z"),
        }
        result = build_targets(feature_frame(), [incident], "apache")

        self.assertEqual(result["incident_onset_within_5m"].tolist()[:2], [0, 1])
        self.assertEqual(result["incident_onset_within_15m"].tolist()[:2], [1, 1])
        self.assertEqual(result["incident_active_at_window_end"].tolist(), [0, 0, 1, 1])
        self.assertTrue(pd.isna(result.loc[2, "incident_onset_within_5m"]))
        self.assertTrue(pd.isna(result.loc[3, "incident_onset_within_15m"]))

    def test_no_incidents_produces_zero_targets(self) -> None:
        result = build_targets(feature_frame(), [], "apache")

        self.assertEqual(result["incident_active_at_window_end"].sum(), 0)
        self.assertEqual(result["incident_onset_within_5m"].sum(), 0)
        self.assertEqual(result["incident_onset_within_15m"].sum(), 0)


if __name__ == "__main__":
    unittest.main()
