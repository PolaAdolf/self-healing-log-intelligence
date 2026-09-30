"""Exploratory timing evidence; deliberately does not infer topology or outage."""
import json
from pathlib import Path

import pandas as pd

from train_v2_models import load_source_frames
from failure_prediction import FAILURE_FIELDS, STEP


def review(input_dir=Path("outputs_v2")):
    sources = load_source_frames(input_dir)
    rows = []
    for source, a in sources.items():
        if source not in FAILURE_FIELDS:
            continue
        field = FAILURE_FIELDS[source]
        if field not in a["frame"]:
            continue
        left = pd.DataFrame({"time": pd.to_datetime(a["frame"][a["timestamp"]], utc=True),
                             "a_failure": a["frame"][field].gt(0)})
        for target, b in sources.items():
            other = FAILURE_FIELDS.get(target)
            if source == target or other not in b["frame"]:
                continue
            right = pd.DataFrame({"time": pd.to_datetime(b["frame"][b["timestamp"]], utc=True),
                                  "b_failure": b["frame"][other].gt(0)})
            for delay in (0, 1):
                shifted = right.copy()
                shifted["time"] -= delay * STEP
                joined = left.merge(shifted, on="time", validate="one_to_one")
                if joined.empty:
                    continue
                exposed = joined.loc[joined["a_failure"], "b_failure"]
                quiet = joined.loc[~joined["a_failure"], "b_failure"]
                rows.append({"source": source, "target": target, "target_delay_minutes": delay * 5,
                    "joint_complete_windows": len(joined), "source_failure_windows": len(exposed),
                    "both_failure_windows": int(exposed.sum()),
                    "target_failure_rate_when_source_fails": float(exposed.mean()) if len(exposed) else None,
                    "target_failure_rate_when_source_quiet": float(quiet.mean()) if len(quiet) else None,
                    "target_base_rate": float(joined["b_failure"].mean())})
    report = {"status": "exploratory_only_no_confirmed_host_or_service_mapping",
        "time_policy": "Uses current UTC normalization, including explicitly assumed UTC sources. No offset optimized to improve results.",
        "limits": ["Timing association is not causation or a confirmed dependency.",
                   "File-range coverage is inferred, not collector-verified.",
                   "No logs does not prove server downtime; heartbeat and source identity are absent.",
                   "Repeated windows can belong to the same failure episode; counts are not independent incident counts.",
                   "This full-archive exploration is not a held-out prediction evaluation."],
        "comparisons": rows}
    path = input_dir / "cross_source_review.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved {len(rows)} directional timing comparisons to {path}")
    return report


if __name__ == "__main__":
    review()
