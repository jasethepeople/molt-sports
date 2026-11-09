"""Frozen test-harness protocol. Do not modify without a contract bump."""
from __future__ import annotations

from typing import Literal, Protocol
from pydantic import BaseModel, Field


class TestSpec(BaseModel):
    family: str
    version: str
    unit: Literal["CREW_GAME", "PLAYER_GAME", "POSSESSION",
                  "MARKET_EVENT", "DRAW", "TEAM_GAME", "GAME"]
    min_sample: int
    min_effect_size: float
    requires_baseline: bool
    adjustment_set_required: list[str]
    alpha_familywise: float = 0.01


class BaselineRef(BaseModel):
    baseline_id: str
    version: str
    hash: str
    parameters: dict = Field(default_factory=dict)


class SourceSnapshotRef(BaseModel):
    source_type: Literal["OFFICIAL_PBP", "VIDEO", "BETTING_FEED",
                        "SENSOR", "L2M_REPORT", "PRESS_STATEMENT"]
    hash: str
    fetched_utc: str


class TestContext(BaseModel):
    subclaim_id: str
    stream: str
    baseline: BaselineRef | None = None
    inputs: list[SourceSnapshotRef] = Field(default_factory=list)
    adjustment_set: dict[str, list] = Field(default_factory=dict)
    rng_seed: int
    alpha: float
    family_size: int
    holdout_seasons: list[str] = Field(default_factory=list)
    # DataFrame handle is passed out-of-band via the runner; ctx only carries hashes.

    model_config = {"arbitrary_types_allowed": True}


class TestResult(BaseModel):
    statistic: float
    effect_size: float
    effect_metric: Literal["COHENS_D", "ODDS_RATIO", "RISK_DIFF", "RAW_DIFF"]
    n: int
    p_raw: float
    p_adjusted: float = 1.0
    power_achieved: float
    ci: tuple[float, float]
    ci_type: Literal["CREDIBLE", "CONFIDENCE", "BOOTSTRAP"]
    direction_stable_on_holdout: bool | None = None
    assumptions_checked: dict[str, bool] = Field(default_factory=dict)
    assumptions_violated: list[str] = Field(default_factory=list)
    notes: str = ""
    artifacts: dict[str, str] = Field(default_factory=dict)
    replay_manifest: dict = Field(default_factory=dict)
    per_unit: list[dict] = Field(default_factory=list)
    # each dict: {"unit_id": str, "effect_size": float, "p_adjusted": float,
    #             "verdict": "SUPPORTED"|"PARTIALLY_SUPPORTED"|"INCONCLUSIVE"|"REFUTED"}


class TestFamily(Protocol):
    spec: TestSpec

    def validate(self, ctx: TestContext, df) -> list[str]: ...
    def run(self, ctx: TestContext, df) -> TestResult: ...
    def power(self, ctx: TestContext, df) -> float: ...
