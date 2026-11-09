# Sports Integrity Event Taxonomy (molt-native)

The rule stays the same as molt-show: the log is the truth. Every assertion—a data feed, a claim, a challenge, a finding—is a signed, hash-chained, append-only event. Nothing exists outside the log. No verdict is ever edited; it's superseded by a later verdict event.

---

## 1. The envelope (every event, no exceptions)

```json
{
  "event_id": "blake3:...",
  "prev": "blake3:...",
  "stream": "sports/nba/2024-25/game/0042400301",
  "kind": "CLAIM.SUBCLAIM",
  "actor": "did:key:...",
  "role": "ENGINE|OPERATOR|REVIEWER|PUBLIC",
  "ts_utc": "2025-03-11T02:14:09.113Z",
  "payload": { },
  "refs": ["blake3:..."],
  "sig": "ed25519:..."
}
```

Hard rules baked into the schema:

- kind is a closed enum. Unknown kinds are quarantined, not accepted.
- refs must resolve. A verdict referencing a missing evidence hash fails admission.
- ts_utc is monotonic per stream. Backdated events are rejected.
- Every event carries model_versions[] when any LLM touched it.

---

## 2. WORLD — genesis and contracts

| Kind | Purpose |
|---|---|
| WORLD.GENESIS | Opens a season or game world. Declares the frozen contract hash. |
| WORLD.ENTITY_REGISTER | Registers a role-coded entity: CREW-2024-017, TEAM-BOS, OFFICIAL-ENT-04. |
| WORLD.CONTRACT_FREEZE | Byte-identical freeze of claim categories, thresholds, and verdict ladder. Any change requires a new world. |
| WORLD.BASELINE_ADOPT | Adopts a named baseline model spec (e.g., OFFICIATING_BASELINE_v3, prior = strongly skeptical). Baselines are versioned artifacts, never implicit. |

Redaction discipline is a schema rule, not a policy: ENTITY_REGISTER stores role codes. Human identity lives in a separate IDENTITY.UNMASK stream with its own access control and its own audit log. The integrity transcript is name-free by construction.

---

## 3. INGEST — provenance before analysis

| Kind | Purpose |
|---|---|
| INGEST.SOURCE_SNAPSHOT | Hash + timestamp + fetch method for one source (official PBP, video, betting feed, sensor). This is what makes retroactive league edits detectable. |
| INGEST.SOURCE_DISCREPANCY | Two sources disagree on the same fact. Emitted automatically. Never smoothed over. |
| INGEST.SOURCE_REVISION | A source changed after the fact. Records both hashes and the delta. |
| INGEST.COVERAGE_GAP | Missing data. First-class event, because absence of data is itself evidence about what can be tested. |

---

## 4. CLAIM — decomposition is the product

| Kind | Purpose |
|---|---|
| CLAIM.ROOT | The raw public assertion, verbatim and attributed. "Told before game one who'd win it all." "The refs extend series." "The lottery is managed." |
| CLAIM.DECOMPOSE | Splits a root claim into N sub-claims, each tagged TESTABLE / UNTESTABLE / TESTIMONY_ONLY. This event is the deliverable. |
| CLAIM.SUBCLAIM | One operationalized hypothesis with an explicit null. |
| CLAIM.TESTIMONY | A witnessed public statement (Shaq's hotel story, Lin's fourth-quarter pull, Hodges' assertion, Cuban on 2006). Catalogued as an artifact. Its presence is never evidence the claim is true—the schema requires a weight: "testimony" field and forbids it from being referenced by a VERDICT as proof. |

### Sub-claim families (closed enum at freeze)

| Family | Example sub-claim | Testable? |
|---|---|---|
| OFFICIATING.CREW_TENDENCY | Crew X's foul differential deviates from baseline at α-corrected significance | Yes |
| OFFICIATING.SERIES_EXTENSION | Trailing-team win rate in elimination games correlates with crew assignment | Yes |
| OFFICIATING.STAR_DIFFERENTIAL | Whistle rate scales with player stature beyond model expectation | Yes |
| OFFICIATING.L2M_CONTRADICTION | Last-Two-Minute report contradicts called floor outcome at above-chance rate | Yes |
| MARKET.PRE_EVENT_DRIFT | Line moved before public information existed | Yes |
| MARKET.PROP_CONCENTRATION | Single-prop exposure anomalously concentrated on one micro-event | Yes |
| MARKET.CROSS_BOOK_DIVERGENCE | Books disagree in a pattern inconsistent with independent pricing | Yes |
| ROTATION.INCENTIVE_DEVIATION | Substitution pattern contradicts coaching-incentive baseline | Yes |
| TEMPORAL.CLOCK_ANOMALY | Timing/possession anomalies beyond tolerance | Yes |
| LOTTERY.ODDS_ANOMALY | Outcome distribution deviates across N draws | Yes |
| STRUCTURAL.REST_ASYMMETRY | Schedule/rest advantage concentrates non-randomly | Yes |
| SCRIPT.PREDETERMINED_TOTALITY | "The entire thing is scripted" | No — emits UNTESTABLE |

That last row is the whole point. The strong version of the belief gets a verdict too: UNTESTABLE, with a written reason. Not mocked, not confirmed. Classified.

---

## 5. EVIDENCE — deterministic only

| Kind | Purpose |
|---|---|
| EVIDENCE.STAT_TEST | Test name, statistic, effect size, raw + multiple-comparison-adjusted value, α, family-wise method |
| EVIDENCE.SIMULATION | N sims, null distribution hash, observed percentile |
| EVIDENCE.CAUSAL_ESTIMATE | Method (DiD / IV / RDD), identifying assumption, sensitivity bound |
| EVIDENCE.BASELINE_COMPARISON | Observed vs. adopted baseline |
| EVIDENCE.REPLAY_PROOF | Code hash + input hash + output hash. Rerunnable by anyone. |
| EVIDENCE.NULL | A test that found nothing. Explicitly emitted, never omitted. |

Enforcement: VERDICT events may only reference EVIDENCE.* and INGEST.*. Any verdict citing an LLM narrative event fails admission. This is the wall between hypothesis and proof, encoded rather than promised.

---

## 6. CHALLENGE — the benign explanation gets equal billing

| Kind | Purpose |
|---|---|
| CHALLENGE.BENIGN | Plausible non-nefarious cause. Must cite evidence or be tagged SPECULATIVE and cannot downgrade a verdict on its own. |
| CHALLENGE.METHODOLOGICAL | Baseline wrong, multiple comparisons uncorrected, power insufficient |
| CHALLENGE.DATA_QUALITY | Source unreliable, coverage gap, revision invalidates test |
| CHALLENGE.ALTERNATIVE_MODEL | A different defensible specification produces a different result |

LLM output lands here and nowhere else. A model that argues "this is suspicious" emits CLAIM.SUBCLAIM; a model that argues "this is just pace" emits CHALLENGE.BENIGN with SPECULATIVE unless evidenced.

---

## 7. VERDICT — the ladder, including the honest dead end

| Verdict | Meaning |
|---|---|
| SUPPORTED | Reproducible, survives challenges, benign explanation ruled out |
| PARTIALLY_SUPPORTED | Holds under some defensible specs, not all |
| INCONCLUSIVE | Insufficient power, data, or methods disagree |
| REFUTED | Tested, did not hold |
| UNTESTABLE | Cannot be operationalized; reason required |

Every verdict carries confidence, evidence_refs[], challenges_considered[], and limitations[]. No verdict may name an individual. Role codes only.

---

## 8. ATTEST — how a finding becomes publishable

| Kind | Purpose |
|---|---|
| ATTEST.PROPOSAL | Engine proposes a verdict package for review |
| ATTEST.COSIGN | Independent reviewer signs (statistician, former official, counsel) |
| ATTEST.SEAL | Package frozen; hash published |
| ATTEST.PUBLISH | Sealed package released at a tier (public / book / regulator) |
| ATTEST.SUPERSEDE | A later verdict replaces an earlier one—appended, never edited |
| ATTEST.RETRACT | A published finding withdrawn with reason. Visible forever. |

---

## 9. QUARANTINE — molt's rule, applied to sports

Failed admission emits QUARANTINE with digest and reason only, exactly as the-room does. Rejected: unsigned feeds, unknown event kinds, backdated timestamps, verdicts citing testimony as proof, verdicts naming individuals, uncorrected multiple comparisons above the family threshold.

Quarantined events are readable in the Observatory. You can see what got refused and why. That's the transparency product.

---

## 10. What the flow looks like — the hotel story

1. CLAIM.ROOT — "A coach told staff to book Finals hotels in the first round." Attributed, verbatim.
2. CLAIM.DECOMPOSE — 4 sub-claims: A (testimony recorded, TESTIMONY_ONLY), B (series-extension pattern exists, TESTABLE), C (crew assignment correlates with extension, TESTABLE), D ("the league scripts champions," UNTESTABLE).
3. EVIDENCE.STAT_TEST + EVIDENCE.SIMULATION on B and C.
4. CHALLENGE.BENIGN — "Confident teams plan travel; hotel demand correlates with team quality, not foreknowledge."
5. VERDICT — B: INCONCLUSIVE; C: PARTIALLY_SUPPORTED; D: UNTESTABLE; A: TESTIMONY_ONLY, not evidence.
6. ATTEST.COSIGN → SEAL → PUBLISH.

Output the customer reads: "Three of four parts of this claim don't survive contact with the data. One part does, weakly. The totality claim can't be tested. Here's the rerunnable code."

That's not debunking. That's not confirming. That's the only thing in this market nobody else sells.

---

## Guardrails encoded in the schema, not the policy doc

- Accusation is structurally impossible — no field can hold an individual's name in a verdict.
- Testimony can never become proof — enforced by reference rules.
- Null results are mandatory events, not absences.
- LLM output is quarantined to hypothesis and challenge kinds.
- Every published claim is rerunnable via EVIDENCE.REPLAY_PROOF.
- Self-correction is visible via SUPERSEDE / RETRACT.

---

## Honesty and the disclaimer

Exactly right—and it's more than a disclaimer, it's a design principle. The same honesty that makes this conversation useful is what makes your app credible.

The irony is sharp: an app whose entire purpose is verifying claims must be the most transparent thing in the room about its own limits. If you hide uncertainty, you become the thing you're fighting.

### Where the disclaimer belongs (and what it should actually say)

Bottom of every output, not buried in a ToS:

"This analysis is probabilistic, not definitive. AI models and statistical methods can produce errors, including false positives and false negatives. Every finding ships with its evidence, method, and confidence level—verify before acting. We test claims; we do not adjudicate guilt."

Per-claim confidence tags, not just one footer:

- Established — reproducible, multiple sources agree
- Probable — statistically significant, benign explanation unlikely but not ruled out
- Inconclusive — data insufficient or methods disagree
- Refuted — tested and did not hold

A visible "known limitations" panel:

- Data source latency and versioning gaps
- Model version and prompt used (reproducibility)
- Sample size and statistical power for this specific claim
- What we could not test and why

### The three audiences who need this differently

1. The sharp bettor doesn't want a disclaimer—they want the confidence interval and the raw evidence. Give them the full artifact.
2. The sportsbook's legal team wants the disclaimer in writing, on every report, with your methodology attached. It's their liability shield as much as yours.
3. The regulator wants to see that you flag your own uncertainty before they ask. That's what separates a standards body from a tip sheet.

### The line that should be your company's actual ethos

"We can be wrong, and we'll show you exactly where and how. That's the point."

Everyone else in this space sells certainty. You sell calibrated honesty—which is the only thing the gambling market actually trusts, because they've been burned by certainty their whole lives.

Put it at the bottom of every screen, every report, every API response. Make it the brand. An integrity product that won't admit uncertainty isn't an integrity product—it's just another confident liar.
