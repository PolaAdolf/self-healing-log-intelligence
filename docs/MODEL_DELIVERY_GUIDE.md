# Deployment and integration

Release 2.2 is a development prototype. Start with the [quick start](../README.md#quick-start) and [limitations](../STATUS.md). This is an evaluation guide, not production certification.

## Run locally

Install Python 3.11 or 3.12 and the pinned requirements in a virtual environment. From the repository root:

```bash
python raw_log_service.py --data-dir tmp/dashboard_demo
```

The service binds to `127.0.0.1:8765`. Upload a supported original text log or Event Viewer CSV. Archive and model-file uploads are rejected. Keep approved uploads in the selected data directory, outside source control.

## Run in GitHub Codespaces

1. Create a Codespace from the branch you want to evaluate.
2. Allow the devcontainer to install requirements.
3. Run `python raw_log_service.py --host 0.0.0.0 --data-dir tmp/dashboard_demo`.
4. Open port 8765 from the Ports panel and keep visibility **Private**.
5. Try the included synthetic Apache sample before approved operational data.

The wider bind is for a private development container. The app does not implement production authentication or authorization. Do not expose it directly as a public service.

## Feature-window integration

```bash
python model_runtime.py --input current_window.json --output prediction.json --state runtime_state.json
```

Follow the [model contract](MODEL_INTERFACE.md). Preserve state between calls and send complete five-minute windows in order. Twelve consecutive windows are required. Gaps restart history; duplicate or older windows are rejected. Model training history does not replace runtime context.

Upstream collection and scheduling are the caller's responsibility. This repository does not configure Kafka, Filebeat or a scheduler. See [raw-file API details](LIVE_DEMO.md).

## Interpret results

Anomaly percentiles measure unusualness against training history, not outage probabilities. Measurements and suggested checks support investigation, not confirmed root cause. Only Apache access exposes experimental future-error forecasts, including continuing errors. Its validation period had no positives, so thresholds are unvalidated. Other forecasts are withheld under the [release policy](MODEL_RELEASE_2_2.md). The system does not execute remediation.

## Build a package

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
python package_live_delivery.py
```

The ZIP contains runtime code, models, retained evaluation evidence, tests, examples and current documentation. Uploaded logs, state, temporary files and historical media are excluded.

## Model artifact trust

Joblib uses pickle serialization and can execute code on load. Only load bundles from verified sources you trust. Compare SHA-256 with [CHECKSUMS.txt](../models_v2/CHECKSUMS.txt). Matching hashes prove byte identity, not the safety of an untrusted source. Never load models supplied by dashboard users.

## Before a production pilot

Agree scope, time zones, collector coverage, access controls and false-alert budget with IT. Obtain reviewed incident labels and reserve untouched later validation data. Evaluate precision, recall, lead time and false alerts. Remediation needs separate approval and reversible runbooks. See the [roadmap](PROJECT_ROADMAP.md) and [incident validation plan](INCIDENT_PREDICTION_PLAN.md).
