from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from train_v2_models import load_source_frames, percentile_scores
from failure_prediction import load_forecast_artifacts, prepare
from forecast_policy import PREVIEW, forecast_availability


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score corrected feature windows with source-specific v2 models"
    )
    parser.add_argument("--input", type=Path, default=Path("outputs_v2"))
    parser.add_argument(
        "--models", type=Path, default=Path("models_v2/self_healing_v2.joblib")
    )
    parser.add_argument("--output", type=Path, default=Path("outputs_v2"))
    return parser.parse_args()


def evidence_for(source: str, row: pd.Series, base_features: list[str]) -> list[str]:
    evidence = []
    for column in base_features:
        value = row.get(column)
        if pd.notna(value) and float(value) > 0:
            evidence.append(f"{column}={float(value):g}")
    return evidence[:6]


def recommendations(source: str, row: pd.Series) -> list[str]:
    advice = ["Verify collection coverage and inspect the source records for this window."]
    if source in {"apache", "iis", "tomcat"}:
        if float(row.get(f"{source}_5xx_count", 0) or 0) > 0:
            advice.append("Check the web service/app-pool state and upstream dependencies.")
            advice.append("Review matching server errors before considering a restart.")
        if float(row.get(f"{source}_4xx_count", 0) or 0) > 0:
            advice.append("Check authentication, authorization, routing, and client request patterns.")
        if source == "iis" and float(row.get("iis_avg_response_ms", 0) or 0) > 0:
            advice.append("Compare IIS latency with application-pool and dependency health.")
    elif source == "windows_eventviewer":
        advice.append("Inspect repeated Event IDs, providers, and Service Control Manager events.")
    elif source == "apache_error":
        advice.append("Inspect the Apache module, certificate, proxy, and backend messages.")
    else:
        advice.append("Inspect ERROR/FATAL messages and explicit stop/start events for the service.")
    advice.append("Use a reviewed runbook and health check before any remediation action.")
    return list(dict.fromkeys(advice))


def score_sources(input_dir: Path, model_file: Path, output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = joblib.load(model_file)
    forecasts, forecast_report = load_forecast_artifacts(
        model_file.with_name("failure_prediction.joblib"),
        input_dir / "failure_prediction_report.json",
    )
    sources = load_source_frames(input_dir)
    scored_frames = []
    latest = []

    for source, config in sources.items():
        base_features = config["base_features"]
        if source in bundle:
            base_features = bundle[source]["base_features"]
            for column in base_features:
                if column not in config["frame"]:
                    config["frame"][column] = 0
        engineered, features = prepare(
            config["frame"], config["timestamp"], base_features
        )
        output = engineered[[config["timestamp"]] + base_features].copy()
        output.insert(0, "source_model", source)
        output.insert(1, "time_basis", config["time_basis"])

        if source not in bundle:
            output["current_status"] = "insufficient_history"
            output["current_anomaly_score"] = np.nan
            output["forecast_score_5m"] = np.nan
            output["forecast_status_5m"] = "not_available"
            output["forecast_score_15m"] = np.nan
            output["forecast_status_15m"] = "not_available"
        else:
            package = bundle[source]
            raw = -package["detector"].decision_function(engineered[features])
            current_scores = percentile_scores(raw, package["detector_reference_scores"])
            output["current_anomaly_score"] = current_scores
            output["current_status"] = np.where(
                raw >= package["detector_raw_threshold"], "unusual", "within_learned_range"
            )
            ready = engineered["history_ready"]
            output.loc[~ready, "current_anomaly_score"] = np.nan
            output.loc[~ready, "current_status"] = "awaiting_history"
            for minutes in (5, 15):
                horizon = f"{minutes}m"
                forecast_source = forecasts.get(source, {})
                forecast_package = forecast_source.get("horizons", {}).get(str(minutes))
                availability = forecast_availability(forecast_report, source, minutes)
                output[f"forecast_score_{horizon}"] = np.nan
                output[f"forecast_status_{horizon}"] = "not_available" if forecast_package is None else availability
                output.loc[~ready, f"forecast_status_{horizon}"] = "awaiting_history"
                if forecast_package is None or availability != PREVIEW or not ready.any():
                    continue
                scores = forecast_package["model"].predict_proba(engineered.loc[ready, forecast_source["features"]])[:, 1]
                output.loc[ready, f"forecast_score_{horizon}"] = scores * 100
                output.loc[ready, f"forecast_status_{horizon}"] = np.where(
                    scores >= forecast_package["threshold"],
                    "elevated_experimental_signal",
                    "lower_experimental_signal",
                )
        scored_frames.append(output)
        last = output.iloc[-1]
        latest.append(
            {
                "source_model": source,
                "time_basis": config["time_basis"],
                "window_start": str(last[config["timestamp"]]),
                "current_status": last["current_status"],
                "current_anomaly_score": (
                    None
                    if pd.isna(last["current_anomaly_score"])
                    else round(float(last["current_anomaly_score"]), 2)
                ),
                "forecast_score_5m": (
                    None
                    if pd.isna(last["forecast_score_5m"])
                    else round(float(last["forecast_score_5m"]), 2)
                ),
                "forecast_status_5m": last["forecast_status_5m"],
                "forecast_score_15m": (
                    None
                    if pd.isna(last["forecast_score_15m"])
                    else round(float(last["forecast_score_15m"]), 2)
                ),
                "forecast_status_15m": last["forecast_status_15m"],
                "current_score_warning": "The anomaly score is a training-history percentile, not a failure probability.",
                "forecast_warning": (
                    "Experimental score for future recorded errors."
                    if pd.notna(last["forecast_score_5m"]) or pd.notna(last["forecast_score_15m"])
                    else "No forecast preview is shown for this window."
                ),
                "evidence": evidence_for(source, last, base_features),
                "recommended_checks": recommendations(source, last),
            }
        )

    if scored_frames:
        pd.concat(scored_frames, ignore_index=True).to_csv(
            output_dir / "v2_scored_windows.csv", index=False
        )
    else:
        pd.DataFrame(columns=["source_model", "current_status"]).to_csv(
            output_dir / "v2_scored_windows.csv", index=False
        )
    (output_dir / "latest_system_assessment.json").write_text(
        json.dumps(latest, indent=2), encoding="utf-8"
    )
    return latest


def main() -> None:
    args = parse_args()
    scored = score_sources(args.input, args.models, args.output)
    print(f"Scored source timelines: {len(scored)}")
    print(f"Latest assessments: {args.output / 'latest_system_assessment.json'}")


if __name__ == "__main__":
    main()
