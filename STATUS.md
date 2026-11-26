# Release 2.2 status

Development prototype. Maintainers: Pola Adolf and Youssef Atef.

## Available today

- Original-file upload and validated feature-window JSON input.
- Four source-specific Isolation Forest detectors after 12 consecutive complete five-minute windows.
- Anomaly percentiles, measured evidence and suggested operational checks.
- Apache access experimental forecasts at five and fifteen minutes. Other source forecasts are withheld.
- 18 automated tests passed in the conference preparation check on 26 November 2026. This verifies software behavior, not predictive accuracy.

## Limits

Anomaly percentiles are training-history ranks, not outage probabilities. Forecasts target future recorded errors, including continuing errors, not confirmed incident onset. Apache's validation period contained no positive windows, so thresholds are not validated. Archive test results have already been inspected and are not a fresh independent assessment.

No production accuracy, confirmed root cause or automatic remediation is claimed. UTC assumptions and inferred collection coverage require owner confirmation. A missing interval restarts the source's history; no logs alone does not prove downtime.

Business percentages are kickoff targets, not measured improvements. See [target provenance](docs/business_case_targets.md), [release evidence](docs/MODEL_RELEASE_2_2.md) and [next-phase plan](docs/INCIDENT_PREDICTION_PLAN.md).
