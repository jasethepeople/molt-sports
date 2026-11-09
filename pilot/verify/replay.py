"""Determinism + replay. Byte-identical result or the run fails."""
from __future__ import annotations

import json

import blake3

from harness.protocol import TestResult


def result_hash(r: TestResult) -> str:
    """Canonical hash of a TestResult, excluding notes and artifacts.

    Excluding notes is deliberate: notes are human-facing and may contain
    floats formatted to fewer digits. The test is deterministic in its
    numbers, not in its prose.
    """
    payload = {
        "statistic": r.statistic,
        "effect_size": r.effect_size,
        "effect_metric": r.effect_metric,
        "n": r.n,
        "p_raw": r.p_raw,
        "p_adjusted": r.p_adjusted,
        "power_achieved": r.power_achieved,
        "ci": r.ci,
        "ci_type": r.ci_type,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return "blake3:" + blake3.blake3(blob).hexdigest()


def assert_reproducible(fn, ctx, df, attempts: int = 3) -> str:
    hashes = {result_hash(fn().run(ctx, df)) for _ in range(attempts)}
    if len(hashes) != 1:
        raise RuntimeError(f"NON_DETERMINISTIC: {hashes}")
    return hashes.pop()
