import unittest

import numpy as np
import pandas as pd

from train_v2_models import engineer_features, percentile_scores


class V2ModelingTests(unittest.TestCase):
    def test_engineered_features_do_not_use_future_rows(self):
        frame = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-01-01", periods=5, freq="5min"),
                "request_count": [1, 2, 3, 4, 5],
            }
        )
        original, features = engineer_features(frame, "timestamp", ["request_count"])
        changed = frame.copy()
        changed.loc[4, "request_count"] = 99999
        modified, _ = engineer_features(changed, "timestamp", ["request_count"])

        pd.testing.assert_series_equal(
            original.loc[0:3, features].stack(),
            modified.loc[0:3, features].stack(),
        )

    def test_percentile_scores_are_monotonic_and_bounded(self):
        reference = np.array([1.0, 2.0, 3.0, 4.0])
        scores = percentile_scores(np.array([-10.0, 1.0, 2.5, 9.0]), reference)

        self.assertTrue(np.all(np.diff(scores) >= 0))
        self.assertGreaterEqual(scores.min(), 0)
        self.assertLessEqual(scores.max(), 100)


if __name__ == "__main__":
    unittest.main()
