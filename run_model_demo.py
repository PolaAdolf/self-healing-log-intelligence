from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pandas as pd

from failure_prediction import load_forecast_artifacts
from model_runtime import REQUIRED_WINDOWS, WINDOW_DURATION, SelfHealingModelRuntime


MODEL_FILE = Path("models_v2/self_healing_v2.joblib")
KNOWN_UTC_FILE = Path("outputs_v2/known_utc_5min_features.csv")
ASSUMED_UTC_FILE = Path("outputs_v2/assumed_utc_5min_features.csv")
DEMO_SOURCES = (
    "apache",
    "iis",
    "apache_error",
    "windows_eventviewer",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a deterministic live demo with 12 real five-minute windows."
    )
    parser.add_argument(
        "--source",
        choices=DEMO_SOURCES,
        default="apache",
        help="Trained source model to demonstrate (default: apache).",
    )
    parser.add_argument(
        "--mode",
        choices=("service", "cli"),
        default="service",
        help=(
            "service loads the model once like a long-running worker; cli starts "
            "a new process for every file (default: service)."
        ),
    )
    return parser.parse_args()


def load_source_rows(source: str, base_features: list[str]) -> pd.DataFrame:
    if source in {"apache", "iis"}:
        frame = pd.read_csv(KNOWN_UTC_FILE)
        start_column = "window_start_utc"
        end_column = "window_end_utc"
        complete_column = f"{source}_window_complete"
    else:
        frame = pd.read_csv(ASSUMED_UTC_FILE)
        frame = frame.loc[frame["timeline"].eq(source)].copy()
        start_column = "window_start_utc"
        end_column = "window_end_utc"
        complete_column = "window_complete"

    required_columns = [start_column, end_column, complete_column, *base_features]
    missing_columns = sorted(set(required_columns) - set(frame.columns))
    if missing_columns:
        raise RuntimeError(f"Prepared data is missing columns: {', '.join(missing_columns)}")

    frame = frame.loc[frame[complete_column].eq(1), required_columns].copy()
    for feature in base_features:
        frame[feature] = pd.to_numeric(frame[feature], errors="coerce").fillna(0)
    frame["_start"] = pd.to_datetime(frame[start_column])
    frame["_end"] = pd.to_datetime(frame[end_column])
    frame = frame.sort_values("_start").reset_index(drop=True)
    return frame


def first_consecutive_history(frame: pd.DataFrame) -> pd.DataFrame:
    sequence: list[int] = []
    previous: pd.Timestamp | None = None
    for index, row in frame.iterrows():
        start = row["_start"]
        if previous is None or start == previous + WINDOW_DURATION:
            sequence.append(index)
        else:
            sequence = [index]
        previous = start
        if len(sequence) == REQUIRED_WINDOWS:
            return frame.loc[sequence].copy()
    raise RuntimeError(
        f"No sequence of {REQUIRED_WINDOWS} complete consecutive windows was found."
    )


def main() -> None:
    args = parse_args()
    if not MODEL_FILE.exists():
        raise FileNotFoundError(f"Model bundle was not found: {MODEL_FILE}")

    loaded_bundle = SelfHealingModelRuntime(model_file=MODEL_FILE).bundle
    forecast_bundle, forecast_report = load_forecast_artifacts(
        MODEL_FILE.with_name("failure_prediction.joblib"),
        KNOWN_UTC_FILE.with_name("failure_prediction_report.json"),
    )
    package = loaded_bundle[args.source]
    base_features = list(package["base_features"])
    history = first_consecutive_history(load_source_rows(args.source, base_features))

    results: list[dict] = []
    runtime_script = Path(__file__).resolve().parent / "model_runtime.py"
    print("SELF-HEALING MODEL - PRODUCTION-LIKE FILE TEST")
    print(f"Mode: {args.mode}")
    print(f"Source model: {args.source}")
    print(f"Windows to send: {len(history)} x 5 minutes")
    print("\nWindow status:")
    with tempfile.TemporaryDirectory(prefix="self_healing_demo_") as temporary:
        demo_directory = Path(temporary)
        state_file = demo_directory / "runtime_state.json"
        service_runtime = SelfHealingModelRuntime(
            state_file=state_file,
            bundle=loaded_bundle,
            forecast_bundle=forecast_bundle,
            forecast_report=forecast_report,
        )
        for number, (_, row) in enumerate(history.iterrows(), start=1):
            payload = {
                "source_model": args.source,
                "window_start": row["_start"].isoformat(),
                "window_end": row["_end"].isoformat(),
                "window_complete": True,
                "features": {name: float(row[name]) for name in base_features},
            }
            input_file = demo_directory / f"window_{number:02d}.json"
            output_file = demo_directory / f"prediction_{number:02d}.json"
            input_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            if args.mode == "service":
                request = json.loads(input_file.read_text(encoding="utf-8"))
                result = service_runtime.predict(request)
                temporary_output = output_file.with_suffix(".json.tmp")
                temporary_output.write_text(
                    json.dumps(result, indent=2), encoding="utf-8"
                )
                temporary_output.replace(output_file)
            else:
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(runtime_script),
                        "--input",
                        str(input_file),
                        "--output",
                        str(output_file),
                        "--models",
                        str(MODEL_FILE.resolve()),
                        "--state",
                        str(state_file),
                    ],
                    cwd=Path(__file__).resolve().parent,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if completed.returncode != 0:
                    raise RuntimeError(
                        f"Window {number} failed: {completed.stderr or completed.stdout}"
                    )
                result = json.loads(output_file.read_text(encoding="utf-8"))
            results.append(result)
            print(f"  {number:02d}: {result['current_status']}", flush=True)

    print("\nFinal model response:")
    print(json.dumps(results[-1], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
