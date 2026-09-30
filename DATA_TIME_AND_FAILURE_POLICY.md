# Data Time and Failure-Signal Policy

## Timestamp normalization

All model windows use UTC.

| Source | Timestamp evidence | Applied rule | Audit status |
|---|---|---|---|
| Apache access | Every parsed record contains an offset such as `+0300` | Convert the represented instant to UTC | `verified_from_record` |
| Tomcat access | Every parsed record contains an offset | Convert the represented instant to UTC | `verified_from_record` |
| IIS W3C | W3C log timestamps are UTC | Parse directly as UTC | `verified_by_format` |
| Apache error | No offset in the supplied text | Interpret the displayed timestamp as UTC | `assumed_utc_by_project_policy` |
| Windows Event Viewer CSV | No offset in the supplied export | Interpret the displayed timestamp as UTC | `assumed_utc_by_project_policy` |
| Application logs | No offset in the supplied text | Interpret the displayed timestamp as UTC | `assumed_utc_by_project_policy` |

The assumed-UTC rows are usable in the current prototype because this is the
integration policy selected for the project. The assumption is kept in the
prepared CSV, record lineage, source profile, and quality report. If IT later
confirms a different source timezone, the raw data must be rebuilt and the
models retrained; changing only the runtime timestamp would be incorrect.

## What the supplied data proves

The logs contain direct failure and degradation signals:

- Apache, IIS, and Tomcat access records include HTTP status families. HTTP
  `5xx` is a server-side failure response and `4xx` is a client/request failure
  response.
- Apache error logs include severity levels such as `WARN` and `ERROR`.
- Application logs include `WARN`, `ERROR`, connection-refused, and service
  stop/start messages.
- Windows Event Viewer includes `Error`, `Warning`, source, Event ID, and
  message fields.

These fields are valid model features and operational evidence. They make a
current abnormal or failure-heavy window observable.

## What the supplied data does not prove

The archive does not contain one reviewed incident table that states, for each
incident, its confirmed start and end, affected service, severity, root cause,
and reviewer. A `5xx` response or an `Error` event can occur without a declared
production incident, and one incident can generate many such records.

Therefore:

- the current Isolation Forest models detect unusual current behavior;
- the anomaly score is a percentile against training history, not a failure
  probability;
- error and failure fields can explain an anomaly;
- production incident prediction still needs approved incident labels and an
  untouched later evaluation period.

The dummy incident file is only for validating the future target-building
pipeline. It must not be reported as evidence of predictive performance.
