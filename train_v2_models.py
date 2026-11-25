from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler


RANDOM_STATE = 42
MIN_DETECTOR_WINDOWS = 500
MIN_FORECAST_POSITIVES = 12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train source-specific v2 anomaly and proxy early-warning models"
    )
    parser.add_argument("--input", type=Path, default=Path("outputs_v2"))
    parser.add_argument("--models", type=Path, default=Path("models_v2"))
    parser.add_argument("--output", type=Path, default=Path("outputs_v2"))
    return parser.parse_args()


def load_source_frames(input_dir: Path) -> dict[str, dict]:
    frames: dict[str, dict] = {}
    known_path = input_dir / "known_utc_5min_features.csv"
    if known_path.exists():
        known = pd.read_csv(known_path)
        for source in ("apache", "iis", "tomcat"):
            coverage = f"{source}_coverage_inferred"
            if coverage not in known:
                continue
            complete = f"{source}_window_complete"
            mask = known[coverage] == 1
            if complete in known:
                mask &= known[complete] == 1
            frame = known.loc[mask].copy()
            if frame.empty:
                continue
            columns = [
                column
                for column in frame.columns
                if column.startswith(f"{source}_")
                and column != coverage
                and (
                    column.endswith("_count")
                    or column.endswith("_bytes_sent")
                    or column.endswith("_response_ms")
                    or column.endswith("_response_ms_max")
                )
            ]
            frames[source] = {
                "frame": frame,
                "timestamp": "window_start_utc",
                "base_features": columns,
                "time_basis": "UTC",
            }

    assumed_utc_path = input_dir / "assumed_utc_5min_features.csv"
    if assumed_utc_path.exists():
        assumed_utc = pd.read_csv(assumed_utc_path)
        for timeline, frame in assumed_utc.groupby("timeline", sort=True):
            if "window_complete" in frame:
                frame = frame.loc[frame["window_complete"] == 1].copy()
            if frame.empty:
                continue
            columns = [column for column in frame.columns if column.endswith("_count")]
            frames[timeline] = {
                "frame": frame.copy(),
                "timestamp": "window_start_utc",
                "base_features": columns,
                "time_basis": "UTC",
            }
    return frames


def engineer_features(
    frame: pd.DataFrame,
    timestamp_column: str,
    base_features: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    result = frame.copy()
    result[timestamp_column] = pd.to_datetime(result[timestamp_column], errors="coerce")
    result = result.dropna(subset=[timestamp_column]).sort_values(timestamp_column).reset_index(drop=True)
    for column in base_features:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0)

    hour = result[timestamp_column].dt.hour + result[timestamp_column].dt.minute / 60
    result["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    result["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    feature_columns = list(base_features) + ["hour_sin", "hour_cos"]

    for column in base_features:
        additions = {
            f"{column}_lag_1": result[column].shift(1),
            f"{column}_diff_1": result[column].diff(1),
            f"{column}_rolling_3_mean": result[column].rolling(3, min_periods=1).mean(),
            f"{column}_rolling_12_mean": result[column].rolling(12, min_periods=1).mean(),
            f"{column}_rolling_12_max": result[column].rolling(12, min_periods=1).max(),
        }
        for name, values in additions.items():
            result[name] = values
            feature_columns.append(name)
    return result, feature_columns


def percentile_scores(raw_scores: np.ndarray, sorted_reference: np.ndarray) -> np.ndarray:
    ranks = np.searchsorted(sorted_reference, raw_scores, side="right")
    return np.clip(100 * ranks / max(len(sorted_reference), 1), 0, 100)


def choose_threshold(y_true: pd.Series, scores: np.ndarray) -> float:
    candidates = np.unique(np.quantile(scores, np.linspace(0.5, 0.99, 100)))
    best = (0.5, -1.0, -1.0)
    for threshold in candidates:
        predicted = scores >= threshold
        f1 = f1_score(y_true, predicted, zero_division=0)
        precision = precision_score(y_true, predicted, zero_division=0)
        if (f1, precision) > (best[1], best[2]):
            best = (float(threshold), float(f1), float(precision))
    return best[0]


def metric_row(
    source: str,
    horizon: str,
    split: str,
    y_true: pd.Series,
    scores: np.ndarray,
    threshold: float,
    timestamps: pd.Series,
) -> dict:
    predicted = scores >= threshold
    tp = int(((predicted == 1) & (y_true.to_numpy() == 1)).sum())
    fp = int(((predicted == 1) & (y_true.to_numpy() == 0)).sum())
    fn = int(((predicted == 0) & (y_true.to_numpy() == 1)).sum())
    duration_days = max(
        (timestamps.max() - timestamps.min()).total_seconds() / 86400,
        5 / 1440,
    )
    positive_rate = float(y_true.mean())
    pr_auc = (
        float(average_precision_score(y_true, scores))
        if y_true.nunique() > 1
        else np.nan
    )
    false_alerts_per_day = fp / duration_days
    return {
        "source_model": source,
        "horizon": horizon,
        "evaluation_split": split,
        "label_type": "proxy_unusual_onset",
        "rows": len(y_true),
        "positive_rows": int(y_true.sum()),
        "positive_rate": positive_rate,
        "threshold": threshold,
        "pr_auc": pr_auc,
        "pr_auc_lift_over_baseline": pr_auc - positive_rate,
        "precision": precision_score(y_true, predicted, zero_division=0),
        "recall": recall_score(y_true, predicted, zero_division=0),
        "f1": f1_score(y_true, predicted, zero_division=0),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "false_alert_windows_per_day": false_alerts_per_day,
        "acceptance_status": (
            "accepted_development_only"
            if pr_auc > positive_rate and false_alerts_per_day <= 12
            else "rejected"
        ),
    }


def main() -> None:
    args = parse_args()
    args.models.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    sources = load_source_frames(args.input)
    bundle: dict[str, dict] = {}
    metrics: list[dict] = []
    inventory: list[dict] = []

    for source, config in sources.items():
        engineered, features = engineer_features(
            config["frame"], config["timestamp"], config["base_features"]
        )
        n_rows = len(engineered)
        inventory_row = {
            "source_model": source,
            "time_basis": config["time_basis"],
            "windows": n_rows,
            "detector_status": "insufficient_history",
            "forecast_5m_status": "not_trained",
            "forecast_15m_status": "not_trained",
        }
        if n_rows < MIN_DETECTOR_WINDOWS or not config["base_features"]:
            inventory.append(inventory_row)
            continue

        train_end = int(n_rows * 0.60)
        validation_end = int(n_rows * 0.80)
        window = pd.Timedelta(minutes=5)
        timestamps = engineered[config["timestamp"]]
        runs = timestamps.diff().ne(window).cumsum()
        ready = engineered.groupby(runs).cumcount().ge(11)
        training = ready & (engineered.index < train_end)
        if training.sum() < 100:
            inventory.append(inventory_row)
            continue
        detector = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scale", RobustScaler()),
                (
                    "model",
                    IsolationForest(
                        n_estimators=400,
                        max_samples="auto",
                        contamination="auto",
                        random_state=RANDOM_STATE,
                        n_jobs=-1,
                    ),
                ),
            ]
        )
        detector.fit(engineered.loc[training, features])
        raw_scores = -detector.decision_function(engineered[features])
        sorted_train_scores = np.sort(raw_scores[training.to_numpy()])
        anomaly_threshold = float(np.quantile(sorted_train_scores, 0.99))
        engineered["proxy_unusual"] = (raw_scores >= anomaly_threshold).astype(int)
        engineered["proxy_onset"] = (
            (engineered["proxy_unusual"] == 1)
            & (engineered["proxy_unusual"].shift(1, fill_value=0) == 0)
        ).astype(int)

        package = {
            "source_model": source,
            "time_basis": config["time_basis"],
            "timestamp_column": config["timestamp"],
            "base_features": config["base_features"],
            "features": features,
            "detector": detector,
            "detector_reference_scores": sorted_train_scores,
            "detector_raw_threshold": anomaly_threshold,
            "detector_score_threshold": float(
                percentile_scores(np.array([anomaly_threshold]), sorted_train_scores)[0]
            ),
            "forecast_models": {},
            "training_rows": train_end,
            "contiguous_training_windows": int(training.sum()),
            "validation_end_row": validation_end,
            "label_type": "proxy_unusual_onset",
        }
        inventory_row["detector_status"] = "trained"

        for horizon, steps in (("5m", 1), ("15m", 3)):
            future = pd.concat(
                [engineered["proxy_onset"].shift(-step) for step in range(1, steps + 1)],
                axis=1,
            )
            target = future.max(axis=1, skipna=False)
            eligible = (engineered["proxy_unusual"] == 0) & target.notna()
            train_mask = eligible & (engineered.index < train_end - steps)
            validation_mask = eligible & (engineered.index >= train_end) & (
                engineered.index < validation_end - steps
            )
            test_mask = eligible & (engineered.index >= validation_end)
            y_train = target.loc[train_mask].astype(int)
            y_validation = target.loc[validation_mask].astype(int)
            y_test = target.loc[test_mask].astype(int)
            if (
                y_train.sum() < MIN_FORECAST_POSITIVES
                or y_validation.sum() < 2
                or y_train.nunique() < 2
                or y_validation.nunique() < 2
            ):
                inventory_row[f"forecast_{horizon}_status"] = "insufficient_proxy_onsets"
                continue

            forecast = Pipeline(
                [
                    ("imputer", SimpleImputer(strategy="median")),
                    (
                        "model",
                        RandomForestClassifier(
                            n_estimators=500,
                            max_depth=10,
                            min_samples_leaf=4,
                            max_features="sqrt",
                            class_weight="balanced_subsample",
                            random_state=RANDOM_STATE,
                            n_jobs=-1,
                        ),
                    ),
                ]
            )
            forecast.fit(engineered.loc[train_mask, features], y_train)
            validation_scores = forecast.predict_proba(
                engineered.loc[validation_mask, features]
            )[:, 1]
            threshold = choose_threshold(y_validation, validation_scores)
            test_scores = forecast.predict_proba(engineered.loc[test_mask, features])[:, 1]
            result = metric_row(
                source,
                horizon,
                "development_test",
                y_test,
                test_scores,
                threshold,
                engineered.loc[test_mask, config["timestamp"]],
            )
            metrics.append(result)
            if result["acceptance_status"] == "accepted_development_only":
                package["forecast_models"][horizon] = {
                    "model": forecast,
                    "threshold": threshold,
                    "steps": steps,
                }
                inventory_row[f"forecast_{horizon}_status"] = "accepted_development_only"
            elif result["pr_auc_lift_over_baseline"] <= 0:
                inventory_row[f"forecast_{horizon}_status"] = "rejected_no_test_lift"
            else:
                inventory_row[f"forecast_{horizon}_status"] = "rejected_alert_flooding"

        bundle[source] = package
        inventory.append(inventory_row)

    joblib.dump(bundle, args.models / "self_healing_v2.joblib")
    metrics_df = pd.DataFrame(metrics)
    metrics_df.to_csv(args.output / "v2_development_metrics.csv", index=False)
    inventory_df = pd.DataFrame(inventory)
    inventory_df.to_csv(args.output / "v2_model_inventory.csv", index=False)

    card = {
        "model_version": "2.2.0-development",
        "detector_models": sorted(bundle),
        "legacy_proxy_candidates": [
            f"{source}:{horizon}"
            for source, package in sorted(bundle.items())
            for horizon in sorted(package["forecast_models"])
        ],
        "detector_fit_scope": "First 60% of each source, with 12 consecutive complete windows",
        "current_score_meaning": "percentile of anomaly extremeness against training history",
        "forecast_score_meaning": "Experimental score for future recorded errors, including recurrence",
        "not_a_probability": True,
        "forecast_preview_gate": "At least 20 positive test windows and higher average precision than persistence",
        "production_limit": "Requires human incident labels and untouched later data",
    }
    (args.models / "model_card.json").write_text(
        json.dumps(card, indent=2), encoding="utf-8"
    )
    print(f"Trained detector models: {len(bundle)}")
    print(f"Development metric rows: {len(metrics_df)}")
    print(inventory_df.to_string(index=False))


if __name__ == "__main__":
    main()
