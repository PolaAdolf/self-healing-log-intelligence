# Conference slide sources

All numbered results are descriptive archive results or a clearly marked synthetic run. Business values are unmeasured goals.

| Slide | Headline | Evidence |
| --- | --- | --- |
| 1 | Self-Healing Log Intelligence | Pola Adolf and Youssef Atef / Release 2.2 |
| 2 | Reactive support begins after business impact | Source: Self_Healing.xlsx, Sheet1 B4; illustrative sequence, no measured timings |
| 3 | Phase 1 sets four goals for a future pilot | Source: docs/business_case_targets.md; Self_Healing.xlsx B11:B15 |
| 4 | We parsed 754,369 supplied log records | Sources: outputs_v2/data_quality_report.md; DATASET_INVENTORY.md |
| 5 | Five steps turn a raw file into an operator’s answer | Sources: README.md architecture; MODEL_INTERFACE.md; raw_log_service.py |
| 6 | 99.18 crosses the source’s review threshold | Source: docs/demo_result.json; examples/apache_demo.log; synthetic current-release run |
| 7 | The live dashboard makes its evidence visible | Source: fresh 1920 × 1080 browser session; docs/images/dashboard.png; synthetic input |
| 8 | Four detectors follow the same release rules | Sources: MODEL_RELEASE_2_2.md; outputs_v2/detector_v22_audit.json |
| 9 | Apache ranks future errors above a simple baseline | Source: MODEL_EVALUATION.md; archive test already inspected; AP means average precision |
| 10 | A harder test exposed too many false alerts | Source: MODEL_RELEASE_2_2.md; 13.5% = 41 / (41 + 262), rounded |
| 11 | Today’s capabilities have clear boundaries | Sources: STATUS.md; TESTING.md; MODEL_RELEASE_2_2.md |
| 12 | A monitored pilot needs operational evidence | Sources: PROJECT_ROADMAP.md; INCIDENT_PREDICTION_PLAN.md; schemas/incident_label.schema.json |
| 13 | Thank you | Pola Adolf and Youssef Atef / NBE Innovation Cycle 2026 |
| 14 | Chronological evaluation protects the time boundary | Appendix A1 / Sources: failure_prediction.py; DATA_TIME_AND_FAILURE_POLICY.md |
| 15 | UTC conversion and UTC assumptions stay separate | Appendix A2 / Source: DATA_TIME_AND_FAILURE_POLICY.md |
| 16 | Missing evidence limits what we can conclude | Appendix A3 / Sources: STATUS.md; DATA_TIME_AND_FAILURE_POLICY.md; INCIDENT_PREDICTION_PLAN.md |

Theme fallback fonts: Georgia headings and Calibri body. All main charts, tables and process diagrams remain editable. The original final deck is preserved byte-for-byte.
