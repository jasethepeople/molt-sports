# Observatory Query Surface

Read-only. Every response carries log_head (latest event hash per stream) and merkle_root so the client can independently verify it's seeing the real, unedited log.

## Auth matrix

| Endpoint | PUBLIC | MEDIA | BOOK | REGULATOR | REVIEWER |
|---|---|---|---|---|---|
| /worlds, /streams | ✅ | ✅ | ✅ | ✅ | ✅ |
| /events (list) | ✅ | ✅ | ✅ | ✅ | ✅ |
| /events/{hash} | ✅ | ✅ | ✅ | ✅ | ✅ |
| /claims/{id}/decomposition | ✅ | ✅ | ✅ | ✅ | ✅ |
| /claims/{id}/verdict | ✅ | ✅ | ✅ | ✅ | ✅ |
| /claims/{id}/evidence | summary | full | full | full | full |
| /verify/{hash} | ✅ | ✅ | ✅ | ✅ | ✅ |
| /reproduce/{verdict} | — | — | ✅ | ✅ | ✅ |
| /quarantine | counts | ✅ | ✅ | ✅ | ✅ |
| /index/entity | ✅ | ✅ | ✅ | ✅ | ✅ |
| /anomaly-feed | — | — | ✅ | ✅ | — |
| /export/package | — | — | ✅ | ✅ | ✅ |

## Core endpoints

```http
GET /v1/worlds
→ 200 { "worlds": [ { "world_id":"...", "contract_hash":"blake3:...", "genesis_utc":"...", "streams": 412 } ], "log_head": "blake3:..." }

GET /v1/streams?sport=nba&season=2024-25&type=game
→ 200 { "streams": [ { "stream":"sports/nba/2024-25/game/0042400301", "head":"blake3:...", "events": 1184, "open_claims": 3 } ] }

GET /v1/events?stream=...&kind=VERDICT.SUPPORTED,VERDICT.PARTIALLY_SUPPORTED&since=&until=&limit=100&cursor=
→ 200 { "events":[...], "next_cursor":"...", "log_head":"blake3:..." }
```

```http
GET /v1/events/blake3:abc…
→ 200 {
  "event": { …full signed envelope… },
  "inclusion": { "merkle_root":"blake3:…", "path":["blake3:…","blake3:…"] }
}
```

inclusion.path is a Merkle proof — the client can verify the event was in the log at that root without trusting you.

```http
GET /v1/claims/CLM-3f9a2c81b4d0/decomposition
→ 200 {
  "claim": { "claim_id":"CLM-…", "verbatim":"…", "attribution": {…} },
  "subclaims": [
    { "subclaim_id":"SUB-…", "family":{"group":"OFFICIATING","member":"SERIES_EXTENSION"},
      "testability":"TESTABLE", "null_hypothesis":"…", "baseline_ref":"blake3:…" },
    { "subclaim_id":"SUB-…", "family":{"group":"SCRIPT","member":"PREDETERMINED_TOTALITY"},
      "testability":"UNTESTABLE", "untestable_reason":"No operationalization exists that a null result could falsify; every contrary observation is absorbable into the hypothesis." }
  ],
  "summary": { "total": 4, "testable": 2, "testimony_only": 1, "untestable": 1 },
  "log_head": "blake3:…"
}
```

```http
GET /v1/claims/CLM-…/verdict?history=true
→ 200 {
  "current": {
    "SUB-…": { "verdict":"INCONCLUSIVE", "confidence":0.41,
               "posterior": {"alpha":3,"beta":6,"mean":0.33},
               "gate_results": {"fdr_pass":false,"power_pass":false,"coverage_complete":false},
               "limitations":["Single season of crew-assignment data; 34 elimination games below power floor."],
               "sealed_at":"2025-11-08T00:00:00Z", "hash":"blake3:…" },
    "SUB-…": { "verdict":"UNTESTABLE", "confidence":null, "reason":"…" }
  },
  "history": [ { "verdict":"PARTIALLY_SUPPORTED", "superseded_by":"blake3:…", "superseded_at":"…", "reason":"Baseline v3 corrected for rest asymmetry" } ],
  "log_head":"blake3:…"
}
```

history is never empty-and-hidden — if a verdict was ever superseded or retracted, it shows. That's the product.

```http
GET /v1/verify/blake3:abc…
→ 200 { "event_id":"…", "sig_valid":true, "chain_valid":true,
        "refs_resolved": 7, "refs_missing": 0,
        "replay": { "code_hash":"blake3:…", "output_reproduced": true } }
```

```http
GET /v1/reproduce/blake3:verdict…
→ 200 { "command":"docker run ghcr.io/…/replay@sha256:…",
        "code_hash":"…", "input_hashes":["…"], "expected_output_hash":"…",
        "runtime":"python:3.12-slim", "est_seconds": 42 }
```

```http
GET /v1/quarantine?stream=...&reason=NAMING_PROHIBITED
→ 200 { "rejected": [ { "digest":"blake3:…", "kind":"VERDICT.SUPPORTED",
                        "reason":"NAMING_PROHIBITED", "at":"2025-11-07T…" } ],
        "counts_by_reason": { "UNCORRECTED_SIGNIFICANCE": 4, "TESTIMONY_AS_PROOF": 1 } }
```

Publishing your own rejection log is the single most credible thing this system does. Customers will check it.

```http
GET /v1/index/entity/CREW-2024-017?sport=nba&window=season
→ 200 {
  "entity_code":"CREW-2024-017",
  "integrity_index": 0.83,
  "subclaims": [ {"family":"OFFICIATING.CREW_TENDENCY","verdict":"PARTIALLY_SUPPORTED","confidence":0.61} ],
  "null_results": 4,
  "open_challenges": 1,
  "limitations": ["Index excludes playoff games with <12 crew appearances."],
  "log_head":"blake3:…"
}
```

Role code only. There is no endpoint that maps CREW-2024-017 to a person unless the caller is REGULATOR tier and hits IDENTITY.UNMASK, which writes its own signed event into an identity/ stream that is visible in the audit log forever.

```http
GET /v1/anomaly-feed?sport=nba&window=live&min_confidence=0.7
→ 200 { "flags": [ { "game":"…", "subclaim_id":"…", "family":"MARKET.PROP_CONCENTRATION",
                     "confidence":0.74, "evidence_ref":"blake3:…",
                     "benign_unresolved": true, "tier":"BOOK" } ],
        "notice":"Probabilistic flags. Not accusations. Verify via /claims/{id}/evidence." }
```

```http
POST /v1/export/package
{ "claim_ids":["CLM-…"], "tier":"REGULATOR", "include":["evidence","replay_proofs","challenges","quarantine_log"] }
→ 202 { "package_id":"PKG-…", "status":"BUILDING", "estimated_utc":"…" }
→ GET /v1/export/package/PKG-…
→ 200 { "bundle_hash":"blake3:…", "manifest":[…], "signatures":["ed25519:…"], "download":"…" }
```

The bundle is the deliverable a regulator can hand to counsel. It carries its own manifest and signature; nothing in it can be edited without breaking bundle_hash.

---

## The two things this gets you

1. Accusation is impossible, structurally. There is no field for a name in a verdict, no reference path from VERDICT to IDENTITY.UNMASK, and the validator refuses narrative containing proper names. You cannot be the story because the schema won't let you write one.

2. The null result is a first-class artifact. EVIDENCE.NULL, VERDICT.REFUTED, VERDICT.UNTESTABLE, and COVERAGE_GAP all have homes. A clean game produces a sealed, signed, publishable package saying so — which is exactly what a sportsbook wants for liability defense and a regulator wants for closure.
