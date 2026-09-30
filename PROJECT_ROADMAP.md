# Project Status and Production Roadmap

## Raw-log dashboard and future-failure extension

The local dashboard now accepts original source files and computes actual
anomaly and observed-failure forecasts. A separate supervised model predicts
whether the next 5/15 minutes contain HTTP 5xx or diagnostic Error events.
These labels come directly from the supplied logs and include persistence and
recurrence. Experimental validation status is displayed per source; see
`LIVE_DEMO.md` and `outputs_v2/failure_prediction_report.json`. This extension
does not establish confirmed-incident prediction or production readiness.

## Delivered

- Corrected parser and five-minute feature builder with record lineage.
- Verified UTC handling for Apache/Tomcat access logs and IIS W3C logs.
- Documented assumed-UTC handling for source exports without an offset.
- Explicit separation between missing collection and observed zero.
- Four source-specific Isolation Forest detectors: Apache, IIS, Apache error
  log, and Windows Event Viewer.
- Stateful one-file inference interface with strict five-minute validation.
- One-hour rolling history using 12 consecutive windows per source.
- A 0-100 historical anomaly percentile, evidence, operator checks, and action.
- Automated tests for parsing, missingness, history, leakage, and scoring.
- A production-like file-flow smoke test for persistent-service and cold-start
  CLI modes.

## Current limitations

- The model version is `2.1.0-development`.
- The anomaly score is not a probability of service failure.
- An unusual window requires operator review and does not prove an incident.
- No future-risk model passed the development acceptance gate. Forecast outputs
  therefore remain `not_available`.
- The model does not execute remediation actions.
- Apache error, application, and Windows Event Viewer exports omit an offset.
  The project currently interprets them as UTC by explicit policy; source-owner
  confirmation remains a production gate.
- The trailing Apache latency field is excluded because its unit was not
  documented.

## Next phase: two parallel tracks

### Track 1 - continue the anomaly prototype

1. Keep the five-minute input contract stable and versioned.
2. Add monitored source coverage and cross-field data-quality checks.
3. Review anomaly-score thresholds against operator feedback.
4. Improve explanations so current values and rolling contributors are clearly
   separated.
5. Run shadow tests with archived inputs and outputs before any operational
   action is enabled.

### Track 2 - prepare incident prediction

1. Adopt `schemas/incident_label.schema.json` as the label contract.
2. Use `examples/dummy_incidents.json` only to test target creation, temporal
   splits, metrics, and pipeline behavior.
3. Keep all synthetic results labelled as pipeline validation, not predictive
   performance.
4. Replace synthetic labels with approved historical incidents when available.
5. Evaluate once on an untouched later period before enabling forecast output.

## Required information

1. Human-confirmed incident start and end times, affected services, severity,
   and root cause.
2. A later untouched period for final evaluation.
3. Source-owner confirmation of the assumed-UTC policy for Apache error,
   Windows Event Viewer, and application logs.
4. The Apache `LogFormat` definition and response-time unit.
5. Deployment, restart, change, and remediation timestamps.
6. Reviewed runbooks defining checks, approvals, actions, health checks, and
   rollback.

## Production acceptance gates

### Data contract

Every joined source must have a documented time basis, feature definition,
unit, missing-data rule, and ownership contact.

### Forecast labels and evaluation

Future-risk targets must use confirmed incident onsets. Final metrics must come
from an untouched later period and report event recall, precision, false alerts
per day, lead time, and missed incidents.

### Operational safety

Any consequential remediation must use a reviewed runbook, an approval or safe
policy, a post-action health check, an audit record, and a rollback path. An
anomaly score alone must never restart a service.

### Deployment readiness

The model process needs versioned configuration, structured logs, monitoring,
serialized state-file access, model and data drift checks, and a rollback plan.
The production-like smoke test in this repository validates the file contract;
it is not a substitute for shadow testing in the target environment.
