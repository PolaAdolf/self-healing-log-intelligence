import unittest

import numpy as np

from model_runtime import ModelInputError, SelfHealingModelRuntime


class ConstantDetector:
    def decision_function(self, frame):
        return np.full(len(frame), 0.25)


def fake_bundle():
    base = ["request_count"]
    features = [
        "request_count",
        "hour_sin",
        "hour_cos",
        "request_count_lag_1",
        "request_count_diff_1",
        "request_count_rolling_3_mean",
        "request_count_rolling_12_mean",
        "request_count_rolling_12_max",
    ]
    return {
        "test": {
            "time_basis": "UTC",
            "timestamp_column": "window_start_utc",
            "base_features": base,
            "features": features,
            "detector": ConstantDetector(),
            "detector_reference_scores": np.array([-1.0, -0.5, 0.0]),
            "detector_raw_threshold": 0.5,
            "forecast_models": {},
        }
    }


def payload(minute: int, complete: bool = True):
    hour = minute // 60
    minute_in_hour = minute % 60
    start = f"2026-01-01T{hour:02d}:{minute_in_hour:02d}:00Z"
    end_minute = minute + 5
    end = f"2026-01-01T{end_minute // 60:02d}:{end_minute % 60:02d}:00Z"
    return {
        "source_model": "test",
        "window_start": start,
        "window_end": end,
        "window_complete": complete,
        "features": {"request_count": minute + 1},
    }


class ModelRuntimeTests(unittest.TestCase):
    def test_waits_for_twelve_consecutive_windows(self):
        runtime = SelfHealingModelRuntime(bundle=fake_bundle())
        for index in range(11):
            result = runtime.predict(payload(index * 5))
            self.assertEqual(result["current_status"], "awaiting_history")
        result = runtime.predict(payload(55))
        self.assertEqual(result["current_status"], "within_learned_range")
        self.assertIsNotNone(result["current_anomaly_score"])

    def test_gap_resets_history(self):
        runtime = SelfHealingModelRuntime(bundle=fake_bundle())
        runtime.predict(payload(0))
        result = runtime.predict(payload(10))
        self.assertEqual(result["current_status"], "awaiting_history_after_gap")
        self.assertEqual(result["history_windows"], 1)

    def test_rejects_incomplete_window(self):
        runtime = SelfHealingModelRuntime(bundle=fake_bundle())
        with self.assertRaises(ModelInputError):
            runtime.predict(payload(0, complete=False))


if __name__ == "__main__":
    unittest.main()
