"""Forecast observed error events, independently of anomaly-derived labels."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_score, recall_score, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler

from train_v2_models import load_source_frames, engineer_features, choose_threshold
from forecast_policy import PREVIEW, UNAVAILABLE, forecast_availability

STEP = pd.Timedelta(300, unit="s")
FAILURE_FIELDS = {
    "apache": "apache_5xx_count", "iis": "iis_5xx_count",
    "tomcat": "tomcat_5xx_count", "apache_error": "error_count",
    "windows_eventviewer": "error_count",
    "application_ua_integration": "error_count",
}


def prepare(frame, timestamp, base_features):
    """Never carry rolling history across a gap; match the runtime's 12 windows."""
    frame = frame.copy()
    frame[timestamp] = pd.to_datetime(frame[timestamp], utc=True)
    frame = frame.sort_values(timestamp).reset_index(drop=True)
    if frame[timestamp].duplicated().any():
        raise ValueError("Duplicate feature window")
    groups = frame[timestamp].diff().ne(STEP).cumsum()
    pieces = []
    names = []
    for _, part in frame.groupby(groups, sort=False):
        engineered, names = engineer_features(part, timestamp, base_features)
        engineered["history_ready"] = np.arange(len(engineered)) >= 11
        pieces.append(engineered)
    if not pieces:
        return frame, names
    return pd.concat(pieces, ignore_index=True), names


def future_targets(frame, timestamp, failure_field, steps):
    """Label any observed failure in the next H COMPLETE contiguous windows.

    Unknown future coverage/tail windows stay missing. Includes recurrence and
    persistence; this target is not a confirmed incident onset.
    """
    ts = pd.to_datetime(frame[timestamp], utc=True)
    failure = frame[failure_field].gt(0)
    valid = pd.Series(True, index=frame.index)
    future = pd.Series(False, index=frame.index)
    for offset in range(1, steps + 1):
        valid &= ts.shift(-offset).eq(ts + offset * STEP)
        future |= failure.shift(-offset, fill_value=False)
    return future.astype(float).where(valid)


def evaluate(y, scores, threshold):
    predicted = scores >= threshold
    return {
        "rows": len(y), "positives": int(y.sum()),
        "prevalence": float(y.mean()),
        "average_precision": float(average_precision_score(y, scores)) if y.sum() > 0 else None,
        "precision": float(precision_score(y, predicted, zero_division=0)),
        "recall": float(recall_score(y, predicted, zero_division=0)),
        "f1": float(f1_score(y, predicted, zero_division=0)),
        "false_alert_windows": int(((np.asarray(y) == 0) & predicted).sum()),
    }


def candidate_scores(candidates, features, labels, stop_times, start_times):
    """Rank candidates on expanding development folds with purged targets."""
    folds = []
    for fraction in (.4, .6, .8):
        start = int(len(labels) * fraction)
        end = min(len(labels), start + len(labels) // 5)
        fit = (stop_times < start_times.iloc[start]).to_numpy()
        validation = labels.iloc[start:end]
        keep = stop_times.iloc[start:end] < start_times.iloc[end] if end < len(labels) else validation.notna()
        validation = validation.loc[keep]
        if fit.sum() < 100 or labels.loc[fit].nunique() < 2 or validation.nunique() < 2 or validation.sum() < 5:
            continue
        folds.append((fit, validation))
    if not folds:
        return {}
    ranking = {}
    for name, model in candidates.items():
        scores = []
        for fit, validation in folds:
            estimator = clone(model).fit(features.loc[fit], labels.loc[fit])
            predictions = estimator.predict_proba(features.loc[validation.index])[:, 1]
            scores.append(average_precision_score(validation, predictions))
        ranking[name] = float(np.mean(scores))
    return ranking


def train(input_dir: Path, model_path: Path, report_path: Path, compare_candidates=False):
    bundle, reports = {}, []
    for source, config in load_source_frames(input_dir).items():
        field = FAILURE_FIELDS.get(source)
        if field is None or field not in config["frame"]:
            continue
        frame, names = prepare(config["frame"], config["timestamp"], config["base_features"])
        n = len(frame)
        train_end, val_end = int(n * .6), int(n * .8)
        ts = frame[config["timestamp"]]
        for horizon, steps in ((5, 1), (15, 3)):
            report = {"source": source, "horizon_minutes": horizon,
                      "target": f"At least one {field} event in the next {horizon} minutes",
                      "status": "insufficient_history_or_classes"}
            reports.append(report)
            if n < 500:
                continue
            target = future_targets(frame, config["timestamp"], field, steps)
            ready = frame["history_ready"] & target.notna()
            # Purge labels that reach into the next split. Split boundaries are
            # fixed before fitting, candidate selection, or threshold selection.
            masks = [ready & (ts + steps * STEP < ts.iloc[train_end]),
                     ready & (ts >= ts.iloc[train_end]) & (ts + steps * STEP < ts.iloc[val_end]),
                     ready & (ts >= ts.iloc[val_end])]
            ys = [target.loc[m].astype(int) for m in masks]
            report["split_positive_counts"] = [int(y.sum()) for y in ys]
            if len(ys[0]) < 100 or ys[0].nunique() < 2 or ys[0].sum() < 5 or any(len(y) < 20 for y in ys[1:]):
                report["split_positive_counts"] = [int(y.sum()) for y in ys]
                continue
            xs = [frame.loc[m, names] for m in masks]
            candidates = {
                "logistic_regression": make_pipeline(RobustScaler(), LogisticRegression(max_iter=2000, random_state=42)),
                "random_forest": RandomForestClassifier(n_estimators=250, max_depth=8,
                    min_samples_leaf=8, random_state=42, n_jobs=-1),
            }
            if compare_candidates:
                candidates["hist_gradient_boosting"] = HistGradientBoostingClassifier(
                    max_iter=120, max_leaf_nodes=15, min_samples_leaf=20,
                    l2_regularization=1.0, random_state=42)
                candidates["shallow_random_forest"] = RandomForestClassifier(
                    n_estimators=160, max_depth=4, min_samples_leaf=16, random_state=42, n_jobs=-1)
            validation_usable = ys[1].nunique() == 2 and ys[1].sum() >= 5
            if validation_usable:
                fitted = []
                for name, estimator in candidates.items():
                    estimator.fit(xs[0], ys[0])
                    validation = estimator.predict_proba(xs[1])[:, 1]
                    fitted.append((float(average_precision_score(ys[1], validation)), name, estimator, validation))
                _, name, estimator, validation = max(fitted, key=lambda row: row[0])
                if compare_candidates:
                    report["candidate_validation_ap"] = {candidate: ap for ap, candidate, _, _ in fitted}
                threshold = choose_threshold(ys[1], validation)
            else:
                # Fixed fallback chosen without test-set tuning. Inference is
                # available for development but cannot pass a validation gate.
                selected = "random_forest"
                suffix = "_fixed_unvalidated"
                if compare_candidates:
                    training_time = ts.loc[masks[0]]
                    ranking = candidate_scores(candidates, xs[0], ys[0], training_time + steps * STEP, training_time)
                    report["candidate_development_fold_ap"] = ranking
                    if ranking:
                        selected = max(ranking, key=ranking.get)
                        suffix = "_development_folds_unvalidated"
                name = selected + suffix
                estimator = candidates[selected]
                estimator.fit(xs[0], ys[0])
                validation = estimator.predict_proba(xs[1])[:, 1]
                threshold = .5
            scores = estimator.predict_proba(xs[2])[:, 1]
            metrics = evaluate(ys[2], scores, threshold)
            persistence = frame.loc[masks[2], field].gt(0).astype(float).to_numpy()
            baseline = evaluate(ys[2], persistence, .5)
            constant = evaluate(ys[2], np.full(len(ys[2]), ys[0].mean()), .5)
            comparable = validation_usable and ys[2].nunique() == 2 and ys[2].sum() >= 5
            better = comparable and metrics["average_precision"] > max(baseline["average_precision"], constant["average_precision"])
            status = ("development_baseline_improvement" if better else
                      "experimental_no_baseline_improvement" if comparable else "experimental_insufficient_validation_events")
            report.update(status=status, algorithm=name, threshold=float(threshold),
                validation_average_precision=float(average_precision_score(ys[1], validation)) if ys[1].sum() else None,
                test=metrics, persistence_baseline=baseline, prevalence_baseline=constant,
                train_rows=len(ys[0]), validation_rows=len(ys[1]),
                test_start=str(ts.loc[masks[2]].iloc[0]), test_end=str(ts.loc[masks[2]].iloc[-1]))
            package = bundle.setdefault(source, {"base_features": config["base_features"],
                "timestamp": config["timestamp"], "features": names,
                "failure_field": field, "horizons": {}})
            package["horizons"][str(horizon)] = {"model": estimator, "threshold": float(threshold),
                "validation_status": status, "algorithm": name, "target": report["target"]}
    model_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_path)
    report_path.write_text(json.dumps({"label_origin": "Observed failures in supplied logs; no dummy labels",
        "target_type": "future_failure_presence_including_persistence_and_recurrence",
        "split": "chronological 60/20/20, purged future targets, full contiguous 12-window history",
        "limitation": "Development evaluation on the supplied archive; not an independent production benchmark. Scores are uncalibrated model scores, not incident probabilities.",
        "results": reports}, indent=2), encoding="utf-8")
    for row in reports:
        print(row["source"], row["horizon_minutes"], row["status"], row.get("test", {}))
    return bundle


def predict_history(bundle, source, history, report=None):
    if source not in bundle:
        return {"status": "insufficient_training_history", "forecasts": []}
    package = bundle[source]
    frame = pd.DataFrame([{package["timestamp"]: item["window_start"], **item["features"]} for item in history])
    frame, _ = prepare(frame, package["timestamp"], package["base_features"])
    if len(frame) < 12 or not bool(frame.iloc[-1]["history_ready"]):
        return {"status": "awaiting_history", "forecasts": []}
    matrix = frame.iloc[[-1]][package["features"]]
    failure_field = package["failure_field"]
    recent_failures = [float(item["features"].get(failure_field, 0)) for item in history]
    current_features = history[-1]["features"]
    explanation = {
        "current_failure_count": recent_failures[-1],
        "failure_windows_in_last_12": sum(value > 0 for value in recent_failures),
        "failure_count_in_last_12": sum(recent_failures),
        "history_windows": len(history),
    }
    request_field = next((name for name in package["base_features"] if name.endswith("_request_count")), None)
    four_xx_field = next((name for name in package["base_features"] if name.endswith("_4xx_count")), None)
    if request_field:
        recent_requests = sum(float(item["features"].get(request_field, 0)) for item in history)
        explanation.update(
            current_request_count=float(current_features.get(request_field, 0)),
            current_failure_rate=(recent_failures[-1] / current_features[request_field] if current_features.get(request_field, 0) else None),
            request_count_in_last_12=recent_requests,
            failure_rate_in_last_12=(sum(recent_failures) / recent_requests if recent_requests else None),
        )
    if four_xx_field:
        recent_four_xx = sum(float(item["features"].get(four_xx_field, 0)) for item in history)
        explanation.update(
            current_4xx_count=float(current_features.get(four_xx_field, 0)),
            four_xx_count_in_last_12=recent_four_xx,
            four_xx_rate_in_last_12=(recent_four_xx / explanation["request_count_in_last_12"] if explanation.get("request_count_in_last_12") else None),
        )
    forecasts = []
    availability = {}
    report = report or {}
    for horizon in (5, 15):
        key = str(horizon)
        availability[key] = (
            forecast_availability(report, source, horizon)
            if key in package["horizons"] else UNAVAILABLE
        )
    for horizon, item in package["horizons"].items():
        if availability.get(horizon) != PREVIEW:
            continue
        score = float(item["model"].predict_proba(matrix)[0, 1])
        forecasts.append({"horizon_minutes": int(horizon), "score": round(score * 100, 2),
            "threshold": round(float(item["threshold"]) * 100, 2),
            "prediction": "elevated_experimental_signal" if score >= item["threshold"] else "lower_experimental_signal",
            "validation_status": item["validation_status"], "algorithm": item.get("algorithm", "unknown"), "target": item["target"]})
    return {"status": "scored" if forecasts else "withheld", "availability": availability,
            "score_meaning": "Uncalibrated model score on a 0–100 display scale.",
            "explanation": explanation, "forecasts": forecasts}


def load_forecast_artifacts(model_path, report_path):
    bundle = joblib.load(model_path) if model_path.is_file() else {}
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    return bundle, report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("outputs_v2"))
    parser.add_argument("--models", type=Path, default=Path("models_v2/failure_prediction.joblib"))
    parser.add_argument("--report", type=Path, default=Path("outputs_v2/failure_prediction_report.json"))
    parser.add_argument("--compare-candidates", action="store_true",
                        help="Compare additional forecast estimators using development data only.")
    args = parser.parse_args()
    train(args.input, args.models, args.report, compare_candidates=args.compare_candidates)
