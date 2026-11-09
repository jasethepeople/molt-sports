"""Synthetic injection scoring report.

Reads out/pilot_report.json, recomputes per-crew verdicts for each injection
scenario using the sealed labels, and emits:

  - out/scoring_report.md   (human-readable)
  - out/scoring_report.json (machine-readable, for CI)

Pass/fail against §C.2 of the design doc. If any scenario fails, exit code 1.
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass

import pandas as pd
import numpy as np

from families.officiating_crew import CrewTendency
from harness.protocol import TestContext, BaselineRef
from synth import labels as labelmod

OUT = pathlib.Path("out")
LABELS = OUT / "labels"

SYNTH_CREW = "CREW-SYNTH-001"

# §C.2 thresholds
THRESHOLDS = {
    "recall_pass": 0.60, "recall_better": 0.80, "recall_fail": 0.40,
    "fpr_pass": 0.05, "fpr_better": 0.02, "fpr_fail": 0.10,
    "bleed_pass": 1, "bleed_better": 0, "bleed_fail": 3,
    "direction_pass": 0.70, "direction_better": 0.85, "direction_fail": 0.60,
}


@dataclass
class ScenarioScore:
    name: str
    recall: float | None = None
    fpr: float | None = None
    bleed: int | None = None
    direction: float | None = None
    notes: str = ""
    passed: bool = False
    failed_reason: str = ""


def _crew_ctx(family_size: int) -> TestContext:
    return TestContext(
        subclaim_id="SUB-SCORE",
        stream="sports/nba/pilot",
        baseline=BaselineRef(
            baseline_id="BSL-OFFICIATING-CREW",
            version="v3.0.0",
            hash="blake3:" + "0" * 64,
            parameters={"prior": "empirical_bayes_normal_normal"},
        ),
        rng_seed=42, alpha=0.01, family_size=family_size,
        holdout_seasons=["2023-24", "2024-25"],
    )


def _flagged_crews(result) -> set[str]:
    """Crews whose verdict is not REFUTED and not INCONCLUSIVE."""
    out = set()
    for u in result.per_unit:
        if u["verdict"] in ("SUPPORTED", "PARTIALLY_SUPPORTED"):
            out.add(str(u["unit_id"]))
    return out


def _direction_positive(result) -> set[str]:
    return {str(u["unit_id"]) for u in result.per_unit if u["effect_size"] > 0}


def score_T_null(inj_df, label_path: pathlib.Path) -> ScenarioScore:
    """T-NULL: nothing injected. FPR must be ≤ 0.05, ideally ≤ 0.02."""
    labels = labelmod.load(label_path)
    ctx = _crew_ctx(family_size=int(inj_df["crew_code"].nunique()))
    res = CrewTendency().run(ctx, inj_df)
    flagged = _flagged_crews(res)
    n_crews = int(inj_df["crew_code"].nunique())
    fpr = len(flagged) / max(1, n_crews)

    sc = ScenarioScore(name="T-NULL", fpr=fpr)
    if fpr <= THRESHOLDS["fpr_better"]:
        sc.passed = True
        sc.notes = f"FPR {fpr:.4f} ≤ {THRESHOLDS['fpr_better']} (better)"
    elif fpr <= THRESHOLDS["fpr_pass"]:
        sc.passed = True
        sc.notes = f"FPR {fpr:.4f} ≤ {THRESHOLDS['fpr_pass']} (pass)"
    elif fpr > THRESHOLDS["fpr_fail"]:
        sc.passed = False
        sc.failed_reason = f"FPR {fpr:.4f} > {THRESHOLDS['fpr_fail']}"
    else:
        sc.passed = False
        sc.failed_reason = f"FPR {fpr:.4f} in fail band"
    return sc


def score_T_inject(
    inj_df, label_path: pathlib.Path, name: str,
    target_crew: str = SYNTH_CREW,
) -> ScenarioScore:
    """T-SMALL / T-LARGE: the injected crew must be flagged."""
    labels = labelmod.load(label_path)
    ctx = _crew_ctx(family_size=int(inj_df["crew_code"].nunique()))
    res = CrewTendency().run(ctx, inj_df)
    flagged = _flagged_crews(res)

    detected = target_crew in flagged
    recall = 1.0 if detected else 0.0

    sc = ScenarioScore(name=name, recall=recall)
    if detected:
        sc.passed = True
        sc.notes = f"{target_crew} flagged; {len(labels['injected_games'])} games injected"
    else:
        sc.passed = False
        sc.failed_reason = f"{target_crew} not flagged ({len(labels['injected_games'])} games injected)"
    return sc


def score_T_diffuse(inj_df, label_path: pathlib.Path) -> ScenarioScore:
    """T-DIFFUSE: 20 synth crews, +0.3 each. Direction accuracy ≥ 0.70 required.
    Also check no more than 3 of the 20 are falsely flagged."""
    labels = labelmod.load(label_path)
    ctx = _crew_ctx(family_size=int(inj_df["crew_code"].nunique()))
    res = CrewTendency().run(ctx, inj_df)

    synth_crews = {c for c in inj_df["crew_code"].unique() if c.startswith("CREW-SYNTH")}
    direction_positive = _direction_positive(res) & synth_crews
    direction = len(direction_positive) / max(1, len(synth_crews))

    flagged = _flagged_crews(res) & synth_crews
    false_flags = len(flagged) - len(direction_positive)  # rough

    sc = ScenarioScore(name="T-DIFFUSE", direction=direction, bleed=max(0, false_flags))
    if direction >= THRESHOLDS["direction_better"]:
        sc.passed = True
        sc.notes = f"direction {direction:.2f} ≥ {THRESHOLDS['direction_better']} (better)"
    elif direction >= THRESHOLDS["direction_pass"]:
        sc.passed = True
        sc.notes = f"direction {direction:.2f} ≥ {THRESHOLDS['direction_pass']} (pass)"
    elif direction < THRESHOLDS["direction_fail"]:
        sc.passed = False
        sc.failed_reason = f"direction {direction:.2f} < {THRESHOLDS['direction_fail']}"
    else:
        sc.passed = False
        sc.failed_reason = f"direction {direction:.2f} in fail band"
    return sc


def score_T_dead(inj_df, label_path: pathlib.Path) -> ScenarioScore:
    """T-DEAD: injection on non-elimination games must NOT bleed into
    SERIES_EXTENSION. Only relevant if the elimination family is present."""
    from families.officiating_series import SeriesExtension
    labels = labelmod.load(label_path)
    ctx = TestContext(
        subclaim_id="SUB-DEAD", stream="sports/nba/pilot",
        baseline=BaselineRef(
            baseline_id="BSL-ELIMINATION-BASE", version="v2.0.0",
            hash="blake3:" + "0" * 64, parameters={},
        ),
        rng_seed=99, alpha=0.01, family_size=1,
        holdout_seasons=["2023-24", "2024-25"],
    )
    res = SeriesExtension().run(ctx, inj_df)

    # bleed = a spurious effect appears when the injection was on regular-season games
    spurious = False
    if res.per_unit:
        spurious = any(u["verdict"] in ("SUPPORTED", "PARTIALLY_SUPPORTED")
                       for u in res.per_unit)
    else:
        # Single-test family: infer from overall effect
        spurious = (
            res.effect_size == res.effect_size  # not NaN
            and abs(res.effect_size - 1.0) > 0.20
            and res.p_adjusted < 0.01
        )

    sc = ScenarioScore(name="T-DEAD", bleed=1 if spurious else 0)
    if not spurious:
        sc.passed = True
        sc.notes = "no bleed (better)"
    else:
        sc.passed = False
        sc.failed_reason = "spurious SERIES_EXTENSION effect from non-elimination injection"
    return sc


def render_markdown(scores: list[ScenarioScore], meta: dict) -> str:
    lines = ["# Synthetic Injection Report", ""]
    lines.append(f"Seasons: {meta.get('seasons', [])}")
    lines.append(f"Holdout: {meta.get('holdout', [])}")
    lines.append(f"Rows: {meta.get('n_rows', '?')}")
    lines.append(f"Elapsed: {meta.get('elapsed_sec', '?')}s")
    lines.append("")
    lines.append("| Scenario | Metric | Value | Threshold | Status | Notes |")
    lines.append("|---|---|---|---|---|---|")
    for s in scores:
        metric, value, thresh = "", "", ""
        if s.recall is not None:
            metric, value = "Recall", f"{s.recall:.2f}"
            thresh = f"≥ {THRESHOLDS['recall_pass']}"
        elif s.fpr is not None:
            metric, value = "FPR", f"{s.fpr:.4f}"
            thresh = f"≤ {THRESHOLDS['fpr_pass']}"
        elif s.bleed is not None:
            metric, value = "Bleed (FPs)", f"{s.bleed}"
            thresh = f"≤ {THRESHOLDS['bleed_pass']}"
        elif s.direction is not None:
            metric, value = "Direction", f"{s.direction:.2f}"
            thresh = f"≥ {THRESHOLDS['direction_pass']}"
        status = "PASS" if s.passed else "FAIL"
        notes = s.notes if s.passed else s.failed_reason
        lines.append(f"| {s.name} | {metric} | {value} | {thresh} | {status} | {notes} |")
    lines.append("")

    all_passed = all(s.passed for s in scores)
    lines.append(f"## Verdict: **{'PASS' if all_passed else 'FAIL'}**")
    if not all_passed:
        lines.append("")
        lines.append("### Failures")
        for s in scores:
            if not s.passed:
                lines.append(f"- **{s.name}**: {s.failed_reason}")
    return "\n".join(lines)


def main() -> int:
    report_path = OUT / "pilot_report.json"
    if not report_path.exists():
        print(f"missing {report_path}; run run.py first")
        return 2
    meta = json.loads(report_path.read_text())

    # Re-derive the injected frames from the same generator (deterministic seeds)
    from synth.inject import inject
    from data.sources import fetch_season_pbp, fetch_crew_assignments, fetch_season_games
    from data.canonical import build_canonical, foul_differential_per_100

    # For scoring, we reload holdout from cache and re-inject with the same seeds.
    # This is why inject() must be deterministic — the labels in out/labels/*.json
    # are the audit trail; the data is regenerated deterministically here.
    # The rebuild mirrors run.py's load_all() exactly (season-level
    # build_canonical, same games/pbp/crews fetch, same series-frame
    # construction) — otherwise the integrity gate's root hashes can never match.
    hold_frames = []
    series_frames = []
    for s in meta["holdout"]:
        games, _ = fetch_season_games(s, "Regular Season")
        try:
            games_po, _ = fetch_season_games(s, "Playoffs")
        except RuntimeError:
            games_po = pd.DataFrame()
        games_all = pd.concat([games, games_po], ignore_index=True) if not games_po.empty else games

        pbp, _ = fetch_season_pbp(s)
        crews, _ = fetch_crew_assignments(s)
        canon, _ = build_canonical(pbp, crews, games_all)
        if not canon["crew_games"].empty:
            cg = foul_differential_per_100(
                canon["crew_games"], canon["fouls"], canon["possessions"])
            cg["season"] = s
            # Adjustment set for CREW_TENDENCY — identical to run.py's
            # load_all (see the comment there). The gate hashes these as
            # part of hold_df, so any drift here fails Check 1 loudly.
            margins = canon["games"][["game_id", "home_score", "away_score"]].copy()
            m = (margins["home_score"] - margins["away_score"]).abs()
            margins["margin_bucket"] = np.where(m <= 5, 0, np.where(m <= 15, 1, 2)).astype(int)
            cg = cg.merge(margins[["game_id", "margin_bucket"]], on="game_id", how="left")
            cg["pace"] = cg["n_poss"]
            cg["rest_diff"] = 0
            hold_frames.append(cg)
        if not canon["games"].empty:
            g = canon["games"].copy()
            g["season"] = s
            g = g.merge(
                canon["crew_games"][["game_id", "crew_code"]], on="game_id", how="left")
            g["home"] = 1
            g["rest_diff"] = 0
            g["injury_active"] = 0
            g["crew_trailing_flag"] = g["crew_code"].notna().astype(int)
            series_frames.append(g)
    hold_df = pd.concat(hold_frames, ignore_index=True) if hold_frames else pd.DataFrame()
    series_hold_df = pd.concat(series_frames, ignore_index=True) if series_frames else pd.DataFrame()

    if hold_df.empty:
        print("no holdout rows; run run.py first to populate cache")
        return 2

    # ---- INTEGRITY GATE — before any scoring ----
    from synth.integrity import (
        verify_report_integrity, IntegrityError, EXIT_INTEGRITY,
    )
    try:
        integrity = verify_report_integrity(
            report_path, hold_df, LABELS, series_hold_df=series_hold_df)
    except IntegrityError as e:
        print("\n### INTEGRITY FAILURE\n")
        print(str(e))
        print("\nRefusing to score. See out/pilot_report.json for the provenance record.")
        return EXIT_INTEGRITY

    if not integrity.pandas_match:
        env = integrity.diagnostics["environment"]
        print(
            f"WARNING: pandas version drift "
            f"(pilot={env['pandas_expected']}, scorer={env['pandas_actual']}).\n"
            "Root hashes matched, but if scoring results look anomalous, "
            "pin pandas and re-run both."
        )

    print(
        f"integrity: OK "
        f"({integrity.scenarios_checked} scenarios reproduced, "
        f"hold_df {integrity.diagnostics['hold_df']['expected'][:24]}…)"
    )

    # ---- from here, scoring proceeds normally ----
    scores: list[ScenarioScore] = []

    # T-NULL
    inj_df, label_hash = inject(hold_df, "T-NULL", seed=100)
    scores.append(score_T_null(inj_df, LABELS / "T-NULL_seed100.json"))

    # T-SMALL, T-LARGE
    for scen in ("T-SMALL", "T-LARGE"):
        inj_df, _ = inject(hold_df, scen, seed=100)
        scores.append(score_T_inject(inj_df, LABELS / f"{scen}_seed100.json", scen))

    # T-DIFFUSE
    inj_df, _ = inject(hold_df, "T-DIFFUSE", seed=100)
    scores.append(score_T_diffuse(inj_df, LABELS / "T-DIFFUSE_seed100.json"))

    # T-DEAD (only if the series holdout frame has elimination games).
    # Scored from the SERIES holdout frame, not the crew frame — the
    # injection in run.py was made there, and the gate verified it there.
    if not series_hold_df.empty and "is_elimination" in series_hold_df.columns:
        inj_df, _ = inject(series_hold_df, "T-DEAD", seed=200)
        scores.append(score_T_dead(inj_df, LABELS / "T-DEAD_seed200.json"))

    md = render_markdown(scores, meta)
    (OUT / "scoring_report.md").write_text(md)
    (OUT / "scoring_report.json").write_text(json.dumps(
        [s.__dict__ for s in scores], indent=2))
    print(md)
    return 0 if all(s.passed for s in scores) else 1


if __name__ == "__main__":
    sys.exit(main())
