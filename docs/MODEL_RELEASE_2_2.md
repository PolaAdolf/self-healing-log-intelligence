# Model release 2.2

The dashboard, feature-window CLI, and archive scorer use the same release policy. They score a completed five-minute window after 12 consecutive complete windows from that source. A gap restarts the count. Each detector was refitted with training windows that meet that same history requirement.

| Source | Eligible training windows | Archived review flags, previous → 2.2 | Forecasts at 5 and 15 minutes |
| --- | ---: | ---: | --- |
| Apache access | 3,548 | 30 → 30 of 1,176 | Experimental preview. Archive test ranking exceeded persistence at both horizons. The validation period had zero positive windows. |
| Apache error | 3,541 | 12 → 11 of 1,174 | Withheld. The archive test had only 2 and 6 positive windows. |
| IIS W3C | 354 | 0 → 0 of 104 | Withheld. The archive test had zero positive windows. |
| Windows Event Viewer | 3,551 | 147 → 122 of 1,188 | Withheld. The forecast ranked below persistence on the original archive test. A later workstation check also produced many false alerts at the saved thresholds. |

The [machine-readable audit](../outputs_v2/detector_v22_audit.json) records the counts. The detector comparison scores the same eligible windows in the last 20% of each archive timeline. Review flag counts show review workload. The archive has no reviewed anomaly labels to tell us which flags were correct. Tomcat and the application logs still have insufficient training history for a detector.

The preview rule requires at least 20 positive test windows and higher average precision than the persistence baseline for the source and horizon. This is a conservative rule for showing a prototype score using previously reviewed archive results. Production use needs independent validation on later data, service-level coverage checks, and an agreed false alert budget.

In the independent Windows workstation check, the 15-minute System forecast caught 41 of 87 positive windows with 262 false alerts. It predicts a future recorded error. Confirmed incident onset requires approved labels with start time, affected service and severity.

## Reproduce

```bash
python train_v2_models.py --models tmp/retrain/models --output tmp/retrain/metrics
python run_model_demo.py --source apache
python run_model_demo.py --source apache_error
python run_model_demo.py --source iis
python run_model_demo.py --source windows_eventviewer
python -m unittest discover -s tests -v
```

For forecast comparison, see [MODEL_EVALUATION.md](MODEL_EVALUATION.md). The old recorded demos and PDF describe the prior prototype. Use the final presentation and the current dashboard when presenting release 2.2.
