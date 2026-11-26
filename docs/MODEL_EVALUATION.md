# Forecast model review

The dashboard uses the existing source-specific Isolation Forest bundles for current anomaly detection and a separate bundle for experimental forecasts of future recorded errors. This review evaluates the forecast bundle against the same archive and target used in the previous evaluation.

## Experiment

The candidate set included logistic regression, the existing random forest, a shallower random forest and histogram gradient boosting. Candidates were ranked by average precision on the chronological validation period when it contained enough positive and negative windows. When that period lacked both classes, the experiment tried expanding folds inside the training portion. Target windows reaching into the next fold were excluded. Where no fold qualified, the fixed random forest remained the fallback. The final test period was reserved for reporting within this experiment. It had already been examined in the previous evaluation.

| Source | Horizon | Existing model AP | Selected candidate AP | Persistence AP |
| --- | ---: | ---: | ---: | ---: |
| Apache access | 5 min | 96.33% | 96.33% | 91.46% |
| Apache access | 15 min | 90.70% | 90.70% | 87.07% |
| Apache error | 5 min | 0.91% | 0.91% | 0.17% |
| Apache error | 15 min | 2.11% | 2.11% | 0.51% |
| Windows Event Viewer | 5 min | 4.08% | 3.93% | 5.56% |
| Windows Event Viewer | 15 min | 11.80% | 11.51% | 16.54% |

Average precision (AP) measures how well the model ranks windows containing future recorded errors. IIS had no positives in the test period, so its AP could not be calculated. The experiment did not show an improvement that justified replacing the current bundle. Keep the forecasts experimental. Confirmed incident prediction requires approved onset labels and a later evaluation period with representative incidents and normal operation.

## Reproduce

From the repository root after installing the project requirements:

```bash
python failure_prediction.py --compare-candidates --models tmp/forecast_candidate.joblib --report tmp/forecast_candidate_report.json
```

The report includes candidate AP in validation, test AP, precision, recall, F1, false alerts and the persistence baseline. Compare it with [the existing forecast report](../outputs_v2/failure_prediction_report.json).
