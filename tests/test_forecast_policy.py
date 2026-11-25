import unittest

from forecast_policy import BASELINE_NOT_BEATEN, PREVIEW, TOO_FEW_EVENTS, UNAVAILABLE, forecast_availability


class ForecastPolicyTests(unittest.TestCase):
    def test_requires_evidence_for_the_exact_source_and_horizon(self):
        report = {"results": [{"source": "apache", "horizon_minutes": 5,
            "test": {"positives": 56, "average_precision": .96},
            "persistence_baseline": {"average_precision": .91}}]}
        self.assertEqual(forecast_availability(report, "apache", 5), PREVIEW)
        self.assertEqual(forecast_availability(report, "apache", 15), UNAVAILABLE)
        self.assertEqual(forecast_availability(report, "iis", 5), UNAVAILABLE)
        row = report["results"][0]
        row["test"]["positives"] = 19
        self.assertEqual(forecast_availability(report, "apache", 5), TOO_FEW_EVENTS)
        row["test"]["positives"] = 56
        row["test"]["average_precision"] = .91
        self.assertEqual(forecast_availability(report, "apache", 5), BASELINE_NOT_BEATEN)
