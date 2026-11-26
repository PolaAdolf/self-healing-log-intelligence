# Incident Prediction Foundation and Validation Plan

## Purpose

The current delivered model detects unusual behavior in the present window.
Incident prediction is a separate supervised task: estimate whether a new,
confirmed incident will begin within the next 5 or 15 minutes.

Synthetic incident labels may be used to build and test the pipeline. They must
never be reported as evidence of real predictive performance.

## Standard label contract

Incident labels must follow `schemas/incident_label.schema.json`. Each record
contains:

- a unique incident ID;
- `label_status`: `confirmed`, `rejected`, `uncertain`, or `synthetic`;
- UTC start and end timestamps;
- affected service;
- severity;
- root cause when known;
- affected source models;
- evidence references and review metadata.

Only `confirmed` labels may be used for final production validation. `synthetic`
labels are allowed only for pipeline tests. `uncertain` and `rejected` labels
must be excluded from positive training targets.

## Controlled synthetic phase

The synthetic phase should verify engineering behavior, not model accuracy:

1. Create deterministic incident episodes with known start and end times.
2. Join them to completed five-minute feature windows using UTC.
3. Mark windows where an incident is already active.
4. Create separate targets for a new incident onset within 5 and 15 minutes.
5. Exclude active-incident windows from onset prediction.
6. Verify target boundaries around every synthetic onset with automated tests.
7. Train a simple baseline and one candidate model to exercise the pipeline.
8. Report every metric as `synthetic_pipeline_validation`, never production
   performance.

The examples in `examples/dummy_incidents.json` are deliberately synthetic and
exist only to test schema validation and target construction.

## Leakage-safe target definition

For a completed feature window ending at time `t`:

- 5-minute target: 1 when a new incident starts in `(t, t + 5 minutes]`;
- 15-minute target: 1 when a new incident starts in `(t, t + 15 minutes]`;
- target: 0 when no new incident starts in that horizon;
- exclude the row when an incident is already active at `t`;
- exclude a row when its horizon crosses a train/validation/test boundary.

Features must be available by `t`. Rolling features may use only windows ending
at or before `t`.

## Development evaluation

Use chronological splits, never random row splits:

```text
earliest period -> training
middle period   -> validation and threshold selection
latest period   -> development test
future approved period -> final untouched test
```

Report:

- PR-AUC and positive-label prevalence;
- incident-level recall and precision;
- false alert windows per day;
- median and distribution of warning lead time;
- missed incident count;
- results by affected service and severity.

ROC AUC alone is not sufficient for rare incidents.

## Acceptance gates

A forecast remains unavailable unless all of these conditions are met:

1. Labels are human-confirmed for final evaluation.
2. Feature and label timestamps are normalized to verified UTC.
3. The final period was not used for feature, model, or threshold selection.
4. PR-AUC exceeds the positive-label prevalence baseline.
5. False alerts per day are within an agreed operational limit.
6. Incident-level recall and lead time are operationally useful.
7. Performance is reported separately by service and severity.
8. Drift, monitoring, rollback, and model-version ownership are documented.

## Transition to approved historical data

When approved labels become available:

1. Validate them against the incident schema.
2. Resolve duplicates, overlaps, timezone ambiguity, and uncertain episodes.
3. Replace synthetic labels; do not combine synthetic positives with final
   evaluation labels.
4. Rebuild targets and chronological splits.
5. Retrain and select thresholds using training/validation periods only.
6. Evaluate once on the untouched later period.
7. Update the model card with label provenance, metrics, limitations, and
   acceptance status.
