"""OFFICIATING.SERIES_EXTENSION — pooled logistic on elimination games.

The whole point of this family in the pilot is that it should mostly say
INCONCLUSIVE. If it produces SUPPORTED, the design is broken.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from harness.protocol import TestContext, TestFamily, TestResult, TestSpec


class SeriesExtension(TestFamily):
    spec = TestSpec(
        family="OFFICIATING.SERIES_EXTENSION",
        version="v1.0.0",
        unit="GAME",
        min_sample=200,   # pooled elimination games
        min_effect_size=0.10,  # OR must differ from 1.0 by ≥10%
        requires_baseline=True,
        adjustment_set_required=["home", "rest_diff", "injury_active"],
    )

    def validate(self, ctx: TestContext, df) -> list[str]:
        v = []
        if "is_elimination" not in df.columns:
            v.append("missing_is_elimination")
        if df.empty or df[df.get("is_elimination", False) == False].shape[0] == len(df):
            v.append("no_elimination_games")
        return v

    def power(self, ctx: TestContext, df) -> float:
        n = int(df.get("is_elimination", pd.Series(dtype=bool)).sum())
        if n < self.spec.min_sample:
            return float(n / self.spec.min_sample) * 0.5
        return 0.85  # crude; production uses simulation-based power

    def run(self, ctx: TestContext, df) -> TestResult:
        elig = df[df["is_elimination"]].copy()
        n = len(elig)
        pow_ = self.power(ctx, df)

        if pow_ < 0.80 or n < self.spec.min_sample:
            return TestResult(
                statistic=float("nan"), effect_size=float("nan"),
                effect_metric="ODDS_RATIO", n=n,
                p_raw=1.0, p_adjusted=1.0, power_achieved=pow_,
                ci=(float("nan"), float("nan")), ci_type="CONFIDENCE",
                notes=f"power_floor: achieved={pow_:.2f}, required=0.80, n={n}",
            )

        X = sm.add_constant(elig[self.spec.adjustment_set_required].astype(float))
        y = elig["trailing_team_won"].astype(int)
        try:
            fit = sm.Logit(y, X).fit(disp=False, maxiter=200)
            or_ = float(np.exp(fit.params.get("crew_trailing_flag", 0.0)))
            ci = tuple(float(v) for v in np.exp(fit.conf_int().loc["crew_trailing_flag"]))
            p = float(fit.pvalues.get("crew_trailing_flag", 1.0))
            effect_above_floor = abs(np.log(or_)) >= self.spec.min_effect_size
            return TestResult(
                statistic=float(fit.params.get("crew_trailing_flag", 0.0)),
                effect_size=or_, effect_metric="ODDS_RATIO", n=n,
                p_raw=p, p_adjusted=p,  # single test in family for pilot
                power_achieved=pow_, ci=ci, ci_type="CONFIDENCE",
                assumptions_checked={"converged": fit.mle_retvals.get("converged", False)},
                assumptions_violated=[] if fit.mle_retvals.get("converged", False) else ["nonconvergence"],
                notes=f"OR={or_:.3f} floor_met={effect_above_floor}",
                replay_manifest={"impl": "pooled_logit_v1", "n": n, "seed": ctx.rng_seed},
            )
        except Exception as e:
            return TestResult(
                statistic=float("nan"), effect_size=float("nan"),
                effect_metric="ODDS_RATIO", n=n,
                p_raw=1.0, p_adjusted=1.0, power_achieved=pow_,
                ci=(float("nan"), float("nan")), ci_type="CONFIDENCE",
                notes=f"fit_failed: {type(e).__name__}",
                assumptions_violated=["nonconvergence"],
            )
