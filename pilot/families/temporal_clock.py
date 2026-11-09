"""TEMPORAL.CLOCK_ANOMALY — data-quality canary. Not an integrity family."""
from __future__ import annotations

import numpy as np
import pandas as pd

from harness.protocol import TestContext, TestFamily, TestResult, TestSpec

MECHANICAL_TOLERANCE_SEC = 0.5


class ClockAnomaly(TestFamily):
    spec = TestSpec(
        family="TEMPORAL.CLOCK_ANOMALY",
        version="v1.0.0",
        unit="POSSESSION",
        min_sample=500,
        min_effect_size=0.0,
        requires_baseline=False,
        adjustment_set_required=[],
    )

    def validate(self, ctx, df) -> list[str]:
        return [] if "timing_delta_sec" in df.columns and len(df) else ["empty_input"]

    def power(self, ctx, df) -> float:
        return 1.0 if len(df) >= self.spec.min_sample else 0.0

    def run(self, ctx, df) -> TestResult:
        d = np.abs(df["timing_delta_sec"].to_numpy(dtype=float))
        flag_rate = float((d > MECHANICAL_TOLERANCE_SEC).mean())
        return TestResult(
            statistic=flag_rate, effect_size=flag_rate, effect_metric="RAW_DIFF",
            n=int(len(d)), p_raw=1.0, p_adjusted=1.0, power_achieved=1.0,
            ci=(flag_rate, flag_rate), ci_type="BOOTSTRAP",
            notes=f"flag_rate={flag_rate:.5f} (threshold 0.005)",
            replay_manifest={"impl": "clock_canary_v1", "seed": ctx.rng_seed},
        )
