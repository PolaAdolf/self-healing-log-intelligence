# Testing and Presentation Guide

This guide matches the current package: the saved five-minute anomaly model,
the raw-log upload dashboard, and the separate experimental failure forecast.
For dashboard API details, see [LIVE_DEMO.md](LIVE_DEMO.md).

## 1. Install and run the tests

From the repository root, create and activate a virtual environment, then
install the listed dependencies:

```powershell
py -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
```

Run the automated suite:

```bash
python -m pytest tests -q
```

The suite covers parsing and timestamps, missing data, feature windows,
stateful history, future-target leakage, and model scoring.

## 2. Demonstrate the model file flow

Run:

```bash
python run_model_demo.py
```

The script sends 12 consecutive Apache five-minute windows through the saved
model while reusing one state file. The first 11 build the one-hour context; the
12th returns an anomaly result. Use `--source iis`, `--source apache_error`, or
`--source windows_eventviewer` for the other trained detectors. Add
`--mode cli` to start a fresh process for each window.

## 3. Demonstrate original raw logs in the dashboard

Start the local service:

```bash
python raw_log_service.py
```

Open **http://localhost:8765**, select a supported source, choose an extracted
original log file, then click **Upload & analyze**. The server parses the
original file, makes complete five-minute windows, and shows the calculated
anomaly history, evidence, operational checks, and any separate experimental
future-failure signals. Uploading original logs is real processing, but it does
not connect the dashboard directly to a production server.

The dashboard keeps results locally in `raw_sessions/`. Upload at least one hour
of complete consecutive history to make a current anomaly assessment available.
A missing five-minute interval resets the history. A saved historical upload can
demonstrate the process without waiting for real-time collection.

## 4. Read the results accurately

- `within_learned_range` means the current window fits the detector's learned
  range. `unusual` means an operator should review it.
- The anomaly score is a percentile of unusualness against training history. It
  is not a failure probability.
- The future 5- and 15-minute outputs concern recorded failure signals,
  including continued or recurring failures. They remain experimental and are
  not probabilities of a confirmed incident.
- The model recommends checks. It does not restart services or take automatic
  remediation actions.

## 5. Troubleshooting

- `ModuleNotFoundError`: activate the virtual environment and install
  `requirements.txt`.
- Missing model bundle: run from the repository root and confirm the files in
  `models_v2/` are present.
- Not enough history: provide at least 12 consecutive complete five-minute
  windows for that source.
- Duplicate or out-of-order window: start a fresh state file for a separate test, or send the next five-minute timestamp in order.
