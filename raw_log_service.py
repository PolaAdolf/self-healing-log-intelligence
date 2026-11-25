"""Local raw-log upload and real inference. No replay or generated demo data."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import joblib
import pandas as pd

from build_corrected_dataset import (BuildState, LINEAGE_FIELDS, DIAGNOSTIC_FIELDS,
    FAILURE_FIELDS, parse_apache_access, parse_iis, parse_apache_errors, parse_event_csv,
    export_known_features, export_assumed_utc_features)
from failure_prediction import load_forecast_artifacts, prepare, predict_history
from model_runtime import MODEL_VERSION, SelfHealingModelRuntime
from train_v2_models import percentile_scores

ROOT = Path(__file__).resolve().parent
SOURCES = {"apache": "Apache access", "iis": "IIS W3C", "apache_error": "Apache error", "windows_eventviewer": "Windows Event Viewer"}


def aggregate_raw(source, input_dir, output_dir):
    if source not in SOURCES:
        raise ValueError("Unsupported source")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = sorted(p for p in input_dir.iterdir() if p.is_file())
    with gzip.open(output_dir / "lineage.csv.gz", "wt", encoding="utf-8", newline="") as lineage, \
         gzip.open(output_dir / "diagnostics.csv.gz", "wt", encoding="utf-8", newline="") as diagnostics, \
         gzip.open(output_dir / "failures.csv.gz", "wt", encoding="utf-8", newline="") as failures:
        writers = [csv.DictWriter(h, fieldnames=f) for h, f in (
            (lineage, LINEAGE_FIELDS), (diagnostics, DIAGNOSTIC_FIELDS), (failures, FAILURE_FIELDS))]
        for writer in writers:
            writer.writeheader()
        state = BuildState("5min", *writers)
        if source == "apache":
            parse_apache_access(paths, state, input_dir, "Apache")
        elif source == "iis":
            parse_iis(paths, state, input_dir)
        elif source == "apache_error":
            parse_apache_errors(paths, state, input_dir)
        else:
            parse_event_csv(paths, state, input_dir)
    parsed = sum(p.parsed_records for p in state.profiles)
    rejected = sum(p.failed_records for p in state.profiles)
    if not parsed:
        raise ValueError(f"No matching records. Check the selected source and original log format. Rejected records: {rejected}")
    # Rotated overlapping files could double-count records. Same-name snapshots
    # are replaced on upload; distinct overlapping files require operator review.
    intervals = sorted((p.min_timestamp_utc, p.max_timestamp_utc, p.source_file)
                       for p in state.profiles if p.min_timestamp_utc is not None)
    for i, current in enumerate(intervals):
        for previous in intervals[:i]:
            known_channels = {"app_eventlog_sanitized.csv", "sedco_eventlog_sanitized.csv", "system_eventlog_sanitized.csv"}
            separate_channels = source == "windows_eventviewer" and current[2].lower() in known_channels and previous[2].lower() in known_channels and current[2].lower() != previous[2].lower()
            if current[0] <= previous[1] and not separate_channels:
                raise ValueError("Uploaded files have overlapping time ranges. Use one cumulative file or non-overlapping rotations to avoid double counting.")
    if source in {"apache", "iis"}:
        frame = export_known_features(state, output_dir)
        complete = f"{source}_window_complete"
    else:
        frame = export_assumed_utc_features(state, output_dir)
        frame = frame.loc[frame["timeline"].eq(source)].copy()
        complete = "window_complete"
    summary = {"parsed_records": parsed, "rejected_records": rejected,
               "input_files": len(paths), "total_windows": len(frame),
               "complete_windows": int(frame[complete].eq(1).sum()),
               "excluded_windows": int(frame[complete].ne(1).sum()),
               "timezone_policy": "UTC from source offset/format" if source in {"apache", "iis"} else "UTC assumed for missing offset",
               "coverage": "Inferred from first and last record in each file; collector completeness is not independently verified."}
    return frame.loc[frame[complete].eq(1)].copy(), summary


def analyze(source, input_dir, output_dir, anomaly_bundle, forecast_bundle, forecast_report=None):
    frame, summary = aggregate_raw(source, input_dir, output_dir)
    package = anomaly_bundle[source]
    # Shared event CSV columns may be absent for a particular source's severity
    # vocabulary. Covered windows get zero for those unobserved event levels.
    for feature in package["base_features"]:
        if feature not in frame:
            frame[feature] = 0.0
        frame[feature] = pd.to_numeric(frame[feature], errors="coerce").fillna(0)
    engineered, _ = prepare(frame, "window_start_utc", package["base_features"])
    ready = engineered.loc[engineered.get("history_ready", pd.Series(False, index=engineered.index))].copy()
    timeline = []
    if not ready.empty:
        raw = -package["detector"].decision_function(ready[package["features"]])
        scores = percentile_scores(raw, package["detector_reference_scores"])
        failure_field = f"{source}_5xx_count" if source in {"apache", "iis"} else "error_count"
        for (_, row), score, value in zip(ready.iterrows(), scores, raw):
            timeline.append({"time": str(row["window_start_utc"]), "score": round(float(score), 2),
                "status": "unusual" if value >= package["detector_raw_threshold"] else "within_learned_range",
                "failure_count": int(row.get(failure_field, 0))})
    runtime = SelfHealingModelRuntime(bundle=anomaly_bundle)
    latest = {"current_status": "no_complete_windows", "history_windows": 0}
    # The final 12 rows suffice; the runtime resets its buffer at real gaps.
    for _, row in frame.tail(12).iterrows():
        payload = {"source_model": source, "window_start": str(row["window_start_utc"]),
            "window_end": str(row["window_end_utc"]), "window_complete": True,
            "features": {name: float(row[name]) for name in package["base_features"]}}
        latest = runtime.predict(payload)
    history = runtime.history.get(source, [])
    forecast = predict_history(forecast_bundle, source, history, forecast_report) if history else {"status": "awaiting_history", "forecasts": []}
    if "current_anomaly_score" in latest:
        latest["anomaly_explanation"] = {
            "score_meaning": "Percentile rank of anomaly extremeness against detector training history; not failure probability",
            "unusual_threshold": round(float(package["detector_score_threshold"]), 2),
            "decision": "unusual only when the score reaches or exceeds the threshold",
        }
    result = {"source": source, "model_version": MODEL_VERSION, "processed_at": datetime.now(timezone.utc).isoformat(),
        "mode": "Actual inference on uploaded raw logs", "summary": summary,
        "latest": latest, "prediction": forecast, "history_windows": len(history),
        "timeline": timeline, "assessment_note": "Uploaded historical logs can overlap model training data. This run demonstrates processing, not independent prediction accuracy."}
    (output_dir / "assessment.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    (output_dir / "runtime_state.json").write_text(json.dumps({"sources": runtime.history}, indent=2), encoding="utf-8")
    return result


class App:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.lock = threading.Lock()
        self.jobs = {}
        self.anomaly = joblib.load(ROOT / "models_v2/self_healing_v2.joblib")
        forecast = ROOT / "models_v2/failure_prediction.joblib"
        report = ROOT / "outputs_v2/failure_prediction_report.json"
        self.forecast, self.forecast_report = load_forecast_artifacts(forecast, report)

    def start(self, source):
        with self.lock:
            if self.jobs.get(source, {}).get("status") == "running":
                raise ValueError("Analysis is already running for this source")
            self.jobs[source] = {"status": "running"}
        def work():
            try:
                result = analyze(source, self.data_dir / source / "raw", self.data_dir / source / "results", self.anomaly, self.forecast, self.forecast_report)
                with self.lock:
                    self.jobs[source] = {"status": "complete", "result": result}
            except Exception as exc:
                traceback.print_exc()
                with self.lock:
                    self.jobs[source] = {"status": "failed", "error": str(exc)}
        threading.Thread(target=work, daemon=True).start()


def handler(app):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, value, content_type="application/json"):
            data = json.dumps(value, allow_nan=False).encode() if content_type == "application/json" else value
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def route(self):
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            return parsed.path, query.get("source", ["apache"])[0], query

        def do_GET(self):
            path, source, _ = self.route()
            if path == "/":
                return self.reply(200, (ROOT / "web/index.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/evaluation":
                return self.reply(200, app.forecast_report or {"results": []})
            if source not in SOURCES:
                return self.reply(400, {"error": "Unsupported source"})
            if path == "/api/status":
                with app.lock:
                    state = app.jobs.get(source)
                if state is None:
                    saved = app.data_dir / source / "results/assessment.json"
                    result = json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else {}
                    state = {"status": "complete", "result": result} if result.get("model_version") == MODEL_VERSION else {"status": "idle"}
                return self.reply(200, state)
            return self.reply(404, {"error": "Not found"})

        def do_POST(self):
            path, source, query = self.route()
            if source not in SOURCES:
                return self.reply(400, {"error": "Unsupported source"})
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                return self.reply(403, {"error": "Cross-origin writes are not allowed"})
            try:
                if path == "/api/analyze":
                    app.start(source)
                    return self.reply(202, {"status": "running"})
                if path != "/api/upload":
                    return self.reply(404, {"error": "Not found"})
                name = query.get("name", [""])[0]
                if not name or name in {".", ".."} or any(c in name for c in "/\\:") or len(name) > 180:
                    raise ValueError("Invalid file name")
                if name.lower().endswith((".rar", ".zip", ".gz", ".exe", ".joblib", ".json")):
                    raise ValueError("Upload the extracted original text log or Event Viewer CSV, not an archive or prepared JSON")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 64 * 1024 * 1024:
                    raise ValueError("Each log must be between 1 byte and 64 MB")
                content = self.rfile.read(size)
                if len(content) != size:
                    raise ValueError("Incomplete upload")
                with app.lock:
                    if app.jobs.get(source, {}).get("status") == "running":
                        raise ValueError("Wait for the current analysis before uploading")
                    folder = app.data_dir / source / "raw"
                    folder.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256(content).digest()
                    for existing in folder.iterdir():
                        if existing.is_file() and hashlib.sha256(existing.read_bytes()).digest() == digest:
                            return self.reply(200, {"status": "duplicate_ignored", "file": name})
                    target = folder / name
                    replaced = target.exists()
                    temporary = folder / (name + ".tmp")
                    temporary.write_bytes(content)
                    temporary.replace(target)
                return self.reply(201, {"status": "snapshot_replaced" if replaced else "uploaded", "file": name})
            except (ValueError, OSError) as exc:
                return self.reply(400, {"error": str(exc)})
    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local live raw-log model dashboard")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (use 0.0.0.0 only inside a private Codespace)",
    )
    parser.add_argument("--data-dir", type=Path, default=ROOT / "raw_sessions")
    args = parser.parse_args()
    app = App(args.data_dir.resolve())
    server = ThreadingHTTPServer((args.host, args.port), handler(app))
    print(f"Listening on {args.host}:{args.port} — upload original raw logs. No simulated results.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
