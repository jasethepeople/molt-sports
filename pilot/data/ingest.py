"""Emit INGEST events: SOURCE_SNAPSHOT, SOURCE_DISCREPANCY, COVERAGE_GAP."""
from __future__ import annotations

import pathlib

import blake3
import pandas as pd


def source_snapshot_event(source_type: str, path: pathlib.Path, fetched_utc: str) -> dict:
    h = "blake3:" + blake3.blake3(path.read_bytes()).hexdigest()
    return {"kind": "INGEST.SOURCE_SNAPSHOT",
            "payload": {"source_type": source_type, "hash": h, "fetched_utc": fetched_utc}}


def coverage_gap_event(stream: str, reason: str, count: int) -> dict:
    return {"kind": "INGEST.COVERAGE_GAP",
            "payload": {"stream": stream, "reason": reason, "count": count}}


def source_discrepancy_event(stream: str, fact: str, a: str, b: str) -> dict:
    return {"kind": "INGEST.SOURCE_DISCREPANCY",
            "payload": {"stream": stream, "fact": fact, "a_hash": a, "b_hash": b}}
