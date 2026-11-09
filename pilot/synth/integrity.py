"""Pilot provenance integrity. Refuse to score unless the frames are provably
identical to what the pilot saw.

A false PASS is worse than a FAIL. This module exists so that the scoring
report can say "PASS" and mean it, because the scorer proved it evaluated the
same bytes the pilot did.

No bypass. No --force flag. If the frames don't match, delete the report and
re-run the pilot.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

import blake3
import pandas as pd

FLOAT_PRECISION = 10
SEP_COL = "\x1f"
SEP_ROW = "\x1e"
EXIT_INTEGRITY = 4


class IntegrityError(RuntimeError):
    """Raised on hard failures. Scorer must exit without scoring."""


@dataclass(frozen=True)
class IntegrityReport:
    ok: bool
    hold_df_match: bool
    pandas_match: bool
    scenarios_checked: int
    scenarios_failed: list[str] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


def frame_hash(df: pd.DataFrame) -> str:
    """Canonical, deterministic hash of a DataFrame.

    Strategy:
      1. Sort columns alphabetically (schema change → different hash, on purpose)
      2. Canonicalize floats to fixed precision (immune to BLAS drift)
      3. Sort rows by all columns (immune to concat order)
      4. Row-wise canonical serialization + hash

    Deterministic across runs. Deterministic across pandas versions on the
    same machine. NOT guaranteed across pandas versions — the version is stored
    separately so drift is surfaced, not hidden.
    """
    if df is None or df.empty:
        return "blake3:" + blake3.blake3(b"EMPTY").hexdigest()

    cols = sorted(df.columns.astype(str))
    ordered = df[cols].copy()

    for c in ordered.columns:
        s = ordered[c]
        if pd.api.types.is_float_dtype(s):
            ordered[c] = s.map(
                lambda v: "nan" if pd.isna(v) else f"{float(v):.{FLOAT_PRECISION}f}"
            )
        elif pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s):
            ordered[c] = s.astype(str).where(s.notna(), "nan")

    ordered = ordered.sort_values(by=cols, kind="mergesort").reset_index(drop=True)
    rows = ordered.astype(str).agg(SEP_COL.join, axis=1)
    stream = (SEP_ROW.join(rows) + SEP_ROW + SEP_COL.join(cols)).encode()
    return "blake3:" + blake3.blake3(stream).hexdigest()


def verify_report_integrity(
    report_path: pathlib.Path,
    hold_df: pd.DataFrame,
    label_dir: pathlib.Path,
    inject_fn=None,
    series_hold_df: pd.DataFrame | None = None,
) -> IntegrityReport:
    """Verify the pilot report can be honestly scored against regenerated data.

    Hard fails (raises IntegrityError):
      - report missing or predates provenance tracking
      - hold_df_hash mismatch (the root check)
      - series_hold_df_hash mismatch, when the report records one
      - any scenario's frame_hash or label_hash mismatch

    Soft warns (returns in IntegrityReport):
      - pandas/numpy version drift

    Scenarios tagged "frame": "series" in the report are re-injected from
    series_hold_df; all others from hold_df. Reports predating the frame tag
    verify exactly as before (every scenario from hold_df).
    """
    if not report_path.exists():
        raise IntegrityError(f"missing pilot report: {report_path}")

    report = json.loads(report_path.read_text())
    diagnostics: dict = {}

    # ---- Check 0: report provenance fields present? ----
    if "hold_df_hash" not in report:
        raise IntegrityError(
            "pilot report predates provenance tracking.\n"
            "Re-run run.py with the current code before scoring."
        )

    # ---- Check 1: ROOT — hold_df hash ----
    actual_hold = frame_hash(hold_df)
    expected_hold = report["hold_df_hash"]
    hold_match = actual_hold == expected_hold
    diagnostics["hold_df"] = {
        "expected": expected_hold,
        "actual": actual_hold,
        "match": hold_match,
    }
    if not hold_match:
        n_expected = report.get("n_holdout_rows", "?")
        n_actual = int(len(hold_df))
        raise IntegrityError(
            "HOLDOUT FRAME CHANGED SINCE PILOT RAN.\n"
            f"  expected hash: {expected_hold}  ({n_expected} rows)\n"
            f"  actual hash:   {actual_hold}  ({n_actual} rows)\n"
            "\n"
            "Likely causes, in order of probability:\n"
            "  1. data/cache/*.parquet was regenerated (re-run run.py to resync)\n"
            "  2. upstream source changed (check INGEST.SOURCE_REVISION events)\n"
            "  3. canonical.py transformation changed (bump spec version)\n"
            "  4. different pandas/numpy version\n"
            f"  pandas expected={report.get('pandas_version')} actual={pd.__version__}\n"
            "\n"
            "Refusing to score. Delete out/pilot_report.json and re-run the pilot,\n"
            "or investigate why the data changed."
        )

    # ---- Check 1b: ROOT — series holdout frame, when the report records one ----
    if "series_hold_df_hash" in report:
        if series_hold_df is None:
            raise IntegrityError(
                "pilot report records series scenarios (series_hold_df_hash present)\n"
                "but no series holdout frame was supplied for verification.\n"
                "Re-run the scorer with the current code."
            )
        actual_series = frame_hash(series_hold_df)
        expected_series = report["series_hold_df_hash"]
        series_match = actual_series == expected_series
        diagnostics["series_hold_df"] = {
            "expected": expected_series,
            "actual": actual_series,
            "match": series_match,
        }
        if not series_match:
            n_expected = report.get("n_series_holdout_rows", "?")
            n_actual = int(len(series_hold_df))
            raise IntegrityError(
                "SERIES HOLDOUT FRAME CHANGED SINCE PILOT RAN.\n"
                f"  expected hash: {expected_series}  ({n_expected} rows)\n"
                f"  actual hash:   {actual_series}  ({n_actual} rows)\n"
                "\n"
                "Likely causes, in order of probability:\n"
                "  1. data/cache/*.parquet was regenerated (re-run run.py to resync)\n"
                "  2. upstream source changed (check INGEST.SOURCE_REVISION events)\n"
                "  3. canonical.py transformation changed (bump spec version)\n"
                "  4. different pandas/numpy version\n"
                f"  pandas expected={report.get('pandas_version')} actual={pd.__version__}\n"
                "\n"
                "Refusing to score. Delete out/pilot_report.json and re-run the pilot,\n"
                "or investigate why the data changed."
            )

    # ---- Check 2: environment drift (soft) ----
    actual_pandas = pd.__version__
    expected_pandas = report.get("pandas_version")
    pandas_match = actual_pandas == expected_pandas
    diagnostics["environment"] = {
        "pandas_expected": expected_pandas,
        "pandas_actual": actual_pandas,
        "pandas_match": pandas_match,
    }

    # ---- Check 3: per-scenario frame + label ----
    if inject_fn is None:
        from synth.inject import inject as inject_fn  # type: ignore

    scenarios_failed: list[str] = []
    scenarios_checked = 0
    scen_diag: dict = {}

    for scenario, stored in report.get("injections", {}).items():
        if "frame_hash" not in stored or "label_hash" not in stored:
            raise IntegrityError(
                f"scenario {scenario}: pilot report missing frame_hash/label_hash.\n"
                "Re-run run.py with current code."
            )
        seed = int(stored.get("seed") or _default_seed(scenario))
        if stored.get("frame") == "series":
            if series_hold_df is None:
                raise IntegrityError(
                    f"scenario {scenario}: tagged frame=series but no series "
                    "holdout frame was supplied for verification."
                )
            frame_df = series_hold_df
        else:
            frame_df = hold_df
        try:
            inj_df, label_hash = inject_fn(frame_df, scenario, seed=seed)
        except Exception as e:
            raise IntegrityError(
                f"scenario {scenario}: reinjection failed with seed={seed}: {e}"
            )

        actual_frame = frame_hash(inj_df)
        if actual_frame != stored["frame_hash"]:
            scenarios_failed.append(scenario)
            scen_diag[scenario] = {
                "reason": "frame_hash mismatch",
                "frame_expected": stored["frame_hash"],
                "frame_actual": actual_frame,
            }
            continue

        if label_hash != stored["label_hash"]:
            scenarios_failed.append(scenario)
            scen_diag[scenario] = {
                "reason": "label_hash mismatch",
                "label_expected": stored["label_hash"],
                "label_actual": label_hash,
            }
            continue

        scenarios_checked += 1

    if scen_diag:
        diagnostics["scenarios"] = scen_diag

    if scenarios_failed:
        raise IntegrityError(
            "INJECTION SCENARIOS DO NOT REPRODUCE.\n"
            f"  failed: {scenarios_failed}\n"
            f"  checked: {scenarios_checked + len(scenarios_failed)}\n"
            "\n"
            "Root hold_df hash matched, so the underlying data is the same.\n"
            "That means inject() is non-deterministic, or a seed was lost.\n"
            "\n"
            "Diagnostics:\n" + json.dumps(diagnostics, indent=2)
        )

    return IntegrityReport(
        ok=True,
        hold_df_match=hold_match,
        pandas_match=pandas_match,
        scenarios_checked=scenarios_checked,
        scenarios_failed=scenarios_failed,
        diagnostics=diagnostics,
    )


def _default_seed(scenario: str) -> int:
    """Mirror run.py's seeds if the report didn't store them."""
    return 200 if scenario in ("T-EXTENSION", "T-DEAD") else 100
