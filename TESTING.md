# Testing and Presentation Guide

For the original-log upload dashboard, use [LIVE_DEMO.md](LIVE_DEMO.md).
The complete suite now contains **17 tests**, including future-failure labels,
missing future coverage, history resets, and raw-file parsing. The older
12-test summaries below describe the original anomaly-only delivery.

This guide shows how to verify the project from a clean environment and how to
demonstrate the same file interface that an upstream production system would
use.

## What is being tested

The repository owns the model component only. The tests verify:

- timestamp and unit handling in the corrected data builder;
- preservation of missing data instead of replacing it with false zeros;
- validation of completed five-minute request windows;
- persistent 12-window history and gap handling;
- leakage-safe feature engineering;
- bounded, monotonic anomaly percentile scoring;
- loading the saved model and processing separate request files through the
  command-line interface.

Log collection, Kafka, Filebeat, scheduling, and raw-log aggregation are outside
this component.

## Clean-environment setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows PowerShell, activate with:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Automated test suite

Run:

```bash
python -W error::DeprecationWarning -m unittest discover -s tests -v
```

Expected summary:

```text
Ran 12 tests
OK
```

Any `FAILED` or `ERROR` result must be resolved before the presentation.

The suite includes incident-target boundary tests. These verify that targets use
future onset times only and that windows with an already active incident are
excluded from onset prediction.

## Production-like file-flow test

Run:

```bash
python run_model_demo.py
```

The demo performs these steps automatically:

1. Selects 12 complete, consecutive Apache windows from the prepared dataset.
2. Writes each window as a separate JSON request file.
3. Sends every file to one persistent model runtime, as a service would.
4. Reuses one persistent state file across all 12 requests.
5. Reads each response file and prints the status.
6. Deletes the temporary test directory after completion.

Expected state sequence:

```text
01-11: awaiting_history
12: within_learned_range or unusual
```

The current bundled Apache demo returns:

```text
source_model: apache
current_status: within_learned_range
current_anomaly_score: 81.09
recommended_action: none
forecast_status_5m: not_available
forecast_status_15m: not_available
```

Run the IIS version with:

```bash
python run_model_demo.py --source iis
```

The current bundled IIS demo returns a `within_learned_range` status and an
anomaly score of 55.59.

The other trained detectors use the same 12-window flow:

```bash
python run_model_demo.py --source apache_error
python run_model_demo.py --source windows_eventviewer
```

Their request timestamps are UTC. The supplied exports omitted an offset, so
the preparation pipeline applied the documented `assumed_utc_by_project_policy`
rule before training.

The exact one-process-per-file CLI path is also available. It is slower because
it reloads the model for every window:

```bash
python run_model_demo.py --mode cli
```

## Manual one-file test

Copy an example to the repository root:

```powershell
Copy-Item examples\apache_window.json current_window.json
```

Then run:

```bash
python model_runtime.py \
  --input current_window.json \
  --output prediction.json \
  --state runtime_state.json
```

The first valid file returns `awaiting_history` with
`history_windows: 1`. Send another 11 consecutive windows, reusing the same
state file, to obtain an anomaly assessment.

## Invalid-input demonstration

Change `window_complete` to `false` and run the same command with a new state
filename. The output should contain:

```json
{
  "model_version": "2.1.0-development",
  "current_status": "invalid_input",
  "error": "window_complete must be true before inference"
}
```

This demonstrates that incomplete aggregation windows are rejected before
scoring.

## Result interpretation

- `within_learned_range`: behavior is within the learned historical range.
- `unusual`: behavior is outside the learned range and needs operator review.
- `awaiting_history`: fewer than 12 consecutive windows are available.
- `awaiting_history_after_gap`: a missing interval reset that source's history.
- `invalid_input`: the request violated the model contract.
- `model_not_available`: there is no trained detector for the source name.

The anomaly score is a historical percentile, not a failure probability.
Forecast fields are unavailable because no future-risk model passed the
development acceptance gate.

## Suggested presentation script

> We first run the automated suite to validate time handling, missingness,
> request validation, stateful history, leakage prevention, and anomaly scoring.
> We then run a production-like smoke test. Twelve separate five-minute JSON
> files are passed to the same command-line interface that an upstream system
> would call. The first eleven files build one hour of history. The twelfth file
> returns the current anomaly status, a 0-100 historical anomaly percentile,
> supporting evidence, and recommended operator checks. The score is not a
> failure probability. Future-incident prediction remains unavailable until a
> model trained on confirmed incidents passes the acceptance criteria.

## Troubleshooting

- `ModuleNotFoundError`: activate the virtual environment and install
  `requirements.txt`.
- `Model bundle was not found`: run the command from the repository root and
  confirm `models_v2/self_healing_v2.joblib` exists.
- `No sequence of 12 complete consecutive windows`: confirm the prepared CSV
  files in `outputs_v2` have not been modified.
- `Duplicate or out-of-order window`: use a new state file for a new test or
  continue with the next exact five-minute timestamp.
