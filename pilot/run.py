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
from data.sources import fetch_season_pbp, fetch_crew_assignments
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


def load_all(seasons: list[str]) -> pd.DataFrame:
    # Per-game build, mirroring synth/report.py's holdout rebuild exactly:
    # build_canonical() takes one game at a time and returns
    # (tables, discrepancies). run.py and report.py must canonicalize the
    # same way, or the integrity gate's hold_df_hash root check can never pass.
    # home_team/away_team are "" placeholders until the data layer (sources.py,
    # still TODO) supplies real team IDs — both sides must change together.
    dfs = []
    for s in seasons:
        pbp, _ = fetch_season_pbp(s)
        crews, _ = fetch_crew_assignments(s)
        for gid in pbp["game_id"].unique() if "game_id" in pbp.columns else []:
            canon, _ = build_canonical(
                pbp[pbp["game_id"] == gid],
                crews,
                game_id=str(gid),
                home_team="", away_team="",
            )
            if not canon["crew_games"].empty:
                cg = foul_differential_per_100(
                    canon["crew_games"], canon["fouls"], canon["possessions"])
                cg["season"] = s
                dfs.append(cg)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def main() -> int:
    t0 = time.time()
    df = load_all(SEASONS)

    if df.empty:
        print("NO DATA. Run data/sources.py to populate cache first.")
        return 2

    fit_df = df[~df["season"].isin(HOLDOUT)]
    hold_df = df[df["season"].isin(HOLDOUT)]

    report: dict = {"seasons": SEASONS, "holdout": HOLDOUT,
                    "n_rows": int(len(df)), "results": {}, "injections": {}}

    # ---- provenance (integrity check) ----
    from synth.integrity import frame_hash as _frame_hash

    report["hold_df_hash"] = _frame_hash(hold_df)
    report["n_holdout_rows"] = int(len(hold_df))
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
            "effect_size": r.effect_size,
            "p_adjusted": r.p_adjusted,
            "notes": r.notes,
        }

    # ---- series extension ----
    if "is_elimination" in df.columns:
        se_ctx = TestContext(
            subclaim_id="SUB-SERIES", stream="sports/nba/pilot",
            baseline=CREW_BASELINE, rng_seed=99, alpha=0.01,
            family_size=1, holdout_seasons=HOLDOUT)
        se_res = SeriesExtension().run(se_ctx, df)
        report["results"]["series_extension"] = se_res.model_dump()

        for scenario in ["T-EXTENSION", "T-DEAD"]:
            # Injected from hold_df, like the four crew scenarios above:
            # the integrity gate (synth/integrity.py Check 3) and the scorer
            # (synth/report.py) both re-inject every scenario from hold_df,
            # so injecting from the full frame here could never reproduce.
            inj_df, label_hash = inject(hold_df, scenario, seed=200)
            r = SeriesExtension().run(se_ctx, inj_df)
            report["injections"][scenario] = {
                "label_hash": label_hash,
                "frame_hash": _frame_hash(inj_df),
                "seed": 200,
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
