# Observatory walkthrough — a regulator opens a sealed finding cold

The demo for the first regulator you talk to. No briefing, no walkthrough call, just a package link. The question at every screen: can they decide whether to act without trusting you?

## The setup

A regulator receives a link: `observatory.molt-sports/v1/export/package/PKG-…`, tier REGULATOR. They have never seen the system. They open it cold. What follows is what they see, in order, and what each screen proves.

## Screen 0 — the link itself

```
Package PKG-2025-1108-0042
Bundle hash: blake3:9c1f…
Tier: REGULATOR
Log head: blake3:44ab…  [verify]
```

Before anything else, the hash. The regulator can check the bundle hash against the published log head without opening the package. If it doesn't match, the package was altered after sealing and the walkthrough stops here. Nothing inside matters until this checks out.

**What it proves:** the thing they're about to read is the thing that was sealed. Not a copy, not an edit.

## Screen 1 — the verdict, plain

```
Verdict: PARTIALLY_SUPPORTED
Confidence: 0.61
Subclaim: SUB-3f9a… — OFFICIATING.SERIES_EXTENSION
Entity: CREW-2024-017 (role code, no name)
Games: 214 elimination games, 2015–2025

NOTICE: Probabilistic finding, not an accusation.
This package names no individual and asserts no intent.
```

One screen, no scrolling to find the point. The verdict, the number, what it covers, what it doesn't say. Confidence is a number, never a word — "0.61", not "likely". The notice is fixed chrome, not a footnote.

**What it proves:** the system will tell you what it found and how sure it is, in the first thing you read.

## Screen 2 — the dissent, before the evidence

```
Signatures (3):
  REVIEWER-STAT   CONCUR   2025-11-01
  REVIEWER-DOMAIN CONCUR   2025-11-03
  REVIEWER-STAT   DISSENT  2025-11-05

Dissent basis:
"Family defined post hoc; FWER not controlled across
the two seasons tested."
Cited evidence: blake3:aa02…
```

The dissent comes before the evidence, on purpose. A regulator who reads the disagreement first cannot be misled by the finding. If there is no dissent, the screen says so plainly: "No dissent. 2 concur."

**What it proves:** disagreement is published, not buried. The system cannot ship a strong finding past an objecting statistician.

## Screen 3 — the evidence chain

```
Evidence (4 refs):
  EVIDENCE.STAT_TEST  pooled logistic, OR 1.31, CI [1.04, 1.66]
    p_raw 0.021 → p_adjusted 0.048 (BH, family of 12)
    power achieved 0.83 · n = 214 · replay ✓
  EVIDENCE.SIMULATION  10,000 sims, observed at 94th percentile
  EVIDENCE.NULL  2 tests found nothing (listed, not omitted)
  EVIDENCE.BASELINE_COMPARISON  vs BSL-ELIMINATION-BASE@v2

Coverage gaps (1):
  2020 bubble games tagged, excluded from fit, counted.

Limitations (3):
  "Single pooled window; series-level clustering unmodeled."
  "Home-court and rest separable, travel not fully."
  "Crew assignment non-random in playoffs."
```

Every number carries its method. Nulls are listed next to positives. The gap is named, not hidden. The limitations are the system's own words about its weakness.

**What it proves:** the finding stands on named tests with named limits, and the tests that found nothing are in the same list.

## Screen 4 — replay

```
Replay this verdict:
  docker run ghcr.io/molt-sports/replay@sha256:…
  Expected output hash: blake3:e07d…
  Runtime: python:3.12-slim · ~42s

[ Run replay ]  →  output hash matches ✓
```

One click. The regulator reruns the exact code on the exact inputs and gets the exact output hash. If it doesn't reproduce, the verdict is auto-flagged for SUPERSEDE and the screen says so.

**What it proves:** the finding is a computation, not a claim. Anyone can redo it.

## Screen 5 — the baseline

```
Baseline: BSL-ELIMINATION-BASE@v2.0.0
  hash blake3:44ab… · adopted 2025-09-14
  Drift flag: none active
  Falsification conditions: 3 (listed)
  Known limitations: 4 (listed)
  Supersedes: v1.3.0 · Superseded by: none
```

The baseline is a frozen artifact with its own falsification conditions — what observation would show it wrong. If the baseline has drifted or been deprecated, that's on this screen, with the chain to its replacement.

**What it proves:** the yardstick itself is public, versioned, and falsifiable. If the baseline is wrong, the verdicts built on it are traceable.

## Screen 6 — the quarantine log

```
Rejected on this stream (5):
  UNCORRECTED_SIGNIFICANCE  3
  TESTIMONY_AS_PROOF        1
  NAMING_PROHIBITED         1

[view digests]
```

The system's own rejection log, published. A regulator can see what the engine refused and why. A system that never rejects anything is a system that never says no.

**What it proves:** the guardrails actually fire. The refusals are visible, not asserted.

## Screen 7 — the decision

Three actions. Each one writes a signed event to the log.

```
[ Open inquiry ]      — package attached, case opened, clock starts
[ Request more ]      — names what's missing (power, coverage, a test)
[ Close with reason ] — writes the reason; the package stays sealed
```

There is no fourth option, no "ignore quietly." Whatever the regulator does, it's on the record — and so is whatever they don't do.

**What it proves:** the regulator's decision is as auditable as the finding.

## What the regulator can say afterward

"I verified the hash, read the dissent before the evidence, reran the test myself, and the finding stands on these numbers — or it doesn't."

## What they can never say

"The system told me who did it." It can't. There is no field for a name in a verdict, no reference path from verdict to identity, and the validator refuses narrative containing proper names. The regulator leaves with a probability and a paper trail, not an accusation.

## The demo, in one sentence

Hand a regulator a link, say nothing, and let the package defend itself — hash first, dissent second, evidence third, replay on demand, decision logged.
