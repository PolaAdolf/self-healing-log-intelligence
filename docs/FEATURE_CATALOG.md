# Feature Catalog and Reliability Status

This catalog documents the features available to the current five-minute model
interface. Reliability describes the supplied dataset and its documented time
and measurement semantics. It does not imply that a feature is sufficient to
identify a real incident.

## Status definitions

| Status | Meaning |
|---|---|
| Reliable | Parsed consistently, with a documented time basis and unit, and used by a trained detector. |
| Reliable with assumed UTC | The measurement parses consistently and is used by a detector; the source omitted its offset, so UTC is a documented project assumption pending owner confirmation. |
| Requires validation | The value exists, but its unit, timezone, coverage, or sample size is not sufficient for production use. |
| Excluded | Deliberately not used by the current model. |

## Apache access model

Source name: `apache`  
Time basis: UTC, converted from the offset embedded in every parsed record.  
Training history: 5,933 complete five-minute windows.

| Feature | Definition | Unit | Status |
|---|---|---|---|
| `apache_request_count` | Parsed requests in the completed window | requests/5 min | Reliable |
| `apache_2xx_count` | Responses with status 200-299 | responses/5 min | Reliable |
| `apache_3xx_count` | Responses with status 300-399 | responses/5 min | Reliable |
| `apache_4xx_count` | Responses with status 400-499 | responses/5 min | Reliable |
| `apache_5xx_count` | Responses with status 500-599 | responses/5 min | Reliable |
| `apache_bytes_sent` | Sum of response bytes reported by Apache | bytes/5 min | Reliable |

For a complete access-log window, the four status-family counts should sum to
`apache_request_count`. The runtime currently validates types, missing fields,
non-negative values, timestamps, and ordering; cross-field equality remains an
upstream data-quality responsibility.

## IIS model

Source name: `iis`  
Time basis: UTC, as defined by the W3C log format.  
Training history: 628 complete five-minute windows.

| Feature | Definition | Unit | Status |
|---|---|---|---|
| `iis_request_count` | Parsed IIS requests in the completed window | requests/5 min | Reliable |
| `iis_2xx_count` | Responses with status 200-299 | responses/5 min | Reliable |
| `iis_3xx_count` | Responses with status 300-399 | responses/5 min | Reliable |
| `iis_4xx_count` | Responses with status 400-499 | responses/5 min | Reliable |
| `iis_5xx_count` | Responses with status 500-599 | responses/5 min | Reliable |
| `iis_response_ms_max` | Maximum W3C `time-taken` in the window | milliseconds | Reliable |
| `iis_avg_response_ms` | Mean W3C `time-taken` for observations in the window | milliseconds | Reliable |

The IIS detector is trained, but its available history is much smaller than the
Apache history. Additional representative normal and incident periods are
needed before production calibration.

## Apache error-log model

Source name: `apache_error`  
Time basis: UTC assumed by project policy because the export omits an offset.  
Training history: 5,921 complete five-minute windows.

| Feature | Definition | Unit | Status |
|---|---|---|---|
| `record_count` | Parsed error-log records | records/5 min | Reliable with assumed UTC |
| `warn_count` | Records labelled `warn` | records/5 min | Reliable with assumed UTC |
| `error_count` | Records labelled `error` | records/5 min | Reliable with assumed UTC |
| `notice_count` | Records labelled `notice` | records/5 min | Reliable with assumed UTC |
| `info_count` | Records labelled `info` | records/5 min | Reliable with assumed UTC |
| `information_count` | Records labelled `information` | records/5 min | Reliable with assumed UTC |
| `warning_count` | Records labelled `warning` | records/5 min | Reliable with assumed UTC |

The counts can be scored within this source. Cross-source correlation uses the
assumed-UTC mapping and must be revalidated if the source owner supplies a
different timezone.

## Windows Event Viewer model

Source name: `windows_eventviewer`  
Time basis: UTC assumed by project policy because the export omits an offset.  
Training history: 5,938 complete five-minute windows.

The model uses the same seven event-count features listed for the Apache
error-log model. The counts use the documented assumed-UTC mapping. The attempted proxy forecast was rejected because
of excessive false alerts and no reliable test lift.

## Available but not trained

| Source | Available history | Status | Required next step |
|---|---:|---|---|
| Tomcat access | 57 complete windows | Requires validation; detector not trained | Collect substantially more representative history. |
| `application_ua_integration` | 371 complete windows | Requires validation; detector not trained | Confirm the UTC assumption and collect more history. |
| `application_ncr_search` | No sufficient complete window history | Excluded from current model | Confirm coverage and the UTC assumption; define stable aggregate features. |

## Excluded or missing features

| Feature or source | Status | Reason / requirement |
|---|---|---|
| Apache trailing response-time value | Excluded | The Apache `LogFormat` and unit were not supplied. Preserve as lineage only until documented. |
| Raw diagnostic message text | Excluded from detector | Current models use stable aggregate counts. Any text model needs redaction, vocabulary/version control, and separate evaluation. |
| CPU, memory, disk, and network metrics | Missing | No infrastructure-metric dataset was supplied. Define source, unit, timestamp, and coverage before joining. |
| Deployment/change/restart events | Missing | Required to separate operational changes from incidents and to evaluate remediation. |
| Human-confirmed incident labels | Missing | Error levels and HTTP failures are observable signals, but supervised incident prediction still requires reviewed incident start/end, affected service, severity, and root cause. |
| Ingestion timestamps/collector heartbeat | Missing | Required to distinguish delayed or missing collection from observed zero with certainty. |

## Engineered model features

For each base feature, the training and runtime pipeline also calculates
past-only rolling and lag features over consecutive windows, plus cyclical hour
features. Twelve consecutive windows are required. These engineered values are
calculated by the model and must not be sent in the request JSON.

No feature is allowed to use a future row. A gap resets the runtime history so
rolling values do not incorrectly bridge missing collection.
