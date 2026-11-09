# The Week-One Pilot

One dataset. Two families. One synthetic injection test. Clear pass/fail. The goal is not to find truth about the NBA — it's to find out whether the design survives contact with real data before you build the rest of the system.

---

## A. Dataset

Ten seasons: 2014-15 through 2024-25.

Why ten and not one or two:

| Need | Requirement | 10 seasons gives you |
|---|---|---|
| CREW_TENDENCY min sample (40 crew-games/crew) | 40 | ~200 crew-games per crew — comfortable |
| SERIES_EXTENSION min sample (200 pooled elimination games) | 200 | ~250 elimination games — just barely enough |
| Holdout for sign stability | 1+ seasons | 2 seasons held out (2023-24, 2024-25) |
| Detect base-rate shifts across eras | Multiple seasons | Bubble, rule changes, pace changes all visible |

Sources (all free or near-free):

| Source | What | Use |
|---|---|---|
| NBA Stats API (cdn.nba.com, stats.nba.com) | Official play-by-play, box scores, crew assignments | Primary ground truth |
| Basketball-Reference | Cross-check PBP, historical fouls | INGEST.SOURCE_DISCREPANCY generation |
| NBA Officiating Last Two Minute reports | Public PDFs | L2M_CONTRADICTION family later; pilot uses for coverage-gap illustration |
| NBA injury reports (public archive) | Pre-tip status | Adjustment set: injury-active flag |

Explicit exclusions, named in limitations, not silently dropped:

- 2020 bubble games — included but tagged SEASON_PHASE: BUBBLE. If you exclude it you're hiding a real data-quality problem; if you include it you're testing whether your model handles regime breaks.
- Games with incomplete crew assignments (some early-season and rescheduled games) — tagged COVERAGE_GAP, excluded from fit, count toward the coverage threshold.
- Games with PBP segments missing or degraded — same treatment.

The pilot must report, at the top of the output: how many games were included, how many excluded, and why. If the exclusion rate is above 5%, the pilot has a data problem, not a statistics problem.

---

## B. The Two Families

### Family 1: OFFICIATING.CREW_TENDENCY

Why this one first: It has the most data, the most existing literature to calibrate against (published referee-analytics work has already shown this is measurable), and the widest range of plausible outcomes — it should produce some nulls, some inconclusive, maybe one or two partial-supported. That range is exactly what you need to test the whole verdict machinery.

Expected pilot outcome:

- 55–70% of crews: REFUTED or EVIDENCE.NULL — CI contains zero
- 20–35%: INCONCLUSIVE — underpowered (crew didn't have enough appearances) or method disagreement
- 5–15%: PARTIALLY_SUPPORTED — real signal on a few crews after FDR correction
- 0%: SUPPORTED — the tier-4 gate requires 4 signatures and 30-day cooling. The pilot ships packages ready for review, not sealed SUPPORTED findings. That's a design feature, not a limitation.

If the pilot produces anything outside these bands, the design is miscalibrated and you find out in week one.

### Family 2: OFFICIATING.SERIES_EXTENSION

Why this one second: It's underpowered by design even with ten years of data. That's the honest test. If your system can ship a VERDICT.INCONCLUSIVE with a clean power citation and no hand-wringing, you've proven the most important thing: the system doesn't manufacture findings when the data can't support them.

Expected pilot outcome:

- 70–85%: INCONCLUSIVE — power floor fires, verdict cites achieved power
- 10–25%: REFUTED — effect estimated but below floor
- 0–5%: PARTIALLY_SUPPORTED — if there's a weak pooled signal, it appears here, but it's not required
- 0%: SUPPORTED — same gate as above

The pilot passes if it says "I don't know" cleanly and often. That is the deliverable.

### Optional canary: TEMPORAL.CLOCK_ANOMALY

Cheap to implement. Not a real family in the integrity sense — it's a data-quality detector. Implement it only to prove your PBP ingestion is clean. If it fires on more than 0.5% of games, your feed has problems and everything downstream is suspect.

Don't skip this. Every statistician who sees your pilot output will ask "how do you know your data is clean?" The canary is your answer.

---

## C. The Synthetic Injection Test

This is the one that matters. Without it, you have no idea whether your detector works — only that it produces output.

### C.1 — The design

Take the real, unmodified ten seasons. Fit CREW_TENDENCY on 8 of them (2014-15 to 2021-22). Hold out 2 (2022-23, 2023-24) for injection. Then:

| Test | Injection | Expected verdict |
|---|---|---|
| T-NULL | Nothing changed | Fit crew effects match fit-set estimates; zero new PARTIALLY_SUPPORTED |
| T-SMALL | Inject 0.5% of games with +1.5 foul/100-possession shift on a single synthetic crew | That crew → PARTIALLY_SUPPORTED; other crews unchanged |
| T-LARGE | Inject 5% of games with +1.5 shift on a single synthetic crew | That crew → SUPPORTED tier-eligible; other crews unchanged |
| T-DIFFUSE | Inject 0.3% of games across 20 crews | ≤2 of the 20 → PARTIALLY_SUPPORTED; ≥15 → REFUTED |
| T-EXTENSION | Inject 15% bias into elimination games favoring trailing team | SERIES_EXTENSION → PARTIALLY_SUPPORTED |
| T-DEAD | Inject into regular-season games, not elimination | SERIES_EXTENSION → REFUTED (doesn't bleed) |

The injected games are labeled with a hash in a separate, sealed file that the harness doesn't see during fitting. The results are compared post-hoc.

### C.2 — Acceptance thresholds

| Metric | Pass | Better | Fail |
|---|---|---|---|
| Recall on T-SMALL, T-LARGE | ≥ 0.60 | ≥ 0.80 | < 0.40 |
| FPR on T-NULL | ≤ 0.05 | ≤ 0.02 | 0.10 |
| Bleed on T-DEAD | ≤ 1 false positive | 0 | ≥ 3 |
| Direction on T-DIFFUSE | Directional accuracy ≥ 70% | ≥ 85% | < 60% |

If recall is low and FPR is high, the detector is noise, not signal. If recall is low and FPR is low, the detector is too conservative — probably the effect size floor or the prior skepticism is too strong. Both are fixable in spec, both are the things you want to find out in week one.

---

## D. Full Acceptance Criteria

The pilot passes if all of these are true:

| # | Criterion | Threshold |
|---|---|---|
| 1 | Determinism | Three runs, same seed, byte-identical TestResult and replay_manifest |
| 2 | Runtime | Full 10-season fit in < 4 hours on one 16-core box (single crew model), < 12 hours for the full pipeline |
| 3 | Coverage | ≥ 95% of games in the dataset pass INGEST.SOURCE_SNAPSHOT validation |
| 4 | Verdict distribution | Within the expected bands defined in §B for both families |
| 5 | Synthetic detection | Meets the thresholds in §C.2 |
| 6 | Replay | Three randomly selected verdicts reproduced byte-identically by an independent run |
| 7 | Human review | 1 statistician + 1 domain reviewer, blind to synthetic labels, agree with 8/10 verdicts |
| 8 | Null artifact | The output includes a sealed, publishable example of a REFUTED verdict for a named code (CREW-…, not a person) |
| 9 | Runtime reproducibility | The replay container (docker run ghcr.io/...) pulls and runs without network access to anything but the frozen data |
| 10 | Bug-free nulls | Zero VERDICT.SUPPORTED in the entire pilot output — if there is one, an admission rule is broken |

Number 10 is non-negotiable. If the pilot produces a SUPPORTED verdict, it means the tier quorum gate has a bug, and that's a release blocker.

---

## E. What Failure Looks Like (and what it tells you)

| Symptom | Diagnosis | Fix |
|---|---|---|
| Every crew returns SUPPORTED | Baseline overfit, effect floor too low, or FDR not applied | Recalibrate BSL-OFFICIATING-CREW; check BH implementation |
| Every crew returns REFUTED | Effect floor too high, prior too strong, or adjustment set too aggressive | Loosen effect floor; check prior scale |
| ~50% INCONCLUSIVE on CREW_TENDENCY | Cohort sizes below threshold — probably too many crews across too few seasons | Extend dataset, or accept the finding |
| Synthetic injection recall < 0.40 | Detector is genuinely weak; the model spec is wrong | Rewrite the spec; do not "tune" your way to recall |
| FPR > 0.10 | Multiple-comparison family too small, or test miscalibrated | Widen the family, use a stronger correction |
| Bleed on T-DEAD > 3 | Contamination between families — series extension is picking up regular-season noise | Check the family isolation in CLAIM.DECOMPOSE |
| Runtime > 24 hours | Architecture is fine, implementation is slow | Vectorize, cache baselines, don't re-fit every season |
| Canary TEMPORAL.CLOCK_ANOMALY fires > 1% | PBP feed is dirty | Stop. Fix ingestion before running any statistics. |

The pilot is not designed to prove the thesis. It's designed to prove the system can distinguish signal from noise from uncertainty from untestable. If it comes back mostly null, that's a successful pilot and a publishable finding. If it comes back mostly flagged, the pilot failed.

If you can't say that out loud to a customer, don't run the pilot.

---

## F. Deliverables From the Pilot

These are the artifacts that come out of the pilot, and each one is either a customer deliverable or a build dependency:

1. The harness — molt/sports/harness/ with two registered families, passing conformance
2. The run script — pilot/run.py, reproducible from a clean checkout
3. The verdict package — one sealed REFUTED and one PARTIALLY_SUPPORTED finding, each with full evidence, replay proof, and review chain (even if the review is your own team for the pilot — the chain is what matters)
4. The synthetic injection report — recall, FPR, bleed, per-family
5. The reproducibility bundle — docker run that recreates the whole pilot output
6. The known-limitations document — what the pilot did not test, what data it didn't have, what the next pilot needs

Artifacts 3 and 4 are what you show the first customer. Artifact 6 is what you show the first lawyer.

---

## G. The One-Sentence Pass Condition

"A statistician I don't know can rerun the pilot from a clean checkout, verify it's deterministic, look at the synthetic injection report, and conclude the detector works — or conclude it doesn't, without ever having to trust me."

That's the bar. If the pilot clears that bar, the design holds and you build the rest of the system. If it doesn't, the failure is visible in week one instead of in front of a regulator.

---

## H. What I'd Do in Week One, Day by Day

| Day | Task |
|---|---|
| 1 | Data acquisition + INGEST.SOURCE_SNAPSHOT for all 10 seasons, plus SOURCE_DISCREPANCY against B-Ref |
| 2 | Canary TEMPORAL.CLOCK_ANOMALY run; if it fires, stop and fix ingestion |
| 3–4 | CREW_TENDENCY implemented, harness conformance passing, fitted on 2014-15 → 2021-22 |
| 5 | SERIES_EXTENSION implemented, conformance passing |
| 6 | Synthetic injection generation (the six test scenarios from §C.1), sealed labels |
| 7 | Full pipeline run, verdict package assembled, human review of 10 verdicts |

If day 2 fires the canary, everything slips. That's fine — it's the whole point of having a canary. You'd rather lose a week to a dirty feed than publish a clean-looking verdict built on contaminated data.

The pilot is the bridge between "the design is written down" and "the design is true." Build it next, before anything else.

The pilot skeleton code lives in `pilot/`. See `pilot/README.md`.
