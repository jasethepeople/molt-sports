# BYOK Key Handling & Provider Abstraction

## B.1 — The architectural invariant

The single most important sentence in this section:

The customer's key is only ever used to generate hypotheses and challenges. It is structurally incapable of producing a verdict or evidence event.

The validator already enforces this — contract.policy.llm_output_permitted_kinds = [CLAIM.SUBCLAIM, CHALLENGE.BENIGN, CHALLENGE.ALTERNATIVE_MODEL]. A compromised key, a jailbroken prompt, a prompt-injected data feed, or a malicious provider cannot produce a published accusation, because there is no event kind the LLM can emit that reaches the verdict path. Key security becomes a data-confidentiality problem, not an integrity problem. That's a much smaller blast radius.

## B.2 — Threat model

| Threat | Vector | Control |
|---|---|---|
| Key theft by insider | Operator with DB access | Envelope encryption; DEK never leaves HSM boundary; KEK in KMS with per-tenant policy |
| Key leakage in logs | Prompt/response logging | Redaction pre-flight; logs store hashes and token counts, never plaintext keys |
| Cross-tenant key misuse | Bug in tenant routing | Tenant ID bound into DEK AAD; decryption fails on mismatch |
| Provider TOS violation | Single key serving multiple paying customers | One key per tenant, never shared. Contract-frozen. |
| Prompt injection → data exfil | Malicious content in ingested feed | Model sees only structured subclaims; never raw feeds, never identity stream |
| Provider sees sensitive queries | Third-party inference | Data minimization: no names, no entity unmasking, no raw play-by-play |
| Key revocation not honored | Stale cache | Revocation propagates in ≤60s; in-flight requests fail closed |
| Budget runaway | Loop or abuse | Per-tenant hard token caps + per-request caps + circuit breaker |

## B.3 — Key custody

Envelope encryption, per tenant:

```
KEK  ── AWS KMS / HashiCorp Vault Transit (never exported, per-tenant key policy)
 └─ DEK_tenant  ── AES-256-GCM, one per tenant, rotated 90d
     └─ ciphertext(key, provider, label)  ── stored; plaintext exists only in request scope
```

Storage record:

```json
{
  "tenant_id": "TNT-…",
  "key_id": "KEY-…",
  "provider": "anthropic",
  "label": "prod-primary",
  "ciphertext": "base64…",
  "iv": "base64…",
  "auth_tag": "base64…",
  "aad": "TNT-…|KEY-…|anthropic|v1",
  "dek_kms_ref": "arn:…",
  "fingerprint": "sha256:…",
  "created_utc": "…",
  "rotated_utc": "…",
  "revoked_utc": null,
  "last_used_utc": "…",
  "scopes": ["CLAIM.SUBCLAIM","CHALLENGE.BENIGN"]
}
```

Rules:

| Rule | Enforcement |
|---|---|
| Plaintext key never persisted | Memory only, zeroized after request via secrecy/zeroize |
| Key never in logs, traces, or error messages | Log scrubber rejects any 20+ char high-entropy string pre-write |
| AAD binds tenant + key + provider | Decryption fails on any mismatch — cross-tenant read is cryptographically impossible |
| Rotation | DEK 90d; provider key rotation prompted at 180d, forced at 365d |
| Revocation | Immediate delete of ciphertext + DEK; in-flight fails closed; KEY.REVOKED event signed to audit stream |
| Access to plaintext | Requires a signed KEY.DECRYPT audit event naming tenant, purpose, requesting service, and correlation ID |

The audit trail is the product feature. Every decryption is a signed event. A customer can query: "when was my key used, for what, and by which service?" That's a compliance deliverable you sell, not a cost center.

## B.4 — Provider abstraction

A single normalized interface. Adapters declare capabilities; the engine negotiates.

```python
class ModelAdapter(Protocol):
    provider: str
    def capabilities(self) -> Capabilities: ...
    def complete(self, req: CompletionRequest, key: SecretStr) -> CompletionResponse: ...
    def health(self) -> HealthStatus: ...

@dataclass(frozen=True)
class Capabilities:
    tool_calling: bool
    json_mode: bool
    structured_output: bool
    max_context: int
    max_output: int
    streaming: bool
    deterministic_seed: bool
    data_residency: tuple[str, ...]   # e.g. ("us","eu")
    retention_days: int | None        # provider's retention policy
```

Adapters shipped:

| Adapter | Notes |
|---|---|
| openai | JSON mode + tool calling; seed support for determinism |
| anthropic | Tool use; strict prompt-hash discipline |
| google | Vertex + AI Studio variants |
| azure-openai | Data residency + enterprise retention terms |
| bedrock | Multi-model, IAM-scoped |
| local (vLLM / Ollama) | Air-gapped tenants; no external egress |

Capability negotiation rule: if a tenant's key doesn't support structured_output or json_mode, the engine refuses to run that purpose rather than falling back to free-text parsing. Free-text parsing is where hallucinated accusations would come from. Fail closed.

Determinism: where the provider supports seeds, the engine pins them and records params_hash. Where it doesn't, the resulting hypothesis is tagged non_deterministic: true and cannot be cited by a verdict — only by a challenge. This preserves replayability.

## B.5 — Data minimization (what the model never sees)

The engine constructs the prompt from a sanitized projection, not raw data:

| Never sent to provider | Why |
|---|---|
| Player/coach/official names | Naming prohibition enforced before the model, not after |
| IDENTITY.UNMASK contents | Gated stream, never in prompt context |
| Raw play-by-play text | Injection surface; replaced by structured aggregates |
| Free-text press statements | Same; replaced by classified testimony metadata |
| Other tenants' data | Tenant isolation |
| Baseline parameters beyond needed summary | IP protection + minimization |

The projection looks like:

```json
{
  "subclaim": {
    "family": "OFFICIATING.SERIES_EXTENSION",
    "null": "P(trailing win) independent of crew assignment",
    "operationalization": "logistic regression, pooled 2015-2025, crew RE",
    "baseline_summary": { "odds_ratio": 1.04, "ci95": [0.91, 1.19], "n": 214 }
  },
  "task": "Propose benign alternative explanations. Cite only the provided evidence. Do not assert intent. Do not name individuals."
}
```

Entity codes (CREW-2024-017) may appear. Real names may not. The provider cannot leak what it never received.

## B.6 — Token governance

| Control | Default | Enforced |
|---|---|---|
| Per-tenant monthly token cap | Contract-set | Hard stop → BUDGET_EXHAUSTED, engine continues deterministically |
| Per-request cap | 8k in / 2k out | Reject oversized |
| Per-decompose hypothesis cap | 200 subclaims | Contract-frozen |
| Retry budget | 2 retries, exponential backoff | Circuit breaker per provider |
| Degradation ladder | full → reduced-context → deterministic-only | Ladder is explicit and logged |

The degradation ladder is the key design choice. When a customer's budget runs out or their provider is down, the engine does not stop — it drops to deterministic-only mode, continues producing evidence and null results, and simply skips hypothesis generation. The integrity product keeps working without the LLM. That's the architectural payoff of never putting the model in the verdict path.

## B.7 — LLM call audit (feeds model_versions[])

Every call emits a signed audit event:

```json
{
  "kind": "LLM.CALL",
  "tenant_id": "TNT-…",
  "key_id": "KEY-…",
  "provider": "anthropic",
  "model": "claude-…",
  "prompt_hash": "blake3:…",
  "params_hash": "blake3:…",
  "purpose": "CHALLENGE.BENIGN",
  "refs_subclaim": "SUB-…",
  "tokens_in": 3184,
  "tokens_out": 412,
  "latency_ms": 2140,
  "output_hash": "blake3:…",
  "non_deterministic": false,
  "seed": 42,
  "at_utc": "…"
}
```

This event is what populates the model_versions[] array on the emitted CHALLENGE.BENIGN. An auditor reading a published package can trace every hypothesis back to the exact model, prompt hash, and provider that generated it. Provenance through the LLM layer, not just the data layer.

## B.8 — Failover and isolation

| Scenario | Behavior |
|---|---|
| Provider 5xx | Retry ×2, then circuit-break, degrade to deterministic-only, log |
| Key revoked mid-flight | Fail closed, emit KEY.REVOKED, notify tenant, never substitute another key |
| Provider outage > 24h | Engine continues deterministic; hypothesis queue drains on recovery |
| Tenant A key hits Tenant B request | AAD mismatch → hard fail → TENANT_ISOLATION_VIOLATION alert |
| Customer wants zero external egress | Route to local adapter on their infrastructure; air-gapped supported |

Never, under any circumstance, fall back to a platform-owned key. That's the line that keeps you compliant with provider terms and keeps the BYOK promise real.

## B.9 — What the customer's dashboard shows

```
TENANT: TNT-…
Keys:    2 active (anthropic/prod-primary, openai/prod-secondary)
Usage:   412k / 2M tokens this month (20.6%)
Calls:   1,847 → 1,812 succeeded, 31 degraded, 4 failed
Purpose: CLAIM.SUBCLAIM 61% | CHALLENGE.BENIGN 34% | OTHER 5%
Audit:   [export signed LLM.CALL log]  [export KEY.DECRYPT log]
Mode:    FULL (deterministic-only fallback available)
```

That dashboard is a sales asset. A book's compliance team can hand it to their CISO.

---

## Where the system stands

| Layer | Status |
|---|---|
| Transparency kernel | Built (molt-show, the-room) |
| Event taxonomy | Frozen, contract v1.1.0 |
| Admission rules | 18 executable checks |
| Baselines | Versioned, falsifiable, drift-monitored |
| Human signoff | Quorum-gated, dissent-published, 30d cooling on top tier |
| Statistical test suite | Specified — 12 families, power floors, null definitions |
| BYOK layer | Specified — envelope encryption, capability negotiation, deterministic-only fallback |

What's left is implementation, not design: the Python/R test harness behind each family, the adapter SDK, and the Observatory front end.

The two things most likely to bite you in build:

1. ROTATION.INCENTIVE_DEVIATION will eat 40% of your engineering. The counterfactual coach model is genuinely hard and every reviewer will contest your spec. Ship it last, cap it at PARTIALLY_SUPPORTED, and say so upfront.
2. Determinism on providers without seeds. Anthropic has no seed parameter. Your non_deterministic tagging has to actually work, or an auditor will find a CHALLENGE.BENIGN in a sealed package that can't be regenerated — and that's the one finding that would puncture the whole credibility story.
