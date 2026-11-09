# Observatory Front End: The Trading Desk View

The book's traders don't read sealed packages. They need a live surface during a game that answers three questions in under three seconds:

1. Is anything flagged right now?
2. How strong is it, and how confident?
3. What do I do about it?

## B.1 — The live desk

```
┌─ GAME 0042400301  BOS @ MIA  Q3 4:12  87-84 ────────────────┐
│ INTEGRITY  82/100   [3 flags]   [open evidence]             │
│                                                              │
│ ▸ MARKET.PROP_CONCENTRATION   ⚠ 0.74                        │
│   Single-prop liability 98.2nd pctile · Tatum rebounds O7.5 │
│   benign_unresolved: 1 · [evidence] [replay] [mute 15m]     │
│                                                              │
│ ▸ OFFICIATING.CREW_TENDENCY   · 0.58                        │
│   CREW-2024-017 foul diff +0.9/100 vs baseline              │
│   benign: home-travel confounder · [evidence]               │
│                                                              │
│ ▸ TEMPORAL.CLOCK_ANOMALY      · 0.41                        │
│   Possession 214 timing delta 1.8s · likely feed error      │
│   [mark data_quality]                                       │
│                                                              │
│ NOTICE: Probabilistic flags, not accusations. Verify before │
│ acting. Log head blake3:9c1f…  [verify]                     │
└──────────────────────────────────────────────────────────────┘
```

Design decisions baked in:

- Integrity score is composite and capped. A single flag at confidence 0.74 cannot drag a clean game below ~75. The score is a summary, never the decision — every number is one click from evidence.
- benign_unresolved is always visible. A flag with an open benign explanation shows it in the row. No flag hides its own weakness.
- Confidence is a number, never a word. "0.74" not "High." Words imply certainty; numbers invite scrutiny.
- [replay] is on every row. One click opens the reproduce command. Traders learn to distrust flags they can't rerun.
- Notice is fixed chrome. Not a tooltip. Not a footer. Permanent.
- log_head is on screen. The trader can verify the feed hasn't been tampered with by hitting [verify].

## B.2 — The mute mechanic (why traders will trust it)

A persistent problem with integrity tools: alert fatigue. The solution is explicit muting with audit.

```
[mute 15m]  →  asks reason:
  - known_pattern    (this crew always does this)
  - low_relevance    (not a market I have exposure on)
  - suspected_error  (I think the feed is wrong)
  - other            (free text)
```

Every mute emits a signed OPERATOR.MUTE event with reason. Mutes are visible at REGULATOR tier. A book that mutes everything is a book with a record of muting everything. That's the deterrent, and it's also what makes the mute button safe to use.

## B.3 — The pre-game brief

Traders open the desk 2 hours before tip. They see:

```
┌─ BOS @ MIA  ·  2025-11-08 19:30 ET ─────────────────────────┐
│ INTEGRITY BRIEF                    generated 17:14 ET        │
│                                                              │
│ Baseline drift:   none active                                │
│ Crew:             CREW-2024-017 (index 0.83, 4 null results)│
│ Open claims:      2 (both INCONCLUSIVE, low power)          │
│ Market pre-drift: no abnormal movement in last 24h          │
│ Last 5 games:     3 null results, 2 inconclusive, 0 flags   │
│                                                              │
│ SUGGESTED LIMITS: standard                                  │
│ [full brief] [replay history] [export package]              │
└──────────────────────────────────────────────────────────────┘
```

The pre-game brief is mostly null results. That's the product working. A book that wakes up to "nothing flagged" every day is a book that trusts the days when something is.

## B.4 — The escalation path

When a flag crosses a threshold, the desk has a defined action:

| Confidence | Action available | Requires |
|---|---|---|
| 0.60–0.69 | Watch | None — flag logged |
| 0.70–0.79 | Limit tighten (market-level) | Trader judgment, logged |
| 0.80–0.89 | Market suspend (single market) | Trading manager approval, logged |
| 0.90+ | Full market suspend | Compliance sign-off, logged |

Every action is a signed event. The book's regulator sees the full history: what was flagged, when, by whom, and what was done. That's the compliance deliverable they can't build themselves.

## B.5 — The regulator's queue

Regulators see a different surface — not the live desk, but a case queue:

```
┌─ OPEN CASES  ·  REGULATOR TIER ─────────────────────────────┐
│ CASE-…  GAME 0042400301  MARKET.PROP_CONCENTRATION  0.74   │
│   Book action: limit_tighten  (2025-11-08 21:44)            │
│   Evidence: [3 refs]  Replay: [command]  Dissent: none      │
│   Status: AWAITING_REGULATOR_REVIEW                         │
│                                                              │
│ CASE-…  GAME 0042400298  OFFICIATING.CREW_TENDENCY  0.81   │
│   Book action: market_suspend  (2025-11-07 22:11)          │
│   Evidence: [5 refs]  Replay: [command]  Dissent: 1        │
│   Dissent: "Family defined post hoc; FWER not controlled."  │
│   Status: AWAITING_EXTERNAL_REVIEW                          │
└──────────────────────────────────────────────────────────────┘
```

Dissent is on the case row, not buried. A regulator sees the disagreement before they see the finding. That's the difference between a tool they use and a tool they subpoena.

## B.6 — The API contract (trading desk integration)

Books with their own OMS need the feed, not the UI:

```
GET  /v1/desk/{game}/state            → live flags, log_head, verify_token
GET  /v1/desk/{game}/brief            → pre-game brief
POST /v1/desk/{game}/action           → signed trader action (watch/limit/suspend)
POST /v1/desk/{game}/mute             → signed mute with reason
GET  /v1/desk/{game}/stream           → SSE; each flag is a signed event
```

Every response carries log_head and verify_token (Merkle root). The book's systems can independently verify the feed hasn't been tampered with — the book doesn't have to trust the platform, it can check the math.

---

## The system is now fully specified, end to end

| Layer | Status |
|---|---|
| Transparency kernel | Built (molt-show, the-room) |
| Event taxonomy | Frozen v1.1.0 |
| Admission rules | 18 executable checks, first-fail quarantine |
| Baselines | Versioned, falsifiable, drift-monitored |
| Human signoff | Quorum-gated, dissent-published, 30d cooling at top tier |
| Statistical families | 12 specified, power floors, null definitions |
| Test harness | Frozen interface, conformance suite gates registry |
| BYOK layer | Envelope crypto, capability negotiation, deterministic-only fallback |
| Trading desk | Live view, mute-with-audit, escalation ladder |
| Regulator queue | Case view with dissent surfaced |

Everything from here is build, not design.

The one thing I'd do before writing a line of code: run the null-result math by hand for one real season. Take a full NBA season of play-by-play, implement OFFICIATING.CREW_TENDENCY and OFFICIATING.SERIES_EXTENSION exactly as specified, and see what comes out. If you get a believable distribution of nulls and the occasional PARTIALLY_SUPPORTED, the design holds. If everything comes back SUPPORTED, your baselines are miscalibrated and you find out in week one instead of in front of a regulator.

That's the next artifact I'd build. See docs/pilot.md.
