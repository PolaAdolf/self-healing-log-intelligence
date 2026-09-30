from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, TextIO

import numpy as np
import pandas as pd


PARSER_VERSION = "2.1.0"
ASSUMED_UTC_STATUS = "assumed_utc_by_project_policy"

APACHE_ACCESS_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^]]+)] '
    r'"(?P<method>\S+) (?P<path>.*?) (?P<protocol>HTTP/[^\"]+)" '
    r'(?P<status>\d{3}) (?P<bytes>\d+|-)'
    r'(?: \[ROUTE=(?P<route>[^]]*)] (?P<response_time>[\d.]+))?'
)
APACHE_ERROR_RE = re.compile(
    r'^\[(?P<ts>[^]]+)] \[(?P<module>[^]:]+):(?P<level>[^]]+)] '
    r'(?:\[pid [^]]+] )?(?:\[client [^]]+] )?(?P<message>.*)$'
)
APP_ISO_RE = re.compile(
    r'^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+'
    r'(?P<level>TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\b(?P<message>.*)$'
)
TOMCAT_RE = re.compile(
    r'^(?P<ts>\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+'
    r'(?P<level>TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\b(?P<message>.*)$'
)
DAEMON_RE = re.compile(
    r'^\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})] '
    r'\[(?P<level>trace|debug|info|warn|error|fatal)](?P<message>.*)$'
)

LINEAGE_FIELDS = [
    "parser_version",
    "source_family",
    "source_file",
    "record_number",
    "record_type",
    "original_timestamp",
    "timestamp_utc",
    "timestamp_local",
    "time_basis",
    "timezone_status",
    "http_status",
    "response_time_raw",
    "response_time_unit_status",
    "level",
    "event_id",
    "provider",
]
DIAGNOSTIC_FIELDS = [
    "parser_version",
    "source_family",
    "source_file",
    "record_number",
    "original_timestamp",
    "timestamp_utc",
    "timestamp_local",
    "timezone_status",
    "level",
    "event_id",
    "provider",
    "message",
]
FAILURE_FIELDS = [
    "parser_version",
    "source_family",
    "source_file",
    "record_number",
    "reason",
    "raw_sha256",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build timezone-safe, traceable log features"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("Project Logs"),
        help="Extracted Project Logs directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs_v2"),
        help="New output directory; existing exploratory outputs are untouched",
    )
    parser.add_argument(
        "--window",
        default="5min",
        help="Pandas window frequency, for example 5min",
    )
    return parser.parse_args()


def locate_project_root(path: Path) -> Path:
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Input path does not exist: {path}")
    candidates = [path] + [p for p in path.rglob("Project Logs") if p.is_dir()]
    for candidate in candidates:
        names = {p.name.lower() for p in candidate.iterdir() if p.is_dir()}
        if {"apache httpd", "iis logs", "app logs", "event viewer"} & names:
            return candidate
    raise FileNotFoundError("Could not locate the extracted Project Logs directory")


def iso_utc(value: pd.Timestamp | None) -> str:
    if value is None or pd.isna(value):
        return ""
    return value.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def iso_local(value: pd.Timestamp | None) -> str:
    if value is None or pd.isna(value):
        return ""
    if value.tzinfo is not None:
        value = value.tz_localize(None)
    return value.isoformat()


def fingerprint(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


@dataclass
class Profile:
    source_family: str
    source_file: str
    time_basis: str
    timezone_status: str
    physical_lines: int = 0
    records_seen: int = 0
    parsed_records: int = 0
    failed_records: int = 0
    continuation_lines: int = 0
    min_timestamp_utc: pd.Timestamp | None = None
    max_timestamp_utc: pd.Timestamp | None = None
    min_timestamp_local: pd.Timestamp | None = None
    max_timestamp_local: pd.Timestamp | None = None

    def success(
        self,
        timestamp_utc: pd.Timestamp | None = None,
        timestamp_local: pd.Timestamp | None = None,
    ) -> None:
        self.records_seen += 1
        self.parsed_records += 1
        if timestamp_utc is not None:
            self.min_timestamp_utc = (
                timestamp_utc
                if self.min_timestamp_utc is None
                else min(self.min_timestamp_utc, timestamp_utc)
            )
            self.max_timestamp_utc = (
                timestamp_utc
                if self.max_timestamp_utc is None
                else max(self.max_timestamp_utc, timestamp_utc)
            )
        if timestamp_local is not None:
            self.min_timestamp_local = (
                timestamp_local
                if self.min_timestamp_local is None
                else min(self.min_timestamp_local, timestamp_local)
            )
            self.max_timestamp_local = (
                timestamp_local
                if self.max_timestamp_local is None
                else max(self.max_timestamp_local, timestamp_local)
            )

    def failure(self) -> None:
        self.records_seen += 1
        self.failed_records += 1

    def row(self) -> dict:
        parse_rate = self.parsed_records / self.records_seen if self.records_seen else np.nan
        return {
            "parser_version": PARSER_VERSION,
            "source_family": self.source_family,
            "source_file": self.source_file,
            "time_basis": self.time_basis,
            "timezone_status": self.timezone_status,
            "physical_lines": self.physical_lines,
            "records_seen": self.records_seen,
            "parsed_records": self.parsed_records,
            "failed_records": self.failed_records,
            "continuation_lines": self.continuation_lines,
            "parse_rate": parse_rate,
            "min_timestamp_utc": iso_utc(self.min_timestamp_utc),
            "max_timestamp_utc": iso_utc(self.max_timestamp_utc),
            "min_timestamp_local": iso_local(self.min_timestamp_local),
            "max_timestamp_local": iso_local(self.max_timestamp_local),
        }


@dataclass
class BuildState:
    window: str
    lineage: csv.DictWriter
    diagnostics: csv.DictWriter
    failures: csv.DictWriter
    known_rows: dict[pd.Timestamp, Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    assumed_utc_rows: dict[tuple[str, pd.Timestamp], Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    coverage: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    assumed_utc_coverage: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    profiles: list[Profile] = field(default_factory=list)

    def add_known(self, ts: pd.Timestamp, name: str, value: float = 1) -> None:
        key = ts.tz_convert("UTC").floor(self.window)
        self.known_rows[key][name] += value

    def add_assumed_utc(
        self, timeline: str, ts: pd.Timestamp, name: str, value: float = 1
    ) -> None:
        key = ts.tz_convert("UTC").floor(self.window)
        self.assumed_utc_rows[(timeline, key)][name] += value


def assume_utc(value: pd.Timestamp) -> pd.Timestamp:
    """Apply the documented project policy to a timestamp without an offset."""
    if value.tzinfo is None:
        return value.tz_localize("UTC")
    return value.tz_convert("UTC")


def write_failure(
    state: BuildState,
    profile: Profile,
    record_number: int,
    reason: str,
    raw: str,
) -> None:
    profile.failure()
    state.failures.writerow(
        {
            "parser_version": PARSER_VERSION,
            "source_family": profile.source_family,
            "source_file": profile.source_file,
            "record_number": record_number,
            "reason": reason,
            "raw_sha256": fingerprint(raw),
        }
    )


def lineage_row(**values: object) -> dict:
    row = {key: "" for key in LINEAGE_FIELDS}
    row.update(values)
    row["parser_version"] = PARSER_VERSION
    return row


def diagnostic_row(**values: object) -> dict:
    row = {key: "" for key in DIAGNOSTIC_FIELDS}
    row.update(values)
    row["parser_version"] = PARSER_VERSION
    return row


def parse_apache_access(
    files: Iterable[Path], state: BuildState, root: Path, family: str
) -> None:
    source_key = family.lower()
    for path in sorted(files):
        relative = str(path.relative_to(root))
        profile = Profile(family, relative, "embedded_offset", "verified_from_record")
        file_min = None
        file_max = None
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                profile.physical_lines += 1
                match = APACHE_ACCESS_RE.match(line)
                if not match:
                    write_failure(state, profile, line_number, "format_mismatch", line)
                    continue
                try:
                    original = match["ts"]
                    aware = pd.Timestamp(
                        datetime.strptime(original, "%d/%b/%Y:%H:%M:%S %z")
                    )
                    utc = aware.tz_convert("UTC")
                    local = aware.tz_localize(None)
                    status = int(match["status"])
                    bytes_sent = 0 if match["bytes"] == "-" else int(match["bytes"])
                    raw_latency = match["response_time"] or ""
                except (TypeError, ValueError) as exc:
                    write_failure(state, profile, line_number, type(exc).__name__, line)
                    continue

                state.add_known(utc, f"{source_key}_request_count")
                state.add_known(utc, f"{source_key}_{status // 100}xx_count")
                state.add_known(utc, f"{source_key}_bytes_sent", bytes_sent)
                profile.success(utc, local)
                file_min = utc if file_min is None else min(file_min, utc)
                file_max = utc if file_max is None else max(file_max, utc)
                state.lineage.writerow(
                    lineage_row(
                        source_family=family,
                        source_file=relative,
                        record_number=line_number,
                        record_type="http_access",
                        original_timestamp=original,
                        timestamp_utc=iso_utc(utc),
                        timestamp_local=iso_local(local),
                        time_basis="embedded_offset",
                        timezone_status="verified_from_record",
                        http_status=status,
                        response_time_raw=raw_latency,
                        response_time_unit_status=(
                            "not_present" if not raw_latency else "unknown_excluded_from_features"
                        ),
                    )
                )
        if file_min is not None:
            state.coverage[source_key].append((file_min, file_max))
        state.profiles.append(profile)


def parse_iis(files: Iterable[Path], state: BuildState, root: Path) -> None:
    for path in sorted(files):
        relative = str(path.relative_to(root))
        profile = Profile("IIS", relative, "iis_w3c_utc", "verified_by_format")
        fields: list[str] | None = None
        file_min = None
        file_max = None
        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                profile.physical_lines += 1
                stripped = line.rstrip("\r\n")
                if stripped.startswith("#Fields:"):
                    fields = stripped.partition(":")[2].strip().split()
                    continue
                if not stripped or stripped.startswith("#"):
                    continue
                values = stripped.split()
                if fields is None or len(values) != len(fields):
                    write_failure(state, profile, line_number, "field_count_mismatch", line)
                    continue
                record = dict(zip(fields, values))
                try:
                    original = f"{record['date']} {record['time']}"
                    utc = pd.Timestamp(original, tz="UTC")
                    status = int(record["sc-status"])
                    latency = (
                        None
                        if record.get("time-taken", "-") == "-"
                        else float(record["time-taken"])
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    write_failure(state, profile, line_number, type(exc).__name__, line)
                    continue

                state.add_known(utc, "iis_request_count")
                state.add_known(utc, f"iis_{status // 100}xx_count")
                if latency is not None and math.isfinite(latency):
                    state.add_known(utc, "iis_response_ms_sum", latency)
                    state.add_known(utc, "iis_response_ms_observations")
                    bucket = state.known_rows[utc.floor(state.window)]
                    bucket["iis_response_ms_max"] = max(
                        bucket.get("iis_response_ms_max", 0), latency
                    )
                profile.success(utc, None)
                file_min = utc if file_min is None else min(file_min, utc)
                file_max = utc if file_max is None else max(file_max, utc)
                state.lineage.writerow(
                    lineage_row(
                        source_family="IIS",
                        source_file=relative,
                        record_number=line_number,
                        record_type="http_access",
                        original_timestamp=original,
                        timestamp_utc=iso_utc(utc),
                        time_basis="iis_w3c_utc",
                        timezone_status="verified_by_format",
                        http_status=status,
                        response_time_raw="" if latency is None else latency,
                        response_time_unit_status="verified_milliseconds",
                    )
                )
        if file_min is not None:
            state.coverage["iis"].append((file_min, file_max))
        state.profiles.append(profile)


def parse_apache_errors(files: Iterable[Path], state: BuildState, root: Path) -> None:
    timeline = "apache_error"
    for path in sorted(files):
        relative = str(path.relative_to(root))
        profile = Profile("ApacheError", relative, "assumed_utc", ASSUMED_UTC_STATUS)
        file_min = None
        file_max = None
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                profile.physical_lines += 1
                match = APACHE_ERROR_RE.match(line)
                if not match:
                    write_failure(state, profile, line_number, "format_mismatch", line)
                    continue
                try:
                    original = match["ts"]
                    local = pd.Timestamp(
                        datetime.strptime(original, "%a %b %d %H:%M:%S.%f %Y")
                    )
                    utc = assume_utc(local)
                except ValueError as exc:
                    write_failure(state, profile, line_number, type(exc).__name__, line)
                    continue
                level = match["level"].upper()
                state.add_assumed_utc(timeline, utc, "record_count")
                state.add_assumed_utc(timeline, utc, f"{level.lower()}_count")
                profile.success(utc, local)
                file_min = utc if file_min is None else min(file_min, utc)
                file_max = utc if file_max is None else max(file_max, utc)
                common = dict(
                    source_family="ApacheError",
                    source_file=relative,
                    record_number=line_number,
                    original_timestamp=original,
                    timestamp_utc=iso_utc(utc),
                    timestamp_local=iso_local(local),
                    timezone_status=ASSUMED_UTC_STATUS,
                    level=level,
                )
                state.lineage.writerow(
                    lineage_row(record_type="diagnostic", time_basis="assumed_utc", **common)
                )
                state.diagnostics.writerow(
                    diagnostic_row(message=match["message"], **common)
                )
        if file_min is not None:
            state.assumed_utc_coverage[timeline].append((file_min, file_max))
        state.profiles.append(profile)


def parse_event_csv(files: Iterable[Path], state: BuildState, root: Path) -> None:
    timeline = "windows_eventviewer"
    for path in sorted(files):
        relative = str(path.relative_to(root))
        profile = Profile("EventViewer", relative, "assumed_utc", ASSUMED_UTC_STATUS)
        file_min = None
        file_max = None
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            profile.physical_lines = reader.line_num
            normalized = [name.strip().lower() for name in header]
            for record_number, row in enumerate(reader, 2):
                profile.physical_lines = reader.line_num
                if not row:
                    continue
                if len(row) < len(normalized):
                    write_failure(
                        state, profile, record_number, "field_count_mismatch", repr(row)
                    )
                    continue
                record = dict(zip(normalized, row[: len(normalized)]))
                message = ",".join(row[len(normalized) :]) if len(row) > len(normalized) else ""
                try:
                    original = record["date and time"]
                    local = pd.to_datetime(original, errors="raise")
                    utc = assume_utc(local)
                except (KeyError, TypeError, ValueError) as exc:
                    write_failure(
                        state, profile, record_number, type(exc).__name__, repr(row)
                    )
                    continue
                level = (record.get("level") or "Unknown").strip().upper()
                provider = (record.get("source") or "").strip()
                event_id = (record.get("event id") or "").strip()
                state.add_assumed_utc(timeline, utc, "record_count")
                state.add_assumed_utc(timeline, utc, f"{level.lower()}_count")
                profile.success(utc, local)
                file_min = utc if file_min is None else min(file_min, utc)
                file_max = utc if file_max is None else max(file_max, utc)
                common = dict(
                    source_family="EventViewer",
                    source_file=relative,
                    record_number=record_number,
                    original_timestamp=original,
                    timestamp_utc=iso_utc(utc),
                    timestamp_local=iso_local(local),
                    timezone_status=ASSUMED_UTC_STATUS,
                    level=level,
                    event_id=event_id,
                    provider=provider,
                )
                state.lineage.writerow(
                    lineage_row(record_type="windows_event", time_basis="assumed_utc", **common)
                )
                state.diagnostics.writerow(diagnostic_row(message=message, **common))
        if file_min is not None:
            state.assumed_utc_coverage[timeline].append((file_min, file_max))
        state.profiles.append(profile)


def parse_application_logs(files: Iterable[Path], state: BuildState, root: Path) -> None:
    formats = (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%d-%b-%Y %H:%M:%S.%f",
    )
    for path in sorted(files):
        if path.stat().st_size == 0 or "access_log" in path.name.lower():
            continue
        relative = str(path.relative_to(root))
        service = path.parent.name.lower()
        timeline = f"application_{service}"
        profile = Profile("Application", relative, "assumed_utc", ASSUMED_UTC_STATUS)
        file_min = None
        file_max = None
        pending: dict | None = None

        def flush_pending() -> None:
            nonlocal pending
            if pending is not None:
                state.diagnostics.writerow(diagnostic_row(**pending))
                pending = None

        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                profile.physical_lines += 1
                match = APP_ISO_RE.match(line) or TOMCAT_RE.match(line) or DAEMON_RE.match(line)
                if not match:
                    if pending is not None:
                        pending["message"] += "\n" + line.rstrip("\r\n")
                        profile.continuation_lines += 1
                    elif line.strip():
                        write_failure(
                            state, profile, line_number, "orphan_continuation", line
                        )
                    continue
                flush_pending()
                original = match["ts"]
                local = None
                for fmt in formats:
                    try:
                        local = pd.Timestamp(datetime.strptime(original, fmt))
                        break
                    except ValueError:
                        continue
                if local is None:
                    write_failure(state, profile, line_number, "invalid_timestamp", line)
                    continue
                utc = assume_utc(local)
                level = match["level"].upper()
                state.add_assumed_utc(timeline, utc, "record_count")
                state.add_assumed_utc(timeline, utc, f"{level.lower()}_count")
                profile.success(utc, local)
                file_min = utc if file_min is None else min(file_min, utc)
                file_max = utc if file_max is None else max(file_max, utc)
                common = dict(
                    source_family="Application",
                    source_file=relative,
                    record_number=line_number,
                    original_timestamp=original,
                    timestamp_utc=iso_utc(utc),
                    timestamp_local=iso_local(local),
                    timezone_status=ASSUMED_UTC_STATUS,
                    level=level,
                )
                state.lineage.writerow(
                    lineage_row(record_type="application_log", time_basis="assumed_utc", **common)
                )
                pending = {
                    **common,
                    "message": match["message"].strip(),
                }
        flush_pending()
        if file_min is not None:
            state.assumed_utc_coverage[timeline].append((file_min, file_max))
        state.profiles.append(profile)


def interval_overlaps(
    start: pd.Timestamp,
    end: pd.Timestamp,
    intervals: list[tuple[pd.Timestamp, pd.Timestamp]],
) -> bool:
    return any(interval_start < end and interval_end >= start for interval_start, interval_end in intervals)


def interval_covers(
    start: pd.Timestamp,
    end: pd.Timestamp,
    intervals: list[tuple[pd.Timestamp, pd.Timestamp]],
) -> bool:
    return any(interval_start <= start and interval_end >= end for interval_start, interval_end in intervals)


def window_duration(window: str) -> pd.Timedelta:
    offset = pd.tseries.frequencies.to_offset(window)
    return pd.Timedelta(offset.nanos, unit="ns")


def export_known_features(state: BuildState, output: Path) -> pd.DataFrame:
    if not state.known_rows:
        raise RuntimeError("No UTC-normalized records were parsed")
    raw = pd.DataFrame.from_dict(state.known_rows, orient="index").sort_index()
    index = pd.date_range(raw.index.min(), raw.index.max(), freq=state.window, tz="UTC")
    raw = raw.reindex(index)
    window_delta = window_duration(state.window)
    source_columns = {
        "apache": [
            "apache_request_count",
            "apache_2xx_count",
            "apache_3xx_count",
            "apache_4xx_count",
            "apache_5xx_count",
            "apache_bytes_sent",
        ],
        "iis": [
            "iis_request_count",
            "iis_2xx_count",
            "iis_3xx_count",
            "iis_4xx_count",
            "iis_5xx_count",
            "iis_response_ms_sum",
            "iis_response_ms_observations",
            "iis_response_ms_max",
        ],
        "tomcat": [
            "tomcat_request_count",
            "tomcat_2xx_count",
            "tomcat_3xx_count",
            "tomcat_4xx_count",
            "tomcat_5xx_count",
            "tomcat_bytes_sent",
        ],
    }
    for source, columns in source_columns.items():
        coverage = pd.Series(
            [
                interval_overlaps(ts, ts + window_delta, state.coverage[source])
                for ts in index
            ],
            index=index,
        )
        raw[f"{source}_coverage_inferred"] = coverage.astype("int8")
        complete = pd.Series(
            [
                interval_covers(ts, ts + window_delta, state.coverage[source])
                for ts in index
            ],
            index=index,
        )
        raw[f"{source}_window_complete"] = complete.astype("int8")
        for column in columns:
            if column not in raw:
                raw[column] = np.nan
            raw.loc[coverage, column] = raw.loc[coverage, column].fillna(0)
            raw.loc[~coverage, column] = np.nan

    observations = raw["iis_response_ms_observations"]
    raw["iis_avg_response_ms"] = np.where(
        observations > 0, raw["iis_response_ms_sum"] / observations, np.nan
    )
    request_columns = [f"{source}_request_count" for source in source_columns]
    raw["web_request_count_observed"] = raw[request_columns].sum(axis=1, min_count=1)
    for group in ("2xx", "3xx", "4xx", "5xx"):
        columns = [f"{source}_{group}_count" for source in source_columns]
        raw[f"http_{group}_count_observed"] = raw[columns].sum(axis=1, min_count=1)
    raw["web_error_count_observed"] = raw[
        ["http_4xx_count_observed", "http_5xx_count_observed"]
    ].sum(axis=1, min_count=1)
    raw["web_error_rate_observed"] = np.where(
        raw["web_request_count_observed"] > 0,
        raw["web_error_count_observed"] / raw["web_request_count_observed"],
        np.nan,
    )
    coverage_columns = [f"{source}_coverage_inferred" for source in source_columns]
    raw["web_sources_available_count"] = raw[coverage_columns].sum(axis=1)
    raw["all_web_sources_available"] = (raw["web_sources_available_count"] == 3).astype("int8")

    result = raw.reset_index(names="window_start_utc")
    result.insert(1, "window_end_utc", result["window_start_utc"] + window_delta)
    result.insert(2, "data_available_at_utc", pd.NaT)
    result.insert(3, "availability_time_status", "not_provided_by_source")
    for column in ("window_start_utc", "window_end_utc"):
        result[column] = result[column].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    result["data_available_at_utc"] = ""
    result.to_csv(output / f"known_utc_{state.window}_features.csv", index=False)
    return result


def export_assumed_utc_features(state: BuildState, output: Path) -> pd.DataFrame:
    frames = []
    window_delta = window_duration(state.window)
    for timeline in sorted({key[0] for key in state.assumed_utc_rows}):
        timeline_rows = {
            ts: values
            for (row_timeline, ts), values in state.assumed_utc_rows.items()
            if row_timeline == timeline
        }
        raw = pd.DataFrame.from_dict(timeline_rows, orient="index").sort_index()
        index = pd.date_range(raw.index.min(), raw.index.max(), freq=state.window)
        raw = raw.reindex(index)
        coverage = pd.Series(
            [
                interval_overlaps(
                    ts, ts + window_delta, state.assumed_utc_coverage[timeline]
                )
                for ts in index
            ],
            index=index,
        )
        count_columns = [column for column in raw.columns if column.endswith("_count")]
        for column in count_columns:
            raw.loc[coverage, column] = raw.loc[coverage, column].fillna(0)
            raw.loc[~coverage, column] = np.nan
        raw["coverage_inferred"] = coverage.astype("int8")
        raw["window_complete"] = [
            int(
                interval_covers(
                    ts, ts + window_delta, state.assumed_utc_coverage[timeline]
                )
            )
            for ts in index
        ]
        raw.insert(0, "timeline", timeline)
        raw.insert(1, "window_start_utc", raw.index)
        raw.insert(2, "window_end_utc", raw.index + window_delta)
        raw.insert(3, "timezone_status", ASSUMED_UTC_STATUS)
        for column in ("window_start_utc", "window_end_utc"):
            raw[column] = raw[column].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        frames.append(raw.reset_index(drop=True))
    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    result.to_csv(output / f"assumed_utc_{state.window}_features.csv", index=False)
    return result


def write_quality_report(
    state: BuildState,
    known: pd.DataFrame,
    assumed_utc: pd.DataFrame,
    output: Path,
) -> None:
    profiles = pd.DataFrame([profile.row() for profile in state.profiles])
    profiles.to_csv(output / "source_profile_v2.csv", index=False)
    parsed = int(profiles["parsed_records"].sum())
    failed = int(profiles["failed_records"].sum())
    records = int(profiles["records_seen"].sum())
    rate = parsed / records if records else 0
    assumed_utc_records = int(
        profiles.loc[
            profiles["timezone_status"] == ASSUMED_UTC_STATUS, "parsed_records"
        ].sum()
    )
    report = f"""# Corrected Data Quality Report (parser {PARSER_VERSION})

## Result

- Parsed records: **{parsed:,} / {records:,} ({rate:.4%})**.
- Parse failures retained with file, record location, reason, and content hash: **{failed:,}**.
- Records whose missing offset was interpreted as UTC by project policy: **{assumed_utc_records:,}**.
- UTC feature windows: **{len(known):,}**.
- Assumed-UTC feature rows: **{len(assumed_utc):,}**.

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

- `known_utc_{state.window}_features.csv`: UTC-safe web features.
- `assumed_utc_{state.window}_features.csv`: source timelines whose missing offsets are explicitly assumed to be UTC.
- `parsed_record_index.csv.gz`: record-level timestamp and source lineage.
- `diagnostic_records.csv.gz`: Event Viewer and application/error messages.
- `parse_failures.csv.gz`: auditable parse failures without copying raw sensitive lines.
- `source_profile_v2.csv`: per-file parsing and time-basis report.

## Gate before model retraining

Confirm the assumed-UTC policy with the source owners, obtain the Apache `LogFormat` definition, and have a human review incident onset labels. Forecasting must target a **new incident onset** and exclude rows where an incident is already active. The final score requires an untouched later period or newly collected data.
"""
    (output / "data_quality_report.md").write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = locate_project_root(args.input)
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    lineage_path = output / "parsed_record_index.csv.gz"
    diagnostics_path = output / "diagnostic_records.csv.gz"
    failures_path = output / "parse_failures.csv.gz"
    with gzip.open(lineage_path, "wt", encoding="utf-8", newline="") as lineage_handle, gzip.open(
        diagnostics_path, "wt", encoding="utf-8", newline=""
    ) as diagnostic_handle, gzip.open(
        failures_path, "wt", encoding="utf-8", newline=""
    ) as failure_handle:
        lineage = csv.DictWriter(lineage_handle, fieldnames=LINEAGE_FIELDS)
        diagnostics = csv.DictWriter(diagnostic_handle, fieldnames=DIAGNOSTIC_FIELDS)
        failures = csv.DictWriter(failure_handle, fieldnames=FAILURE_FIELDS)
        lineage.writeheader()
        diagnostics.writeheader()
        failures.writeheader()
        state = BuildState(args.window, lineage, diagnostics, failures)

        apache = root / "Apache httpd"
        parse_apache_access(apache.glob("access.log*"), state, root, "Apache")
        parse_apache_errors(apache.glob("error.log*"), state, root)

        iis = root / "IIS Logs"
        parse_iis(iis.rglob("*.log"), state, root)

        app = root / "App Logs"
        parse_apache_access(app.rglob("*access_log*.txt"), state, root, "Tomcat")
        parse_application_logs(app.rglob("*.log"), state, root)

        events = root / "Event Viewer" / "output_sanitized"
        parse_event_csv(events.glob("*.csv"), state, root)

    known = export_known_features(state, output)
    assumed_utc = export_assumed_utc_features(state, output)
    write_quality_report(state, known, assumed_utc, output)
    print(f"Corrected dataset completed: {output}")
    print(f"UTC feature rows: {len(known):,}")
    print(f"Assumed-UTC feature rows: {len(assumed_utc):,}")
    print(f"Parsed records: {sum(p.parsed_records for p in state.profiles):,}")
    print(f"Parse failures: {sum(p.failed_records for p in state.profiles):,}")


if __name__ == "__main__":
    main()
