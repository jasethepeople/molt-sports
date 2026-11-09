# molt-sports

A MOLT-native sports integrity event taxonomy: signed, hash-chained, append-only claims, evidence, challenges, and verdicts. The log is the truth. Nothing exists outside the log. No verdict is ever edited; it is superseded by a later verdict event.

The product is claim decomposition. A raw public assertion ("the refs extend series", "the lottery is managed", "the entire thing is scripted") is split into operationalized sub-claims, each tagged TESTABLE / UNTESTABLE / TESTIMONY_ONLY, tested against deterministic evidence, challenged by benign explanations, and given a verdict on a ladder that includes the honest dead end: UNTESTABLE, with a written reason. The strong version of the belief gets a verdict too. Not mocked, not confirmed. Classified.

## Honesty principle

This analysis is probabilistic, not definitive. AI models and statistical methods can produce errors, including false positives and false negatives. Every finding ships with its evidence, method, and confidence level — verify before acting. We test claims; we do not adjudicate guilt.

- Accusation is structurally impossible: no field can hold an individual's name in a verdict, and the validator refuses narrative containing proper names.
- Testimony can never become proof: enforced by reference rules, not policy.
- Null results are mandatory first-class events (EVIDENCE.NULL, VERDICT.REFUTED, VERDICT.UNTESTABLE, INGEST.COVERAGE_GAP), never absences.
- Dissent is published: a REVIEW.DISSENT cannot be removed, overridden, or hidden, and it is appended to the sealed package at every tier.
- LLM output is quarantined to hypothesis and challenge kinds (CLAIM.SUBCLAIM, CHALLENGE.BENIGN, CHALLENGE.ALTERNATIVE_MODEL). No model output can reach the verdict path.
- Every published claim is rerunnable via EVIDENCE.REPLAY_PROOF.

"We can be wrong, and we'll show you exactly where and how. That's the point."

## Layout

| Path | What it is |
|---|---|
| `contract/sports-integrity-v1.1.0.json` | The frozen contract: closed kind enums, claim families, thresholds, policy. Changing any enum or threshold requires a new world and a new contract hash. |
| `schemas/event.json` | The event envelope schema (every event, no exceptions). |
| `schemas/payloads/` | Kind-specific payload schemas: CLAIM.ROOT, CLAIM.DECOMPOSE, CLAIM.SUBCLAIM, EVIDENCE.STAT_TEST, EVIDENCE.REPLAY_PROOF, CHALLENGE.BENIGN, VERDICT. |
| `docs/taxonomy.md` | The event taxonomy: envelope, WORLD / INGEST / CLAIM / EVIDENCE / CHALLENGE / VERDICT / ATTEST / QUARANTINE, sub-claim families, the hotel-story flow, guardrails, and the disclaimer. |
| `docs/validator.md` | The 18 admission checks, in order (first failure wins, emits QUARANTINE.REJECTED), plus the ATTEST.SEAL gate. |
| `docs/observatory.md` | The Observatory query surface: auth matrix and all endpoints, with Merkle proofs on every response. |
| `docs/observatory-walkthrough.md` | The demo: a regulator opens a sealed finding cold, with no briefing, and decides whether to act. |
| `docs/baselines.md` | The baseline registry: artifact schema, lifecycle, the OFFICIATING_BASELINE_v3 worked example, drift monitoring. |
| `docs/review.md` | The reviewer/cosign workflow: roles, review event kinds, dissent/refusal rules, quorum by tier, seal gate, timeout/escalation, sealed package manifest. |
| `docs/test-suite.md` | The statistical test suite, per claim family (all 12), plus cross-cutting rules and the expected output distribution. |
| `docs/byok.md` | BYOK key handling and provider abstraction: envelope encryption, capability negotiation, deterministic-only fallback. |
| `docs/harness.md` | The test harness interface: one signature every family implements, conformance suite, registry. |
| `docs/trading-desk.md` | The Observatory front end: live desk, mute-with-audit, pre-game brief, escalation path, regulator queue, API contract. |
| `docs/pilot.md` | The week-one pilot: dataset, two families, synthetic injection test, acceptance criteria, failure table, deliverables, day-by-day plan. |
| `pilot/` | The pilot skeleton: frozen harness, two real family implementations (empirical-Bayes crew tendency, pooled-logistic series extension), a data-quality canary, a synthetic injection harness with sealed labels, a scoring report, determinism/replay checks, and the integrity check that refuses to score unless the frames provably match what the pilot saw. |

## Status

- Spec complete through contract v1.1.0, harness, pilot skeleton, and the integrity check.
- Transparency kernel built (molt-show, the-room). Everything else is specified, not implemented.
- Nothing is implemented beyond the pilot skeleton. The pilot code contains `# TODO(PILOT)` stubs for the network fetchers and canonical transformations; those are the real work of days 1–2.
- The week-one pilot is the next buildable piece: one dataset (ten NBA seasons), two families, one synthetic injection test, clear pass/fail. If the pilot comes back mostly null, that's a successful pilot and a publishable finding. If it comes back mostly flagged, the pilot failed.
- The pilot is the bridge between "the design is written down" and "the design is true." Build it next, before anything else.
