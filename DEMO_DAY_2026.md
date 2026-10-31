# NBE Innovation Cycle 2026: demo day run of show

**Date:** 26 November 2026  
**Team:** Pola Adolf and Youssef Atef  
**Total stage slot:** about 10 minutes: five minutes for the idea owner, then about five minutes for the recorded solution run with student commentary.

## Files to bring

- [Five-minute idea pitch](output/presentations/NBE_Innovation_Cycle_2026_Demo_Day_5_Minute_Pitch.pptx)
- [Recorded raw-log demonstration](output/video/NBE_Innovation_Cycle_2026_Demo_Day_Full_Run.mp4)
- [Technical backup deck](output/presentations/NBE_Innovation_Cycle_2026_Model_Journey_Team_Edition.pptx)
- [Project report](output/pdf/NBE_Innovation_Cycle_2026_Self_Healing_Log_Intelligence_Report.pdf)

Download the pitch and video to the presentation laptop before arrival. Play the video as a local file. Test the display and audio output on the room equipment. Keep the music low enough for Pola and Youssef to speak while it plays.

## Part 1: idea owner, five minutes

| Time | Slide | Suggested message |
|---|---|---|
| 0:00–0:40 | 1. Opening | Operational teams receive many logs. The goal is to turn them into evidence an operator can review earlier. |
| 0:40–1:45 | 2. Challenge | The supplied archive has 754,369 parsed records in different formats. Individual errors do not give an hour-long picture, and confirmed incident labels were not supplied. |
| 1:45–2:50 | 3. Solution | The local prototype accepts original files, groups records into five-minute windows, keeps one hour of consecutive history, and shows an anomaly percentile with the measured values and suggested checks. |
| 2:50–4:10 | 4. What works | The video uses an original Apache access log. One run parsed 153,947 records, rejected one record, and built 174 complete windows. The current anomaly score is 95.45, below the unusual threshold of 98.99. The future-failure scores are experimental. |
| 4:10–5:00 | 5. Bank pilot | The next phase needs a reliable five-minute feed, confirmed incident records, and validation on later data. Hand over to the engineers for the recorded run. |

## Part 2: solution video, student commentary

The video shows one continuous Edge recording of the local dashboard using the supplied `Project Logs/Apache httpd/access.log.1` file. The browser uploads the original file, waits for the real parser and saved models, then moves through the actual results. English captions and quiet original instrumental music are included. The speakers can use these short explanations:

| Video moment | Suggested commentary |
|---|---|
| File selection and upload | “This is the supplied raw Apache log. We upload it without making a prepared feature JSON file.” |
| Processing and coverage | “The parser accepted 153,947 records, kept one rejected record for review, and formed 174 complete five-minute windows.” |
| Anomaly cards and chart | “The current anomaly percentile is 95.45. The model marks this window within its learned range because the unusual threshold is 98.99. The chart shows earlier windows too.” |
| Measured evidence | “The current window contains 300 requests: 234 successful 2xx responses, 64 client 4xx responses, and two server 5xx responses.” |
| Experimental forecast | “The displayed 5- and 15-minute values are model scores, not percentages or confirmed incident probabilities. Eleven of the previous 12 windows contained at least one 5xx response.” |
| Operational checks | “The system suggests checks for an IT operator. It does not restart a service or take an automatic repair action.” |
| Validation and closing | “This upload demonstrates real processing. A bank pilot would need confirmed incident labels and a later, independent evaluation period.” |

## Claims to keep precise

- The anomaly percentile ranks unusualness against training history. It is not the probability of failure.
- The forecast target is at least one recorded future failure signal, including continued or recurring errors. It is not a confirmed new incident.
- The historical source file can overlap model training data. This video proves the working pipeline, not independent predictive accuracy.
- Source-to-service relationships are not confirmed. Do not infer that a missing log means a server is down or that simultaneous errors prove causation.
- Operators decide whether to follow the checks. The prototype performs no automatic remediation.

## Technical questions likely to arise

**Why 12 windows?** Each window covers five minutes. Twelve consecutive windows provide one hour of recent context. On the 13th window, the model uses that window and the 11 immediately before it. A missing interval resets the history.

**Why can the five-minute signal be high when the current window has only two 5xx responses?** The model uses recent history as well as the current window. In this run, 11 of the last 12 windows contained a 5xx response, with 32 such responses in that hour. The 85.27 score is uncalibrated, so it must not be described as an 85.27% failure probability.

**Which algorithms are used?** Source-specific Isolation Forest models rank current anomalies. A separate Random Forest produces experimental future-failure scores for this Apache run. Its validation period had too few positive outcomes to support a production accuracy claim.

## Live backup

The recorded video is the planned stage demonstration. For a live backup, use the existing Ubuntu/WSL environment, whose scikit-learn version matches the saved models:

```bash
cd '/mnt/c/Users/padol/Downloads/Self_Healing_Log_EDA_Package (1)/log_eda_project'
.venv/bin/python raw_log_service.py --port 8765 --data-dir .build/demo_day/on_site_session
```

Open `http://localhost:8765`, select **Apache access**, choose `Project Logs/Apache httpd/access.log.1`, and click **Upload & analyze**. Wait for **Analysis complete**. Use a fresh data directory for a fresh demonstration. The source file is historical, and the dashboard has no live connection to the bank's production servers.
