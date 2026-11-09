# Baseline Registry

Every EVIDENCE.STAT_TEST carries a baseline_ref. That reference is the load-bearing wall of the entire credibility chain: if the baseline is private, unauditable, or silently revised, every verdict built on it is worthless. So baselines are first-class frozen artifacts, published, hashed, and falsifiable.

## A.1 — Contract bump

This adds kinds the v1.0.0 contract didn't have. Per the freeze discipline, this is a new contract version, not a patch:

```
contract_version: 1.1.0
added_kinds:
  BASELINE: [PROPOSE, REVIEW, ADOPT, DEPRECATE, DRIFT_FLAG]
  REVIEW:   [ASSIGN, DISCLOSE, ACCEPT, REFUSE, CONCUR, DISSENT, TIMEOUT]
```

A world frozen at 1.0.0 continues to validate against 1.0.0. No retroactive relabeling. That's the point of freezing.

## A.2 — Baseline artifact schema

```json
{
  "$id": "molt://sports/schema/baseline/v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "baseline_id","name","version","scope","population","unit_of_analysis",
    "outcome","adjustment_set","estimation_method","prior",
    "uncertainty","falsification_conditions","known_limitations",
    "source_data_hashes","author","proposed_utc","status"
  ],
  "properties": {
    "baseline_id": { "type": "string", "pattern": "^BSL-[A-Z0-9_]+$" },
    "name": { "type": "string" },
    "version": { "type": "string", "pattern": "^v[0-9]+\\.[0-9]+\\.[0-9]+$" },
    "scope": {
      "type": "object",
      "required": ["sport","seasons","game_types"],
      "properties": {
        "sport": { "enum": ["NBA","NFL","WNBA","NCAA-M","NCAA-W","MLB","NHL"] },
        "seasons": { "type": "array", "items": { "type": "string", "pattern": "^[0-9]{4}-[0-9]{2}$" } },
        "game_types": { "type": "array", "items": { "enum": ["REGULAR","PLAYOFF","PLAYIN","ELIMINATION","FINALS"] } }
      }
    },
    "population": { "type": "string", "minLength": 40 },
    "unit_of_analysis": { "enum": ["CREW_GAME","PLAYER_GAME","POSSESSION","MARKET_EVENT","DRAW"] },
    "outcome": {
      "type": "object",
      "required": ["variable","definition"],
      "properties": {
        "variable": { "type": "string" },
        "definition": { "type": "string", "minLength": 40 }
      }
    },
    "adjustment_set": {
      "type": "array",
      "minItems": 1,
      "items": { "type": "string" },
      "description": "Covariates the model conditions on. Anything omitted here must be named in known_limitations as a confounder risk."
    },
    "estimation_method": {
      "type": "object",
      "required": ["family","spec"],
      "properties": {
        "family": { "enum": ["HIERARCHICAL_BAYES","FREQUENTIST_GLM","MIXED_EFFECTS","NONPARAMETRIC","SIMULATION_ONLY"] },
        "spec": { "type": "string", "minLength": 40 }
      }
    },
    "prior": {
      "type": "object",
      "required": ["type","parameters","justification"],
      "properties": {
        "type": { "enum": ["BETA","NORMAL","HALF_NORMAL","STUDENT_T","NONE"] },
        "parameters": { "type": "object" },
        "justification": { "type": "string", "minLength": 60 }
      }
    },
    "uncertainty": {
      "type": "object",
      "required": ["interval_type","level"],
      "properties": {
        "interval_type": { "enum": ["CREDIBLE","CONFIDENCE","BOOTSTRAP"] },
        "level": { "type": "number", "minimum": 0.5, "maximum": 0.999 }
      }
    },
    "falsification_conditions": {
      "type": "array",
      "minItems": 1,
      "items": { "type": "string", "minLength": 40 },
      "description": "REQUIRED. What observation would show this baseline is wrong. A baseline with no falsification condition is refused admission."
    },
    "known_limitations": { "type": "array", "minItems": 2, "items": { "type": "string", "minLength": 30 } },
    "source_data_hashes": { "type": "array", "minItems": 1, "items": { "type": "string", "pattern": "^blake3:" } },
    "code_hash": { "type": "string", "pattern": "^blake3:" },
    "author": { "type": "string", "pattern": "^did:key:" },
    "proposed_utc": { "type": "string", "format": "date-time" },
    "adopted_utc": { "type": "string", "format": "date-time" },
    "status": { "enum": ["PROPOSED","UNDER_REVIEW","ADOPTED","DEPRECATED"] },
    "supersedes": { "type": "string" },
    "superseded_by": { "type": "string" },
    "review_refs": { "type": "array", "items": { "type": "string" } }
  }
}
```

The rule that matters: falsification_conditions is mandatory and non-empty. A baseline that cannot be shown wrong is not a baseline — it's a belief with a hash. Refused at admission with reason UNFALSIFIABLE_BASELINE.

## A.3 — Lifecycle

```
BASELINE.PROPOSE  →  BASELINE.REVIEW  →  BASELINE.ADOPT  →  [monitoring]  →  BASELINE.DEPRECATE
                                              │
                                              └──→ BASELINE.DRIFT_FLAG  (quarterly)
```

| Transition | Who | Gate |
|---|---|---|
| PROPOSE → UNDER_REVIEW | ENGINE author | Schema valid, falsification conditions present, all source_data_hashes resolve |
| UNDER_REVIEW → ADOPTED | Quorum per §B.4 | No unresolved REVIEW.DISSENT at adoption tier |
| ADOPTED → DEPRECATED | OPERATOR | Requires a superseded_by ref to an ADOPTED replacement, or a written deprecation reason ≥ 100 chars |

Deprecation does not invalidate prior verdicts. A verdict built on OFFICIATING_BASELINE_v2 stays sealed and tagged with that baseline hash forever. The Observatory shows the chain: verdict → baseline v2 → deprecated by v3 → drift flag. Anyone auditing can see exactly which model produced which finding, and when it was replaced.

## A.4 — Worked example: OFFICIATING_BASELINE_v3

```json
{
  "baseline_id": "BSL-OFFICIATING-CREW",
  "name": "NBA crew foul-differential baseline",
  "version": "v3.0.0",
  "scope": { "sport": "NBA", "seasons": ["2015-16","2016-17","2017-18","2018-19","2019-20","2020-21","2021-22","2022-23","2023-24","2024-25"], "game_types": ["REGULAR","PLAYOFF"] },
  "population": "All crew-games with complete official play-by-play and Last Two Minute report coverage; excludes games with fewer than 3 assigned officials or missing PBP segments.",
  "unit_of_analysis": "CREW_GAME",
  "outcome": {
    "variable": "foul_differential_per_100_poss",
    "definition": "(fouls called on home team − fouls called on away team) / possessions × 100, computed over possessions with |margin| ≤ 20 and clock within regulation, excluding intentional-foul and garbage-time windows per filter spec FILT-GT-v2."
  },
  "adjustment_set": [
    "pace", "score_margin_bucket", "garbage_time_indicator",
    "player_stature_index", "rest_days_home", "rest_days_away",
    "back_to_back_home", "back_to_back_away", "season_phase"
  ],
  "estimation_method": {
    "family": "HIERARCHICAL_BAYES",
    "spec": "Partial-pooled varying-intercept model with crew random effects; crews with fewer than 40 appearances shrink toward league mean."
  },
  "prior": {
    "type": "STUDENT_T",
    "parameters": { "df": 3, "loc": 0, "scale": 0.15 },
    "justification": "Heavy-tailed prior centered at zero effect; scale chosen so a 0.15 foul/100-possession crew effect is 1 SD, roughly the observed spread in published referee-analytics literature. Deliberately skeptical of large crew effects."
  },
  "uncertainty": { "interval_type": "CREDIBLE", "level": 0.95 },
  "falsification_conditions": [
    "A crew's 95% credible interval excludes zero in two non-overlapping seasons after Benjamini-Hochberg correction across all crews.",
    "Residual diagnostics show systematic miscalibration (posterior predictive p < 0.01) that is not resolved by adding a named adjustment_set covariate.",
    "An independent re-estimation on held-out seasons reverses the sign of a crew effect that was previously ADOPTED as PARTIALLY_SUPPORTED."
  ],
  "known_limitations": [
    "Player stature index is a proxy for star treatment and is estimated from usage, not officiating-specific data.",
    "Crew assignment is not random with respect to game importance; playoff crews are selected, which confounds any playoff-specific estimate.",
    "Last Two Minute reports cover only the final two minutes and only games within a 5-point window, so L2M-based subclaims have structurally lower power.",
    "No adjustment for in-game injury or ejection cascades."
  ],
  "source_data_hashes": ["blake3:9c1f…", "blake3:44ab…", "blake3:e07d…"],
  "code_hash": "blake3:5b22…",
  "author": "did:key:z6Mk…",
  "proposed_utc": "2025-09-01T00:00:00Z",
  "adopted_utc": "2025-10-14T17:22:00Z",
  "status": "ADOPTED",
  "supersedes": "BSL-OFFICIATING-CREW@v2.1.0",
  "review_refs": ["blake3:aa01…","blake3:aa02…","blake3:aa03…"]
}
```

## A.5 — Drift monitoring

Quarterly, an automated job re-estimates each ADOPTED baseline on newly available data and emits BASELINE.DRIFT_FLAG if any of these trip:

| Metric | Threshold | Meaning |
|---|---|---|
| Population shift | PSI > 0.20 | The games themselves changed; old baseline may not apply |
| Posterior predictive miscalibration | p < 0.01 | Model no longer fits |
| Parameter drift | \|Δ posterior mean\| > 1 prior SD | Effects moved substantially |
| Coverage degradation | 10% of required_data missing vs. baseline era | You're now imputing where you used to observe |

A drift flag does not auto-deprecate. It forces a BASELINE.REVIEW and, critically, it tags every new verdict built on that baseline with a baseline_drift: true field until the review resolves. The Observatory surfaces it. Sportsbooks will ask about it. That's the product working.
