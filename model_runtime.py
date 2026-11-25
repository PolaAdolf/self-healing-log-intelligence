from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from score_v2_system import evidence_for, recommendations
from failure_prediction import load_forecast_artifacts, predict_history
from train_v2_models import engineer_features, percentile_scores


MODEL_VERSION = "2.2.0-development"
WINDOW_MINUTES = 5
REQUIRED_WINDOWS = 12
WINDOW_DURATION = pd.Timedelta(WINDOW_MINUTES * 60, unit="s")


class ModelInputError(ValueError):
    pass


class SelfHealingModelRuntime:
    def __init__(
        self,
        model_file: Path | None = None,
        state_file: Path | None = None,
        bundle: dict[str, dict] | None = None,
        forecast_bundle: dict | None = None,
        forecast_report: dict | None = None,
    ) -> None:
        if bundle is None:
            if model_file is None or not model_file.exists():
                raise FileNotFoundError(model_file)
            bundle = joblib.load(model_file)
        self.bundle = bundle
        self.forecast_bundle = forecast_bundle or {}
        self.forecast_report = forecast_report or {}
        self.state_file = state_file
        self.history: dict[str, list[dict[str, Any]]] = {}
        if state_file is not None and state_file.exists():
            saved = json.loads(state_file.read_text(encoding="utf-8"))
            if saved.get("model_version") in {"2.1.0-development", MODEL_VERSION}:
                self.history = saved.get("sources", {})

    def save_state(self) -> None:
        if self.state_file is None:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {"model_version": MODEL_VERSION, "sources": self.history},
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.state_file)

    def validate(self, payload: dict[str, Any]) -> tuple[str, pd.Timestamp, dict[str, float]]:
        required = {"source_model", "window_start", "window_end", "window_complete", "features"}
        missing_envelope = sorted(required - payload.keys())
        if missing_envelope:
            raise ModelInputError(f"Missing input fields: {', '.join(missing_envelope)}")
        source = str(payload["source_model"])
        if source not in self.bundle:
            return source, pd.Timestamp(payload["window_start"]), {}
        if payload["window_complete"] is not True:
            raise ModelInputError("window_complete must be true before inference")
        start = pd.Timestamp(payload["window_start"])
        end = pd.Timestamp(payload["window_end"])
        if end - start != WINDOW_DURATION:
            raise ModelInputError("The model accepts completed 5-minute windows only")
        package = self.bundle[source]
        if package["time_basis"] == "UTC":
            if start.tzinfo is None or end.tzinfo is None:
                raise ModelInputError("UTC source timestamps must include an explicit UTC offset")
            start = start.tz_convert("UTC")
            end = end.tz_convert("UTC")
        elif start.tzinfo is not None or end.tzinfo is not None:
            raise ModelInputError("Unknown-local source timestamps must not include an assumed offset")

        supplied = payload["features"]
        if not isinstance(supplied, dict):
            raise ModelInputError("features must be a JSON object")
        missing_features = [name for name in package["base_features"] if name not in supplied]
        if missing_features:
            raise ModelInputError(f"Missing model features: {', '.join(missing_features)}")
        clean: dict[str, float] = {}
        for name in package["base_features"]:
            value = supplied[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ModelInputError(f"Feature {name} must be numeric")
            numeric = float(value)
            if not math.isfinite(numeric) or numeric < 0:
                raise ModelInputError(f"Feature {name} must be finite and non-negative")
            clean[name] = numeric
        return source, start, clean

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        source, start, features = self.validate(payload)
        if source not in self.bundle:
            return {
                "model_version": MODEL_VERSION,
                "source_model": source,
                "window_start": str(start),
                "current_status": "model_not_available",
                "current_anomaly_score": None,
                "forecast_status_5m": "not_available",
                "forecast_status_15m": "not_available",
                "recommended_action": "collect_training_history",
            }

        history = self.history.setdefault(source, [])
        if history:
            previous = pd.Timestamp(history[-1]["window_start"])
            expected = previous + WINDOW_DURATION
            if start <= previous:
                raise ModelInputError("Duplicate or out-of-order window")
            if start != expected:
                history.clear()
                gap_status = "awaiting_history_after_gap"
            else:
                gap_status = "awaiting_history"
        else:
            gap_status = "awaiting_history"

        history.append({"window_start": str(start), "features": features})
        del history[:-REQUIRED_WINDOWS]
        self.save_state()
        if len(history) < REQUIRED_WINDOWS:
            return {
                "model_version": MODEL_VERSION,
                "source_model": source,
                "window_start": str(start),
                "current_status": gap_status,
                "history_windows": len(history),
                "history_windows_required": REQUIRED_WINDOWS,
                "current_anomaly_score": None,
                "forecast_status_5m": "not_available",
                "forecast_status_15m": "not_available",
                "recommended_action": "wait_for_complete_history",
            }

        package = self.bundle[source]
        timestamp_column = package["timestamp_column"]
        rows = [
            {timestamp_column: item["window_start"], **item["features"]}
            for item in history
        ]
        frame, engineered_features = engineer_features(
            pd.DataFrame(rows), timestamp_column, package["base_features"]
        )
        if engineered_features != package["features"]:
            raise RuntimeError("Runtime feature schema does not match the trained model")
        current = frame.iloc[-1]
        current_matrix = frame.loc[[frame.index[-1]], package["features"]]
        raw_score = -package["detector"].decision_function(current_matrix)[0]
        anomaly_score = float(
            percentile_scores(
                np.array([raw_score]), package["detector_reference_scores"]
            )[0]
        )
        unusual = raw_score >= package["detector_raw_threshold"]
        result: dict[str, Any] = {
            "model_version": MODEL_VERSION,
            "source_model": source,
            "time_basis": package["time_basis"],
            "window_start": str(start),
            "window_end": str(pd.Timestamp(payload["window_end"])),
            "current_status": "unusual" if unusual else "within_learned_range",
            "current_anomaly_score": round(anomaly_score, 2),
            "score_definition": "Training-history anomaly percentile; not a failure probability.",
            "evidence": evidence_for(source, current, package["base_features"]),
            "recommended_checks": recommendations(source, current),
            "recommended_action": "operator_review" if unusual else "none",
        }
        prediction = predict_history(self.forecast_bundle, source, history, self.forecast_report)
        forecasts = {item["horizon_minutes"]: item for item in prediction["forecasts"]}
        for horizon in (5, 15):
            forecast = forecasts.get(horizon, {})
            availability = prediction.get("availability", {}).get(str(horizon))
            result[f"forecast_score_{horizon}m"] = forecast.get("score")
            result[f"forecast_status_{horizon}m"] = forecast.get("prediction", availability or "not_available")
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run model inference for one 5-minute feature window")
    parser.add_argument("--input", required=True, type=Path, help="JSON feature-window request")
    parser.add_argument("--output", type=Path, default=Path("prediction.json"))
    parser.add_argument(
        "--models", type=Path, default=Path("models_v2/self_healing_v2.joblib")
    )
    parser.add_argument("--state", type=Path, default=Path("runtime_state.json"))
    parser.add_argument("--forecast-models", type=Path, default=Path("models_v2/failure_prediction.joblib"))
    parser.add_argument("--forecast-report", type=Path, default=Path("outputs_v2/failure_prediction_report.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        forecasts, report = load_forecast_artifacts(args.forecast_models, args.forecast_report)
        runtime = SelfHealingModelRuntime(args.models, args.state, forecast_bundle=forecasts, forecast_report=report)
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        result = runtime.predict(payload)
    except (OSError, json.JSONDecodeError, ModelInputError) as exc:
        result = {
            "model_version": MODEL_VERSION,
            "current_status": "invalid_input",
            "error": str(exc),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
