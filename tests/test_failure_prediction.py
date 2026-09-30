import unittest

import pandas as pd

from failure_prediction import future_targets, prepare


class FailurePredictionTests(unittest.TestCase):
    def frame(self, count=20):
        return pd.DataFrame({"time": pd.date_range("2026-01-01", periods=count, freq="5min", tz="UTC"), "error_count": [0] * count})

    def test_target_uses_future_not_current_failure(self):
        frame = self.frame()
        frame.loc[12, "error_count"] = 5
        target = future_targets(frame, "time", "error_count", 1)
        self.assertEqual(target.iloc[11], 1)
        self.assertEqual(target.iloc[12], 0)
        self.assertTrue(pd.isna(target.iloc[-1]))

    def test_gap_and_unknown_future_are_not_negative_labels(self):
        frame = self.frame().drop(index=13).reset_index(drop=True)
        target = future_targets(frame, "time", "error_count", 3)
        self.assertTrue(target.iloc[10:13].isna().all())
        self.assertTrue(target.tail(3).isna().all())

    def test_history_restarts_at_gap_and_future_cannot_change_past_features(self):
        frame = self.frame(40).drop(index=15).reset_index(drop=True)
        original, names = prepare(frame, "time", ["error_count"])
        self.assertTrue(original.iloc[14]["history_ready"])
        self.assertFalse(original.iloc[15]["history_ready"])
        self.assertFalse(original.iloc[25]["history_ready"])
        self.assertTrue(original.iloc[26]["history_ready"])
        frame.loc[35, "error_count"] = 999
        modified, _ = prepare(frame, "time", ["error_count"])
        pd.testing.assert_frame_equal(original.loc[:34, names], modified.loc[:34, names])


if __name__ == "__main__":
    unittest.main()
