# Admission Validator (the quarantine rules, executable)

Run in this order. First failure wins and emits QUARANTINE.REJECTED with digest + reason only.

| # | Check | Reject reason |
|---|---|---|
| 1 | Schema valid against kind-specific payload | SCHEMA_INVALID |
| 2 | sig verifies over canonical event_id | SIG_INVALID |
| 3 | kind exists in contract enum | UNKNOWN_KIND |
| 4 | prev == current stream head | CHAIN_BREAK |
| 5 | ts_utc ≥ stream head ts_utc | BACKDATED |
| 6 | All refs resolve | DANGLING_REF |
| 7 | model_versions present if LLM-permitted kind | MISSING_MODEL_PROVENANCE |
| 8 | Verdict refs obey allowlist | FORBIDDEN_REFERENCE |
| 9 | No CLAIM.TESTIMONY / IDENTITY.UNMASK in verdict refs | TESTIMONY_AS_PROOF |
| 10 | family_size ≤ 200 and matches decompose sibling count | MULTIPLE_COMPARISON_VIOLATION |
| 11 | p_adjusted ≥ p_raw, alpha_used ≤ contract | UNCORRECTED_SIGNIFICANCE |
| 12 | SCRIPT.* subclaim classified UNTESTABLE | SCRIPT_TESTABILITY_VIOLATION |
| 13 | UNTESTABLE has a reason ≥ 40 chars | UNTESTABLE_NO_REASON |
| 14 | accuses_individual === false | ACCUSATION_ATTEMPT |
| 15 | narrative free of proper personal names | NAMING_PROHIBITED |
| 16 | VERDICT.SUPPORTED gate results all true | GATE_INCOMPLETE |
| 17 | EVIDENCE.REPLAY_PROOF.deterministic === true and present on any cited STAT_TEST | NON_REPRODUCIBLE |
| 18 | COVERAGE_GAP emitted if required_data unmet | SILENT_GAP |

## Conditional rules (encoded in the validator, not the schema)

- model_versions is required when kind ∈ contract.policy.llm_output_permitted_kinds. Absence → quarantine.
- Every key in testability_map marked UNTESTABLE must have an entry in untestable_reasons. No silent shrugs.
- If family.group == "SCRIPT", the parent CLAIM.DECOMPOSE must classify this subclaim UNTESTABLE. Enforced, not advised.
- p_adjusted ≥ p_raw. family_size must equal the sibling count in the same CLAIM.DECOMPOSE. alpha_used ≤ contract.thresholds.alpha_familywise. Missing replay_proof_ref → quarantine.
- CHALLENGE.BENIGN with status "EVIDENCED" requires non-empty evidence_refs that resolve to EVIDENCE.* or INGEST.*. SPECULATIVE with evidence_refs → quarantine. A SPECULATIVE challenge cannot be the sole basis for downgrading a verdict.
- VERDICT validator rules, non-negotiable:
  1. accuses_individual must be literally false, or the event is refused.
  2. Every evidence_refs entry must resolve to a permitted kind per contract.policy.verdict_may_reference_kinds. A ref to CLAIM.TESTIMONY or IDENTITY.UNMASK → quarantine with reason TESTIMONY_AS_PROOF / IDENTITY_LEAK.
  3. For kind: VERDICT.SUPPORTED, all of fdr_pass, fwer_pass, power_pass, benign_ruled_out, reproduced must be true.
  4. narrative is scanned against the entity_code_pattern allowlist — any capitalized proper name of a person → quarantine NAMING_PROHIBITED.

---

## The seal gate, executable

ATTEST.SEAL admission checks, in order:

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
