# Corrected Data Quality Report (parser 2.1.0)

## Result

- Parsed records: **754,369 / 754,381 (99.9984%)**.
- Parse failures retained with file, record location, reason, and content hash: **12**.
- Records whose missing offset was interpreted as UTC by project policy: **44,408**.
- UTC feature windows: **5,938**.
- Assumed-UTC feature rows: **12,250**.

## Time handling

- Apache and Tomcat access timestamps contain an explicit `+0300` offset and were converted to UTC.
- IIS W3C timestamps were interpreted as UTC. IIS `time-taken` is retained in milliseconds.
- Apache error, Windows Event Viewer, and application log timestamps have no offset in their record prefix. Per the project integration policy, they are interpreted as UTC and marked `assumed_utc_by_project_policy` in every auditable output.
- Every feature row contains window start and end. The archive has no ingestion timestamp, so `data_available_at_utc` is deliberately blank.
- `*_window_complete` identifies windows fully covered by the source interval. Training and runtime assessment exclude incomplete edge windows.

## Missingness and coverage

- Counts are zero only inside a source file's observed first-to-last-record interval.
- Counts are blank outside that inferred interval. This prevents absent collection from becoming a measured zero.
- `*_coverage_inferred` documents the assumption. True collector heartbeat or ingestion metadata was not supplied.
- Cross-source totals use the suffix `_observed` because some sources can be unavailable in a window.

## Measurement limitations

- The trailing Apache response-time value is preserved in the lineage file as raw evidence, but excluded from model features because its unit is not documented by an Apache `LogFormat` configuration.
- No CPU, memory, deployment, change, ingestion, remediation, or SLA dataset is present.
- Earlier pseudo-label incident and forecast experiments are not independent validation.

## Output files

- `known_utc_5min_features.csv`: UTC-safe web features.
- `assumed_utc_5min_features.csv`: source timelines whose missing offsets are explicitly assumed to be UTC.
- `parsed_record_index.csv.gz`: record-level timestamp and source lineage.
- `diagnostic_records.csv.gz`: Event Viewer and application/error messages.
- `parse_failures.csv.gz`: auditable parse failures without copying raw sensitive lines.
- `source_profile_v2.csv`: per-file parsing and time-basis report.

## Gate before model retraining

Confirm the assumed-UTC policy with the source owners, obtain the Apache `LogFormat` definition, and have a human review incident onset labels. Forecasting must target a **new incident onset** and exclude rows where an incident is already active. The final score requires an untouched later period or newly collected data.
