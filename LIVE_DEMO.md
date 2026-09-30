# Live raw-log dashboard

This dashboard runs actual parsing and saved-model inference when an original
log file is uploaded. It has no simulated stream, prerecorded results, dummy
records, or accelerated replay. Historical source files retain their original
event times. A live screen recording shows the real upload and computation;
it does not establish a live connection to the source servers.

## Start

Use the project's existing Python environment and installed requirements:

```bash
python raw_log_service.py
```

Open **http://localhost:8765**. Keep the terminal running during the meeting.
The server binds only to the local computer.

## Demonstrate original data

1. Select the source: Apache access, IIS W3C, Apache error, or Windows Event Viewer.
2. Choose the original extracted `.log`, rotated log, `.txt`, or `.csv` file.
   Do not convert it to feature JSON. Extract the RAR first.
3. Click **Upload & analyze**. Wait for the parsing and inference result.
4. Show parsed/rejected records, complete windows, and the timestamp policy.
5. Show the anomaly timeline, current measured evidence, and operational checks.
6. Show the separate five-minute and fifteen-minute future-failure scores.
   Explain the validation status displayed in the table.
7. Export the computed assessment if a reviewer needs the exact result.

Suggested files from the supplied archive:

| Source selection | Original file |
|---|---|
| Apache access | `Project Logs/Apache httpd/access.log.1` |
| IIS W3C | A W3C `.log` file under `Project Logs/IIS Logs` |
| Apache error | `Project Logs/Apache httpd/error.log` |
| Windows Event Viewer | `Project Logs/Event Viewer/output_sanitized/App_EventLog_Sanitized.csv` |

The upload preserves raw bytes locally. The server parses the original formats,
aggregates completed five-minute windows, and derives rolling features. The
inference models are loaded once when the server starts; uploads do not retrain
them. Training data is not modified by uploads.

## Receiving additional data

Upload the next original file when it arrives. The server retains uploaded files
per source and recomputes that source's assessment. A growing file with the same
name replaces its prior snapshot. Identical files are ignored. Distinct files
with overlapping time ranges are rejected to avoid double counting; the three
distinct supplied Windows Event Viewer channels may overlap.

The local API also accepts the raw file body, so an upstream sender can use it
without preparing feature JSON:

```bash
curl --fail --data-binary @access.log \
  -H 'Content-Type: application/octet-stream' \
  'http://localhost:8765/api/upload?source=apache&name=access.log'
curl --fail -X POST 'http://localhost:8765/api/analyze?source=apache'
curl --fail 'http://localhost:8765/api/status?source=apache'
```

The upstream sender decides when to send the next file (for example every five
minutes). This dashboard does not collect files from remote systems or run a
scheduler. Files up to 64 MB each are supported; upload separate rotations for
larger datasets. Do not expose this local development server publicly.

Raw logs do not prove collector completeness. The current parser conservatively
uses first-to-last-record coverage per file and excludes incomplete edge windows.
A just-ended window can remain unavailable until a later record establishes its
end boundary. For an actual streaming integration, IT must provide a reliable
window-close or completeness signal. Twelve consecutive complete windows are
needed; a gap resets history. Uploading an hour or more of actual historical logs
can supply that history immediately without waiting an hour or simulating time.

Data and reports are under `raw_sessions/<source>/`. Start with a different
`--data-dir` for an independent demonstration. The dashboard can display the last
saved assessment after restart, including its processing timestamp.

## What prediction means

The supervised target is **at least one recorded failure in the next five or
fifteen minutes**. For HTTP sources the target is a `5xx` response; current `4xx`
counts are input features. For diagnostic sources it is an `ERROR`/`Error` event.
This includes continued and recurring failures, not just new incident onsets.

For a prediction made at 10:00, input features use records available through
10:00. The label comes from errors recorded between 10:00 and 10:05 (or 10:15).
Those future outcomes are never given to the model as input. HTTP status is a
usable observed outcome label; no invented incident labels are used here.

The score is an uncalibrated classifier score. It is not a confirmed outage
probability. A low score does not certify service health.

## Training and honest evaluation

```bash
python failure_prediction.py
python -W error::DeprecationWarning -m unittest discover -s tests -v
```

Training uses chronological 60/20/20 splits, a complete contiguous hour of
history, and purged targets at split boundaries. Missing future windows are not
labelled as successes. Candidate selection and threshold tuning use validation
only. When validation contains too few failures, a fixed Random Forest with a
0.5 threshold is saved as experimental without claiming successful validation.
The later test period is reported without adjusting the model to that result.

`outputs_v2/failure_prediction_report.json` reports test precision, recall,
average precision, false alert windows, and a persistence baseline. In the
supplied archive, Apache's validation slice has no positive targets, IIS has no
positive targets in validation or test, and Apache error has very few positives.
Event Viewer is evaluable but the trained classifiers did not improve on the
baseline. These limitations remain visible. This is a development result on one
archive, not production certification or accuracy on independent incidents.

Models are in `models_v2/failure_prediction.joblib`. The original anomaly bundle
and legacy feature-window CLI are retained. The raw-log service combines that
anomaly detector with the separate failure-prediction bundle. The legacy CLI's
old proxy-forecast fields still remain unavailable; the new service exposes the
actual failure forecasts under `prediction`.

Tomcat and application logs remain documented in the dataset inventory. Their
history is insufficient for this training recipe, and the dashboard does not
present them as supported prediction models.
