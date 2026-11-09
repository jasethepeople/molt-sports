# Test Harness Interface

One signature every family implements. The registry is only as honest as this contract, so it's frozen alongside the baselines. No family ships without passing the conformance suite.

## A.1 — The contract

```python
# molt/sports/harness/protocol.py
from typing import Protocol, Literal
from pydantic import BaseModel

class TestSpec(BaseModel):
    """Frozen metadata. Registered in contract, not invented at runtime."""
    family: str                        # "OFFICIATING.SERIES_EXTENSION"
    version: str                       # "v1.2.0" — bump = new contract
    unit: Literal["CREW_GAME","PLAYER_GAME","POSSESSION","MARKET_EVENT","DRAW","TEAM_GAME"]
    min_sample: int
    min_effect_size: float
    requires_baseline: bool
    adjustment_set_required: list[str]
    emits_null_kind: Literal["EVIDENCE.NULL"]

class TestContext(BaseModel):
    """Everything the test is allowed to touch. Nothing else."""
    subclaim_id: str
    stream: str
    baseline: BaselineRef | None       # resolved + hash-verified
    inputs: list[SourceSnapshotRef]    # every input hash-verified
    adjustment_set: dict[str, list]
    rng_seed: int                      # pinned; recorded in replay proof
    alpha: float
    family_size: int                   # for BH correction
    holdout_seasons: list[str]         # must be excluded from fit

class TestResult(BaseModel):
    """Structured output. Free-text goes in `notes` only, never in verdict path."""
    statistic: float
    effect_size: float
    effect_metric: Literal["COHENS_D","ODDS_RATIO","RISK_DIFF","RAW_DIFF"]
    n: int
    p_raw: float
    power_achieved: float
    ci: tuple[float, float]
    ci_type: Literal["CREDIBLE","CONFIDENCE","BOOTSTRAP"]
    direction_stable_on_holdout: bool | None
    assumptions_checked: dict[str, bool]
    assumptions_violated: list[str]
    notes: str                         # human-readable, NEVER parsed
    artifacts: dict[str, str]          # name -> blob hash (plots, diagnostics)

class TestFamily(Protocol):
    spec: TestSpec

    def validate(self, ctx: TestContext) -> list[str]:
        """Pre-flight: return list of contract violations. Empty = run."""
        ...

    def run(self, ctx: TestContext) -> TestResult:
        """Deterministic given (ctx, rng_seed). Must not read env or clock."""
        ...

    def replay_manifest(self, ctx: TestContext) -> dict:
        """Code hash, container ref, input hashes, expected output hash."""
        ...

    def power(self, ctx: TestContext) -> float:
        """Pre-test power estimate. Used to skip underpowered tests → INCONCLUSIVE."""
        ...
```

## A.2 — The rules that make it honest

| Rule | Enforcement |
|---|---|
| run() is pure | Harness rejects any test importing time, os.environ, random (except seeded numpy.random.Generator), socket |
| run() deterministic | Conformance suite runs each test 3× with same seed → byte-identical TestResult or test is rejected |
| validate() runs first | Non-empty return → no run(), emit EVIDENCE.NULL with reason: VALIDATION_FAILED |
| power() gates run() | Power < 0.80 → skip run(), emit VERDICT.INCONCLUSIVE with power cited. You cannot fish for significance on an underpowered test. |
| notes is never parsed | CI check greps for result.notes in verdict path — presence = build failure |
| Holdout is held out | run() receives holdout_seasons; harness asserts those rows aren't in inputs used for fit |
| Replay manifest required | No EVIDENCE.REPLAY_PROOF → harness refuses to emit EVIDENCE.STAT_TEST |

## A.3 — Conformance suite (every family must pass)

```
harness.conformance.test:
  T01 schema_valid
  T02 deterministic_3x
  T03 no_forbidden_imports
  T04 validate_catches_bad_input
  T05 power_gate_fires
  T06 null_emitted_on_underpower
  T07 replay_manifest_complete
  T08 holdout_exclusion_verified
  T09 adjustment_set_honored
  T10 notes_not_in_output_path
```

A family that fails any of these cannot be registered in the contract. The registry is a build artifact, not a wiki page.

## A.4 — The registry file

```json
{
  "registry_version": "1.0.0",
  "families": {
    "OFFICIATING.CREW_TENDENCY": {
      "impl": "molt.sports.families.officiating:crew_tendency",
      "spec_version": "v1.1.0",
      "conformance_hash": "blake3:…",
      "status": "ADOPTED"
    },
    "OFFICIATING.SERIES_EXTENSION": { "…": "…" },
    "SCRIPT.PREDETERMINED_TOTALITY": {
      "impl": "molt.sports.families.structural:untestable_by_construction",
      "spec_version": "v1.0.0",
      "status": "ADOPTED",
      "note": "Implements only validate() and returns UNTESTABLE with reason. run() raises by design."
    }
  }
}
```

SCRIPT.PREDETERMINED_TOTALITY ships as a real family with a real implementation that returns UNTESTABLE. It's the most-referenced family in the system and it has zero statistics. That's the product.
