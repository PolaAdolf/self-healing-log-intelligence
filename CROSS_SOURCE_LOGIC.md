# Evidence-based cross-source correlation

## Identity comes before joining

A source type is not a machine or service identity. Confirm which host/service
produced each file, and whether Apache proxies to IIS/Tomcat or shares a host
with the Event Viewer export. The current request schema has no asset identity;
mixing unrelated hosts into one source model is unsupported. A production
contract needs `host_id`, `service_id`, `source_instance_id`, and an approved
dependency map before cross-source predictions can be interpreted operationally.

## Time and availability

Join only matching five-minute UTC intervals for known related entities. Keep
the assumed-UTC provenance on sources whose records omit offsets. Source-owner
confirmation is particularly important for temporal correlation: normalizing an
assumed timezone does not establish that two clocks represent the same instant.
Do not choose a timezone shift merely because it maximizes correlation.

Use a separate coverage indicator. Missing delivery, an observed zero count,
and a failed host are different states. Heartbeats, ingestion timestamps, and
active health probes are not present in the current archive.

| Observations | Defensible interpretation |
|---|---|
| Related backend reports a stop/error; frontend 5xx rises afterward | Candidate dependency failure requiring repeated evidence and validation |
| HTTP logs stop; collector heartbeat is missing | Loss of visibility; host health unknown |
| No requests; collector is healthy and reports complete empty windows | Observed idle traffic; not proof of downtime |
| HTTP traffic stops; an independent health probe fails | Suspected availability failure, supported by the probe |
| Same-time failures from sources without confirmed relationship | Timing association only |

## Model comparison

After identity and clock assumptions are confirmed, compare a single-source
predictor with a joined predictor on the same chronological test windows. Inputs
can include current/past backend error counts, frontend error rates, latency,
recent changes, collector coverage, and time since last received record.
Only information available at prediction time is eligible. Same-window failures
can support diagnosis; they do not prove advance warning.

Keep an untouched later period for the final comparison. Measure precision,
recall, false alerts, and advance warning time. Report whether the additional
source actually improves the result; do not promise a higher score just from
adding more features. Keep repeated windows from the same incident in mind.

## Available exploratory evidence

Run `python cross_source_review.py` to produce
`outputs_v2/cross_source_review.json`. It reports aligned coverage, joint failure
windows, and target error rates with and without source errors, both in the same
window and one window later. It uses only complete source windows and preserves
the existing UTC policy. This is an exploratory full-archive report, not proof
of topology, causality, downtime, or predictive improvement.
