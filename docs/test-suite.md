# Statistical Test Suite, Per Claim Family

Every subclaim resolves to exactly one registered test spec. The spec is part of the frozen contract; the engine cannot invent a test on the fly. Each row below defines unit of analysis, test, effect metric, minimum power gate, the confounders that must be in the adjustment set, and — critically — what a NULL looks like, because that's the artifact you'll ship most often.

## A.1 — Cross-cutting rules

| Rule | Value |
|---|---|
| Multiple-comparison family | Defined before testing, at CLAIM.DECOMPOSE time, capped at 200 |
| Correction | Benjamini–Hochberg at FDR 0.01, Bonferroni secondary gate on any SUPPORTED promotion |
| Power floor | 0.80 to leave INCONCLUSIVE; below that, verdict is INCONCLUSIVE with power cited |
| Effect floor | Family-specific min_effect_size_floor; below floor → REFUTED even if p is tiny |
| Reproducibility | Every test emits EVIDENCE.REPLAY_PROOF; non-deterministic test → quarantine |
| Held-out validation | Any SUPPORTED requires sign stability on a holdout season the baseline wasn't fit on |
| Priors | Skeptical by contract: Beta(1,4) for rates, StudentT(3,0,0.15) for effects |

## A.2 — The family register

### OFFICIATING.CREW_TENDENCY

| Field | Spec |
|---|---|
| Unit | CREW_GAME |
| Test | Hierarchical Bayes varying-intercept, crew random effects, partial pooling |
| Outcome | Foul differential per 100 possessions, garbage time excluded |
| Effect metric | Posterior mean crew intercept ÷ prior scale (standardized) |
| Baseline | BSL-OFFICIATING-CREW@v3.0.0 |
| Min sample | 40 crew-games per crew; crews below threshold shrink to league mean |
| Confounders | pace, margin bucket, rest, back-to-back, player stature, season phase |
| NULL | All crew 95% credible intervals contain zero after BH; or ≥80% of crews shrink below 0.5 SD |
| SUPPORTED requires | CI excludes zero, holdout sign stable, benign ruled out, effect ≥ floor |

### OFFICIATING.SERIES_EXTENSION

| Field | Spec |
|---|---|
| Unit | Elimination game (playoff series, down 3-1, 3-2, etc.) |
| Test | Logistic regression, crew random effects, pooled across seasons |
| Outcome | P(trailing team wins) |
| Effect metric | Odds ratio vs. league elimination-game baseline |
| Baseline | BSL-ELIMINATION-BASE@v2 |
| Min sample | 200 elimination games pooled — single-season testing is forbidden by contract |
| Confounders | home court, rest differential, injury status at tip, series score, travel |
| NULL | OR 95% CI contains 1.0 across all pooled windows |
| SUPPORTED requires | OR CI excludes 1, ≥3 independent seasons show same direction, benign (home court, rest) fully separable |
| Honest expectation | This family will usually return INCONCLUSIVE on power. That's the finding. |

### OFFICIATING.STAR_DIFFERENTIAL

| Field | Spec |
|---|---|
| Unit | PLAYER_GAME |
| Test | Mixed-effects model, player random effects, stature-index interaction |
| Outcome | Free-throw rate per shot attempt, controlling for shot location mix |
| Effect metric | Differential (stars − matched non-stars), standardized |
| Baseline | BSL-STAR-STATURE@v1 |
| Min sample | 500 player-games per stature tier |
| Confounders | usage, drive rate, shot location, defender quality, game state |
| NULL | Differential CI contains zero once shot-location and drive-rate are in the model |
| Critical caveat | Bias ≠ rigging. A positive result here is evidence of whistle bias, not intent. The verdict narrative is contract-forbidden from using intent language. |

### OFFICIATING.L2M_CONTRADICTION

| Field | Spec |
|---|---|
| Unit | L2M-report call |
| Test | Binomial vs. expected error rate, crew-stratified |
| Outcome | Rate of "incorrect" calls in L2M reports |
| Effect metric | Risk difference vs. league L2M error rate |
| Min sample | 300 L2M calls per crew |
| Confounders | margin, clock, call type, review availability |
| NULL | Error rate within expected band |
| Structural limitation | L2M covers only last 2 min of ≤5-point games — selection is severe and must be named in limitations |

### MARKET.PRE_EVENT_DRIFT

| Field | Spec |
|---|---|
| Unit | MARKET_EVENT |
| Test | Event study: abnormal line movement in windows before public information timestamp |
| Outcome | Absolute line move vs. expected move distribution |
| Effect metric | Abnormal return, z-scored against market's own baseline vol |
| Min sample | 100 events per market type |
| Confounders | injury news timing, public betting volume, sharp money flow, book limits |
| NULL | Movement distribution indistinguishable from pre-event baseline |
| The hard distinction | Sharp money moving a line is not manipulation. SUPPORTED requires the movement precede any information arrival AND correlate with a subsequently revealed event. Absent the second half, verdict caps at INCONCLUSIVE. |

### MARKET.PROP_CONCENTRATION

| Field | Spec |
|---|---|
| Unit | Prop market |
| Test | Exposure concentration vs. empirical null distribution of concentration |
| Outcome | HHI / Gini of liability on a single micro-event |
| Effect metric | Concentration percentile |
| Min sample | 50 comparable props |
| NULL | Concentration within 95th percentile of empirical distribution |
| Why this family matters | Micro-event fixing (one pitch, one rebound) is where integrity risk concentrates. This is the family most likely to produce a genuine flag. |

### MARKET.CROSS_BOOK_DIVERGENCE

| Field | Spec |
|---|---|
| Unit | Book-pair × event |
| Test | Variance-ratio test on price dispersion vs. efficient-market expectation |
| Outcome | Cross-book price spread |
| Effect metric | Dispersion ratio |
| NULL | Dispersion consistent with independent pricing + noise |
| Caveat | Books have different risk appetites and customer bases. Divergence is weak evidence on its own; it can only support a subclaim, never stand alone. |

### ROTATION.INCENTIVE_DEVIATION

| Field | Spec |
|---|---|
| Unit | Substitution event |
| Test | Compare observed rotation to a win-probability-maximizing counterfactual |
| Outcome | Deviation from expected minutes allocation |
| Effect metric | Win-probability cost of observed vs. optimal rotation |
| Min sample | 30 games per coach-team-season |
| NULL | Deviation within historical variance of coaches who were not suspected of anything |
| Hardest family | Requires estimating a counterfactual coach. Every model choice is contestable. Cap at PARTIALLY_SUPPORTED unless multiple counterfactual specs converge. |

### TEMPORAL.CLOCK_ANOMALY

| Field | Spec |
|---|---|
| Unit | Possession / timing event |
| Test | Sequence analysis against timing-tolerance null |
| Outcome | Clock/possession deviation beyond mechanical tolerance |
| NULL | Deviations within stadium-level measurement error |
| Note | Mostly a data-quality detector. Real flags here usually indicate feed errors, not fixing. |

### LOTTERY.ODDS_ANOMALY

| Field | Spec |
|---|---|
| Unit | DRAW (one per year) |
| Test | Exact test of outcome vs. pre-draw odds, pooled across N draws |
| Power reality | You get one observation per year. Even 10 years of draws is underpowered for anything but extreme deviation. This family will return INCONCLUSIVE almost always, and the honest product says so loudly. |
| NULL | Outcome distribution consistent with stated odds |

### STRUCTURAL.REST_ASYMMETRY

| Field | Spec |
|---|---|
| Unit | TEAM_GAME |
| Test | Compare actual rest-advantage distribution to randomized-schedule null |
| Outcome | Rest differential |
| NULL | Distribution consistent with random scheduling given arena and broadcast constraints |
| Caveat | Schedule asymmetry is often explained by broadcast windows and arena availability. Benign explanation is strong and must be ruled out explicitly. |

### SCRIPT.PREDETERMINED_TOTALITY

| Field | Spec |
|---|---|
| Test | None. By construction. |
| Contract behavior | CLAIM.DECOMPOSE must classify UNTESTABLE; validator refuses any SUBCLAIM with this family that isn't so classified |
| Output | VERDICT.UNTESTABLE with a written reason: no operationalization exists whose falsification would be accepted — contrary observations are absorbed into the hypothesis, so no test can discriminate |
| Why this is the most important row | The strongest form of the belief gets a real, signed, published verdict too. Not mocked. Not confirmed. Classified. That's the product. |

## A.3 — Why most outputs will be INCONCLUSIVE, and why that sells

Look at the power floors. Series extension needs 200 pooled elimination games. Lottery gets one draw a year. L2M has severe selection. The honest output distribution across a season is roughly:

- REFUTED / EVIDENCE.NULL — ~55%
- INCONCLUSIVE (power, coverage, method disagreement) — ~35%
- UNTESTABLE — ~7%
- PARTIALLY_SUPPORTED — ~2.5%
- SUPPORTED — ~0.5%, and almost never touching SCRIPT or LOTTERY

A sportsbook's counsel wants that 55% null pile badly — it's liability defense. A regulator wants the UNTESTABLE classifications because they close files. A sharp bettor wants the 2.5% and the benign_unresolved field. The null results are the volume business.
