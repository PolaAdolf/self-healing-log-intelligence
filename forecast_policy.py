"""Decide which forecast scores operators can see using archived evidence."""
from __future__ import annotations


TOO_FEW_EVENTS = "too_few_test_errors"
BASELINE_NOT_BEATEN = "persistence_baseline_not_beaten"
UNAVAILABLE = "forecast_not_evaluated"
PREVIEW = "experimental_preview"


def forecast_availability(report, source, horizon):
    row = next((item for item in report.get("results", [])
                if item["source"] == source and item["horizon_minutes"] == horizon), {})
    test = row.get("test")
    if test is None:
        return UNAVAILABLE
    if test["positives"] < 20:
        return TOO_FEW_EVENTS
    ap = test.get("average_precision")
    baseline = (row.get("persistence_baseline") or {}).get("average_precision")
    if ap is None or baseline is None or ap <= baseline:
        return BASELINE_NOT_BEATEN
    return PREVIEW
