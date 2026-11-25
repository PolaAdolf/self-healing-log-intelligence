# Conference rehearsal

Use the conference deck for release 2.2. Keep forecasts labelled experimental.

1. Install Python 3.11 or 3.12, create a virtual environment, then run `python -m pip install -r requirements-dev.txt`.
2. Run `python -m pytest tests -q`. The preparation run passed 18 tests. Test count is not model accuracy.
3. Start `python raw_log_service.py --data-dir tmp/conference_rehearsal`. Open http://localhost:8765.
4. Choose Apache access. Upload `examples/apache_demo.log`, then click **Upload & analyze**. This is a deliberately synthetic demonstration, not customer evidence or a blind accuracy test.
5. Show coverage and 12/12 consecutive windows. The file contains an hour of history; it does not require an hour of waiting.
6. Compare the displayed anomaly percentile with its source threshold. Read the current status. Explain that this is unusualness relative to training history, not the probability of an outage.
7. Show the measured HTTP status counts and suggested checks. These support an operator's investigation, not an established root cause.
8. Show the experimental Apache forecasts. They concern recorded errors, not confirmed incidents; their thresholds are not validated.
9. Export assessment. Explain that repeated identical uploads are ignored and missing intervals restart history.
10. Close with the pilot ask: confirm time zones and topology, provide reviewed incident labels, agree a limited pilot and false-alert budget.

Use `docs/demo_result.json` and `docs/images/dashboard.png` as the recorded synthetic rehearsal evidence. If the live result differs, inspect model checksum, source, input and accumulated session data. Do not alter model thresholds to match a slide.

The optional HTML opening film is an explanatory animation. Its illustrated graphs are not monitoring telemetry. Use the live dashboard for the actual product demonstration.
