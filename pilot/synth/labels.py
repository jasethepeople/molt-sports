"""Read sealed labels post-hoc, for scoring only. Never imported by families."""
from __future__ import annotations

import json
import pathlib


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_bytes())


def recall(detected: set[str], labels: dict) -> float:
    injected = set(map(str, labels["injected_games"]))
    return len(detected & injected) / max(1, len(injected))
