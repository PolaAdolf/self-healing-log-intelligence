# Dataset and Model Inventory

## Supplied data coverage

The IT dataset contained more than Apache access and IIS logs. Parser version
2.1 processed 754,369 of 754,381 records (99.9984%). The sources are kept
separate when their feature meaning differs.

| Source family | Parsed records | Time basis | Complete model windows | Detector status |
|---|---:|---|---:|---|
| Apache access | 514,284 | UTC from embedded `+0300` offset | 5,933 | Trained |
| Apache error log | 12,801 | UTC assumed by project policy | 5,921 | Trained |
| IIS W3C access | 177,080 | UTC by W3C format | 628 | Trained |
| Tomcat access | 18,597 | UTC from embedded offset | 57 | Not trained: insufficient history |
| Application logs (`ua_integration`) | 40 | UTC assumed by project policy | 371 | Not trained: insufficient history |
| Application logs (`ncr_search`) | 36 | UTC assumed by project policy | Insufficient complete history | Not trained |
| Windows Event Viewer | 31,531 | UTC assumed by project policy | 5,938 | Trained |
| **Total** | **754,369** | UTC verified or explicitly assumed | - | Four detectors trained |

Record counts and five-minute window counts are different measures. Sparse
event sources can cover long time intervals containing complete zero-event
windows, while dense sources can contain many records inside one window.

## Where each source is stored

### UTC-safe feature table

`outputs_v2/known_utc_5min_features.csv` contains the prepared five-minute
features for:

- Apache access;
- IIS W3C access;
- Tomcat access.

The table keeps source-specific coverage and completeness flags. Missing source
coverage remains missing and is not converted to a false zero.

### Assumed-UTC feature table

`outputs_v2/assumed_utc_5min_features.csv` contains separate source
timelines for:

- Apache error logs;
- Windows Event Viewer;
- `ua_integration` application logs;
- `ncr_search` application logs where available.

Their exports omit an offset. The project policy interprets the displayed
timestamps as UTC and marks each row `assumed_utc_by_project_policy` so the
assumption stays visible and can be revised later.

### Audit and data-quality files

- `outputs_v2/source_profile_v2.csv`: every input file, parse counts, date
  coverage, and time-basis decision.
- `outputs_v2/data_quality_report.md`: parsing, timezone, missingness, and
  measurement limitations.
- `outputs_v2/parsed_record_index.csv.gz`: record-level source and timestamp
  lineage.
- `outputs_v2/diagnostic_records.csv.gz`: retained diagnostic/event records.
- `outputs_v2/parse_failures.csv.gz`: the 12 auditable parse failures.

### Training and scoring evidence

- `outputs_v2/v2_model_inventory.csv`: window count and training status for
  every candidate source.
- `outputs_v2/v2_development_metrics.csv`: rejected proxy-forecast results.
- `outputs_v2/v2_scored_windows.csv`: development anomaly scores.
- `outputs_v2/latest_system_assessment.json`: example combined assessment.
- `models_v2/self_healing_v2.joblib`: the four trained detector packages.
- `models_v2/model_card.json`: model version, accepted/rejected capabilities,
  score meaning, and production limitation.

## Why there is no single model for all data

The project deliberately uses source-specific detectors:

1. The sources have different feature meanings and volumes.
2. Apache access and IIS provide a verified UTC mapping. Apache error,
   application, and Event Viewer use the explicit assumed-UTC policy.
3. Tomcat and application sources do not have enough complete history for a
   defensible detector.
4. No source contains human-confirmed incident labels, so the current models
   detect present anomalies and do not claim real incident prediction.

The default live demo uses Apache, and `--source iis` demonstrates IIS. This is
a presentation choice and does not mean that the other supplied sources were
ignored. Apache error and Windows Event Viewer detectors are also present in
the model bundle. Their UTC mapping is an assumption to confirm with IT before
production validation.

## Raw logs in the delivery package

The shareable ZIP excludes the original raw logs and the local virtual
environment. It includes the prepared aggregate feature tables, data-quality
evidence, model inventory, model bundle, code, tests, and examples. The original
raw archive remains only in the local development workspace.
