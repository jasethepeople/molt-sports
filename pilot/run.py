"""Pilot orchestrator. Deterministic. No network in this script — data
must already be cached by data/sources.py."""
from __future__ import annotations

import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

from data.canonical import build_canonical, foul_differential_per_100
from data.sources import fetch_season_pbp, fetch_crew_assignments, fetch_season_games
from families.officiating_crew import CrewTendency
from families.officiating_series import SeriesExtension
from families.temporal_clock import ClockAnomaly
from harness.protocol import TestContext, BaselineRef
from synth.inject import inject
from verify.replay import assert_reproducible, result_hash

SEASONS = [f"{y}-{str(y+1)[-2:]}" for y in range(2014, 2025)]
HOLDOUT = SEASONS[-2:]
OUT = pathlib.Path("out")
OUT.mkdir(exist_ok=True)

CREW_BASELINE = BaselineRef(
    baseline_id="BSL-OFFICIATING-CREW", version="v3.0.0",
    hash="blake3:" + "0" * 64, parameters={"prior": "empirical_bayes_normal_normal"},
)


def load_all(seasons: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (crew_game_outcome_df, series_state_df)."""
    cg_frames = []
    series_frames = []
    for s in seasons:
        games, _ = fetch_season_games(s, "Regular Season")
        try:
            games_po, _ = fetch_season_games(s, "Playoffs")
        except RuntimeError:
            games_po = pd.DataFrame()
        games_all = pd.concat([games, games_po], ignore_index=True) if not games_po.empty else games

        pbp, _ = fetch_season_pbp(s)
        crews, _ = fetch_crew_assignments(s)

        canon, discs = build_canonical(pbp, crews, games_all)
        print(f"  {s}: {len(canon['crew_games'])} crew-games, {len(discs)} discrepancies")

        if not canon["crew_games"].empty:
            cg = foul_differential_per_100(
                canon["crew_games"], canon["fouls"], canon["possessions"])
            cg["season"] = s
            # Adjustment set for CREW_TENDENCY: the family regresses y on
            # these three columns, but no pipeline ever supplied them, so
            # run.py crashed at CrewTendency before any injection ran.
            # pace = total possessions (n_poss); margin_bucket = final-margin
            # bucket (0: <=5, 1: 6-15, 2: >15 — pilot convention, documented
            # here, not a spec claim); rest_diff = 0 until the game-date
            # per-team derivation lands (same TODO as the series frame).
            # report.py's rebuild must compute these identically — the gate
            # hashes them as part of hold_df.
            margins = canon["games"][["game_id", "home_score", "away_score"]].copy()
            m = (margins["home_score"] - margins["away_score"]).abs()
            margins["margin_bucket"] = np.where(m <= 5, 0, np.where(m <= 15, 1, 2)).astype(int)
            cg = cg.merge(margins[["game_id", "margin_bucket"]], on="game_id", how="left")
            cg["pace"] = cg["n_poss"]
            cg["rest_diff"] = 0
            cg_frames.append(cg)

        # series frame for SERIES_EXTENSION
        if not canon["games"].empty:
            g = canon["games"].copy()
            g["season"] = s
            g = g.merge(
                canon["crew_games"][["game_id", "crew_code"]], on="game_id", how="left")
            g["home"] = 1  # placeholder; adjustment set entry
            g["rest_diff"] = 0  # TODO(PILOT): derive from game_date per team
            g["injury_active"] = 0  # TODO(PILOT): derive from injury reports
            g["crew_trailing_flag"] = g["crew_code"].notna().astype(int)
            series_frames.append(g)

    cg_df = pd.concat(cg_frames, ignore_index=True) if cg_frames else pd.DataFrame()
    series_df = pd.concat(series_frames, ignore_index=True) if series_frames else pd.DataFrame()
    return cg_df, series_df


def main() -> int:
    t0 = time.time()
    df, series_df = load_all(SEASONS)

    if df.empty:
        print("NO DATA. Run data/sources.py to populate cache first.")
        return 2

    fit_df = df[~df["season"].isin(HOLDOUT)]
    hold_df = df[df["season"].isin(HOLDOUT)]
    series_hold_df = (
        series_df[series_df["season"].isin(HOLDOUT)]
        if not series_df.empty else pd.DataFrame()
    )

    report: dict = {"seasons": SEASONS, "holdout": HOLDOUT,
                    "n_rows": int(len(df)), "results": {}, "injections": {}}

    # ---- provenance (integrity check) ----
    from synth.integrity import frame_hash as _frame_hash

    report["hold_df_hash"] = _frame_hash(hold_df)
    report["n_holdout_rows"] = int(len(hold_df))
    report["series_hold_df_hash"] = _frame_hash(series_hold_df)
    report["n_series_holdout_rows"] = int(len(series_hold_df))
    report["pandas_version"] = pd.__version__
    report["numpy_version"] = np.__version__

    # ---- canary ----
    canary_ctx = TestContext(
        subclaim_id="SUB-CANARY", stream="sports/nba/2024-25/game/pilot",
        rng_seed=7, alpha=0.01, family_size=1, holdout_seasons=HOLDOUT)
    # Canary expects a possessions frame; in pilot we pass the crew_game frame with
    # a timing_delta_sec column if present.
    if "timing_delta_sec" in df.columns:
        cr = ClockAnomaly().run(canary_ctx, df)
        report["results"]["canary"] = {"flag_rate": cr.statistic,
                                        "notes": cr.notes}
        if cr.statistic > 0.005:
            print("CANARY FIRED. Fix ingestion before continuing.")
            return 3

    # ---- crew tendency ----
    crew_ctx = TestContext(
        subclaim_id="SUB-CREW", stream="sports/nba/pilot",
        baseline=CREW_BASELINE, rng_seed=42, alpha=0.01,
        family_size=int(df["crew_code"].nunique()), holdout_seasons=HOLDOUT)
    crew_hash = assert_reproducible(CrewTendency, crew_ctx, fit_df)
    crew_res = CrewTendency().run(crew_ctx, fit_df)
    report["results"]["crew_tendency"] = {
        "result_hash": crew_hash, **crew_res.model_dump(),
    }

    # ---- synthetic injections ----
    for scenario in ["T-NULL", "T-SMALL", "T-LARGE", "T-DIFFUSE"]:
        inj_df, label_hash = inject(hold_df, scenario, seed=100)
        ctx = crew_ctx.model_copy(update={"subclaim_id": f"SUB-{scenario}"})
        r = CrewTendency().run(ctx, inj_df)
        report["injections"][scenario] = {
            "label_hash": label_hash,
            "frame_hash": _frame_hash(inj_df),
            "seed": 100,
            "frame": "crew",
            "effect_size": r.effect_size,
            "p_adjusted": r.p_adjusted,
            "notes": r.notes,
        }

    # ---- series extension ----
    # Runs on the SERIES frame (series_df), not the crew outcome frame:
    # the crew frame has no is_elimination column, so guarding on it would
    # silently skip the series scenarios entirely.
    if not series_df.empty and "is_elimination" in series_df.columns:
        se_ctx = TestContext(
            subclaim_id="SUB-SERIES", stream="sports/nba/pilot",
            baseline=CREW_BASELINE, rng_seed=99, alpha=0.01,
            family_size=1, holdout_seasons=HOLDOUT)
        se_res = SeriesExtension().run(se_ctx, series_df)
        report["results"]["series_extension"] = se_res.model_dump()

        for scenario in ["T-EXTENSION", "T-DEAD"]:
            # Injected from the SERIES holdout frame: the integrity gate and
            # the scorer re-inject series scenarios from the series frame,
            # not the crew frame — injecting from the crew frame here could
            # never reproduce (and the crew frame lacks the columns anyway).
            inj_df, label_hash = inject(series_hold_df, scenario, seed=200)
            r = SeriesExtension().run(se_ctx, inj_df)
            report["injections"][scenario] = {
                "label_hash": label_hash,
                "frame_hash": _frame_hash(inj_df),
                "seed": 200,
                "frame": "series",
                "notes": r.notes,
                "effect_size": r.effect_size,
                "p_adjusted": r.p_adjusted,
            }

    report["elapsed_sec"] = round(time.time() - t0, 1)
    out = OUT / "pilot_report.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"wrote {out}  elapsed={report['elapsed_sec']}s")

    # ---- pass/fail ----
    failures = []
    for name, r in report["injections"].items():
        if name in ("T-EXTENSION", "T-DEAD"):
            continue  # series tests assessed separately
        if name == "T-NULL" and abs(r["effect_size"]) > 0.5:
            failures.append(f"T-NULL leaked: {r['effect_size']}")
        if name in ("T-SMALL", "T-LARGE") and abs(r["effect_size"]) < 0.5:
            failures.append(f"{name} not detected: {r['effect_size']}")
    if failures:
        print("PILOT FAILED:")
        for f in failures:
            print(" -", f)
        return 1
    from synth.report import main as scoring_main
    rc = scoring_main()
    if rc != 0:
        print("SCORING FAILED. See out/scoring_report.md")
        return 1
    print("PILOT PASSED (structural + synthetic)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
