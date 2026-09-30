from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import pandas as pd


SOURCE_FEATURES = {
    "apache": [
        "apache_request_count",
        "apache_2xx_count",
        "apache_bytes_sent",
        "apache_4xx_count",
        "apache_5xx_count",
        "apache_3xx_count",
    ],
    "iis": [
        "iis_request_count",
        "iis_2xx_count",
        "iis_response_ms_max",
        "iis_5xx_count",
        "iis_3xx_count",
        "iis_4xx_count",
        "iis_avg_response_ms",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build leakage-safe incident-onset targets for UTC feature windows."
    )
    parser.add_argument(
        "--features",
        type=Path,
        default=Path("outputs_v2/known_utc_5min_features.csv"),
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path("examples/dummy_incidents.json"),
    )
    parser.add_argument("--source", choices=sorted(SOURCE_FEATURES), default="apache")
    parser.add_argument(
        "--label-status",
        choices=("confirmed", "synthetic"),
        default="synthetic",
        help="Use synthetic only for pipeline testing; use confirmed for approved labels.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs_v2/dummy_incident_targets.csv"),
    )
    return parser.parse_args()


def load_incidents(
    path: Path, source: str, allowed_statuses: Iterable[str]
) -> list[dict]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Incident label file must contain a JSON array")
    allowed = set(allowed_statuses)
    selected: list[dict] = []
    for record in records:
        if record.get("label_status") not in allowed:
            continue
        if source not in record.get("source_models", []):
            continue
        start = pd.Timestamp(record["start_time_utc"])
        end = pd.Timestamp(record["end_time_utc"])
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError(f"Incident {record.get('incident_id')} must use UTC timestamps")
        start = start.tz_convert("UTC")
        end = end.tz_convert("UTC")
        if end <= start:
            raise ValueError(f"Incident {record.get('incident_id')} has an invalid interval")
        selected.append({**record, "_start": start, "_end": end})
    return selected


def build_targets(
    feature_frame: pd.DataFrame,
    incidents: list[dict],
    source: str,
    horizons: tuple[int, ...] = (5, 15),
) -> pd.DataFrame:
    features = SOURCE_FEATURES[source]
    complete_column = f"{source}_window_complete"
    required = {"window_start_utc", "window_end_utc", complete_column, *features}
    missing = sorted(required - set(feature_frame.columns))
    if missing:
        raise ValueError(f"Feature table is missing: {', '.join(missing)}")

    result = feature_frame.loc[
        feature_frame[complete_column].eq(1),
        ["window_start_utc", "window_end_utc", *features],
    ].copy()
    result = result.dropna(subset=features)
    result["window_start_utc"] = pd.to_datetime(result["window_start_utc"], utc=True)
    result["window_end_utc"] = pd.to_datetime(result["window_end_utc"], utc=True)
    result.insert(0, "source_model", source)

    active_flags: list[int] = []
    targets = {horizon: [] for horizon in horizons}
    for timestamp in result["window_end_utc"]:
        active = any(
            incident["_start"] <= timestamp < incident["_end"]
            for incident in incidents
        )
        active_flags.append(int(active))
        for horizon in horizons:
            future_end = timestamp + pd.Timedelta(horizon * 60, unit="s")
            onset = any(
                timestamp < incident["_start"] <= future_end
                for incident in incidents
            )
            targets[horizon].append(pd.NA if active else int(onset))

    result["incident_active_at_window_end"] = active_flags
    for horizon in horizons:
        result[f"incident_onset_within_{horizon}m"] = pd.array(
            targets[horizon], dtype="Int64"
        )
    return result


def main() -> None:
    args = parse_args()
    incidents = load_incidents(args.labels, args.source, [args.label_status])
    features = pd.read_csv(args.features)
    result = build_targets(features, incidents, args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)

    summary = {
        "source_model": args.source,
        "label_status": args.label_status,
        "incident_count": len(incidents),
        "eligible_windows": int(result["incident_active_at_window_end"].eq(0).sum()),
        "active_incident_windows_excluded": int(
            result["incident_active_at_window_end"].eq(1).sum()
        ),
        "positive_5m_targets": int(result["incident_onset_within_5m"].sum()),
        "positive_15m_targets": int(result["incident_onset_within_15m"].sum()),
        "output": str(args.output),
        "warning": (
            "Synthetic labels test pipeline behavior only and are not evidence of "
            "incident-prediction performance."
            if args.label_status == "synthetic"
            else None
        ),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
