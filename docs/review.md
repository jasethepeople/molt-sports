# Reviewer / Cosign Workflow

The engine can propose. It cannot publish. Publication requires human counter-signature, and the signature chain is public.

## B.1 — Reviewer roles

| Role code | Who | Signs off on |
|---|---|---|
| REVIEWER-STAT | Statistician / methodologist | Test choice, correction, power, baseline fit |
| REVIEWER-DOMAIN | Former official, ex-front-office, credentialed analyst | Domain plausibility, benign explanation adequacy |
| REVIEWER-COUNSEL | Attorney | Naming compliance, defamation exposure, tier appropriateness |
| REVIEWER-EXTERNAL | Independent observer, no commercial tie | Required only at Tier 4 |
| OPERATOR | Your org | Seals and publishes; cannot overrule a dissent |

Reviewers are identified in the public log only by role code and DID, e.g. REVIEWER-STAT:did:key:z6Mk…. Their real identity lives in the identity/ stream, unmaskable only at REGULATOR tier, which writes a permanent signed IDENTITY.UNMASK event visible to everyone as a fact of access even if the name itself stays gated.

## B.2 — Review event kinds

```json
REVIEW.ASSIGN     { "verdict_proposal":"blake3:…", "reviewer":"did:key:…", "role":"REVIEWER-STAT", "deadline_utc":"…" }
REVIEW.DISCLOSE   { "reviewer":"did:key:…", "conflicts":[…], "attestation":"No financial interest in outcome" }
REVIEW.ACCEPT     { "reviewer":"did:key:…", "assignment":"blake3:…" }
REVIEW.REFUSE     { "reviewer":"did:key:…", "assignment":"blake3:…", "reason":"…", "reason_code":"METHOD|SCOPE|COI|CAPACITY|DISAGREE" }
REVIEW.CONCUR     { "reviewer":"did:key:…", "assignment":"blake3:…", "note":"…", "conditions":[] }
REVIEW.DISSENT    { "reviewer":"did:key:…", "assignment":"blake3:…", "basis":"…", "cited_evidence":["blake3:…"] }
REVIEW.TIMEOUT    { "assignment":"blake3:…", "elapsed_days":14, "effect":"DOWNGRADE" }
```

REVIEW.DISCLOSE is mandatory and must precede REVIEW.ACCEPT. Disclosed conflicts:

```
BOOK_EMPLOYMENT | TEAM_EMPLOYMENT | ACTIVE_BETTING_EXPOSURE |
PRIOR_PUBLIC_STATEMENT | LITIGATION_PARTY | NONE
```

A reviewer with ACTIVE_BETTING_EXPOSURE on the game in question is automatically reassigned — no discretion, no exception. A reviewer with PRIOR_PUBLIC_STATEMENT (e.g., has publicly called the league fixed) may review, but the disclosure is attached to the sealed package and visible at MEDIA tier.

## B.3 — Dissent and refusal are published

This is the thing that makes the system real. Two rules:

1. A REVIEW.DISSENT cannot be removed, overridden, or hidden. It is appended to the sealed package at every tier. The published finding reads: "Verdict: PARTIALLY_SUPPORTED (2 concur, 1 dissent). Dissent basis: multiple-comparison family was defined post hoc; see cited evidence." Customers see the disagreement.
2. A REVIEW.REFUSE with reason_code: METHOD blocks sealing at that tier. Silence cannot produce SUPPORTED — a timeout defaults to DOWNGRADE.

The practical effect: you cannot publish a strong finding that a competent statistician objected to. That's not a policy you can quietly relax. It's in the seal gate.

## B.4 — Quorum by verdict tier

| Tier | Verdict | Required signatures | Cooling period | Notes |
|---|---|---|---|---|
| 0 | REFUTED, EVIDENCE.NULL | 1× STAT | 0d | Low-salience nulls ship fast; that's the volume product |
| 1 | UNTESTABLE | 1× STAT | 0d | Reason text is the deliverable |
| 2 | INCONCLUSIVE | 1× STAT | 0d | Includes power failures and coverage gaps |
| 3 | PARTIALLY_SUPPORTED | 1× STAT + 1× DOMAIN, both CONCUR | 7d | Default ceiling for anything touching officiating |
| 4 | SUPPORTED — general | 1× STAT + 1× DOMAIN + 1× COUNSEL, unanimous | 14d | Unanimity, no exceptions |
| 5 | SUPPORTED — touches OFFICIATING.* or LOTTERY.* | Tier 4 + 1× EXTERNAL, unanimous | 30d | The top of the ladder, and deliberately hard |

Nothing publishes at SUPPORTED touching officiating or lottery without four human signatures and a 30-day cooling period. If the finding is real, it survives 30 days. If it doesn't survive 30 days, it wasn't real.

Any REVIEW.DISSENT at Tier 4 or 5 → automatic downgrade to Tier 3 ceiling (PARTIALLY_SUPPORTED), published with the dissent attached. The finding still ships. It just ships honestly.

## B.5 — The seal gate, executable

ATTEST.SEAL admission checks, in order. (Also listed in docs/validator.md.)

| # | Check | Reject reason |
|---|---|---|
| 1 | All required roles assigned per tier | QUORUM_INCOMPLETE |
| 2 | Every assignee has a REVIEW.DISCLOSE preceding REVIEW.ACCEPT | COI_UNDISCLOSED |
| 3 | No assignee has ACTIVE_BETTING_EXPOSURE on this event | CONFLICT_INELIGIBLE |
| 4 | Required CONCUR count met, unanimity where tier demands | CONCUR_INSUFFICIENT |
| 5 | Zero unresolved REFUSE with reason_code: METHOD | METHOD_REFUSAL_BLOCKS_SEAL |
| 6 | Cooling period elapsed since last CONCUR | COOLING_PERIOD_ACTIVE |
| 7 | Verdict tier ≤ quorum tier achieved | TIER_EXCEEDS_QUORUM |
| 8 | All DISSENT refs attached | DISSENT_SUPPRESSED |
| 9 | Baseline status == ADOPTED and no active drift flag (or drift flag attached) | BASELINE_NOT_ADOPTED / DRIFT_UNDISCLOSED |
| 10 | accuses_individual === false, naming scan clean | ACCUSATION_ATTEMPT / NAMING_PROHIBITED |

Fail 8, 9, or 10 and it's not a downgrade — it's a quarantine with the reason published. Those three are integrity violations, not workflow friction.

## B.6 — Timeout and escalation

Default assignment window: 14 days. On expiry, REVIEW.TIMEOUT fires automatically and the effect is contract-frozen:

```
STAT timeout      → DOWNGRADE (verdict cannot exceed INCONCLUSIVE)
DOMAIN timeout    → DOWNGRADE (cannot exceed INCONCLUSIVE)
COUNSEL timeout   → HOLD (cannot publish; no downgrade, just blocked)
EXTERNAL timeout  → DOWNGRADE (cannot exceed PARTIALLY_SUPPORTED)
```

The asymmetry is deliberate: counsel silence blocks, everyone else's silence downgrades. You should never be able to publish past a lawyer by waiting them out, and you should never be able to publish a strong claim past an absent statistician.

Two timeout cycles on the same assignment → OPERATOR must either reassign to a new DID or publish at the downgraded tier with the timeout history attached.

## B.7 — What the customer actually receives

The sealed package manifest:

```json
{
  "package_id": "PKG-…",
  "verdict_tier": 3,
  "verdict": "PARTIALLY_SUPPORTED",
  "confidence": 0.61,
  "baseline": { "ref": "BSL-OFFICIATING-CREW@v3.0.0", "hash": "blake3:…", "drift_flag": false },
  "signatures": [
    { "role": "REVIEWER-STAT",   "did": "did:key:z6Mk…", "action": "CONCUR",  "at": "…" },
    { "role": "REVIEWER-DOMAIN", "did": "did:key:z6Mk…", "action": "CONCUR",  "at": "…" },
    { "role": "REVIEWER-STAT",   "did": "did:key:z6Mk…", "action": "DISSENT",
      "basis": "Family defined post hoc; FWER not controlled across the two seasons tested.",
      "cited_evidence": ["blake3:…"] }
  ],
  "cooling_elapsed": "7d",
  "limitations": [ "…", "…" ],
  "benign_unresolved": [ "Home-team travel advantage not fully separable from crew assignment in this window." ],
  "replay": { "command": "docker run ghcr.io/…", "expected_output_hash": "blake3:…" },
  "notice": "Probabilistic finding, not an accusation. One reviewer dissented; see signatures.",
  "bundle_hash": "blake3:…"
}
```

A sportsbook's counsel reads that and knows exactly what they're standing on. A regulator reads the dissent and knows you didn't bury it. A sharp bettor reads benign_unresolved and prices the uncertainty themselves. Nobody has to trust you — they can verify you.

---

## Where this leaves the whole system

| Layer | Status |
|---|---|
| Transparency kernel | Built — molt-show / the-room |
| Event taxonomy | Specified, contract v1.1.0 |
| Admission rules | 18 executable checks, first-fail quarantine |
| Baselines | Versioned, falsifiable, drift-monitored |
| Human signoff | Quorum-gated, dissent-published, cooling-period enforced |
| Observable to customers | Read-only, Merkle-proofed, tier-gated |

The remaining unbuilt pieces are the sports ontology implementation (the actual statistical tests behind each claim_family) and the BYOK model layer wiring customer keys into CLAIM.SUBCLAIM / CHALLENGE.BENIGN generation only. Everything upstream and downstream of those two is now specified.
