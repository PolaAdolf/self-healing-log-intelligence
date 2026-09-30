# Model Inference Interface

## Scope

The model component receives one completed, aggregated five-minute feature
window. Log collection, parsing transport, Kafka, Filebeat, scheduling, and
storage are outside this component.

Data may arrive continuously, but inference runs only when a five-minute window
is complete. A different window duration requires a separately trained model.

## Request

```json
{
  "source_model": "apache",
  "window_start": "2026-09-08T11:00:00Z",
  "window_end": "2026-09-08T11:05:00Z",
  "window_complete": true,
  "features": {
    "apache_request_count": 200,
    "apache_2xx_count": 180,
    "apache_bytes_sent": 85000,
    "apache_4xx_count": 15,
    "apache_5xx_count": 5,
    "apache_3xx_count": 0
  }
}
```

Required source schemas are stored inside `models_v2/self_healing_v2.joblib`.
The current trained detector sources are `apache`, `iis`,
`apache_error`, and `windows_eventviewer`.

The same request contract is published as JSON Schema in
`schemas/feature_window.schema.json`. Exact feature definitions, units, and
reliability status are documented in `FEATURE_CATALOG.md`.

Every runtime request must send timestamps with `Z` or an explicit UTC offset.
For source exports that originally omitted an offset, the preparation pipeline
applies the documented assumed-UTC policy before training.

## Stateful history

Rolling features require 12 consecutive windows. `model_runtime.py` stores the
last 12 windows per source in a JSON state file. During the first 11 windows it
returns `awaiting_history`. A time gap resets that source and returns
`awaiting_history_after_gap`.

The runtime rejects incomplete, duplicate, out-of-order, non-five-minute, missing,
non-numeric, negative, or non-finite inputs.

## Response

```json
{
  "model_version": "2.1.0-development",
  "source_model": "apache",
  "time_basis": "UTC",
  "window_start": "2026-09-08 11:00:00+00:00",
  "window_end": "2026-09-08 11:05:00+00:00",
  "current_status": "within_learned_range",
  "current_anomaly_score": 84.2,
  "score_definition": "Training-history anomaly percentile; not a failure probability.",
  "evidence": ["apache_request_count=200", "apache_5xx_count=5"],
  "recommended_checks": ["Review matching server errors before considering a restart."],
  "recommended_action": "none",
  "forecast_score_5m": null,
  "forecast_status_5m": "not_available",
  "forecast_score_15m": null,
  "forecast_status_15m": "not_available"
}
```

`current_status=unusual` means the window is outside the learned historical
range. It does not prove service failure. Forecast fields remain unavailable
until a model trained on human-confirmed incident onsets passes its acceptance
gate.

## Command-line integration

```bash
python model_runtime.py \
  --input current_window.json \
  --output prediction.json \
  --state runtime_state.json
```

The calling application can invoke this command whenever a completed window is
ready. The same Python class can also be imported into an API process:

```python
from pathlib import Path
from model_runtime import SelfHealingModelRuntime

runtime = SelfHealingModelRuntime(
    Path("models_v2/self_healing_v2.joblib"),
    Path("runtime_state.json"),
)
result = runtime.predict(payload)
```
