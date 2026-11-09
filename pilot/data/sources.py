"""Network fetchers. Cache to parquet. Never called from inside family.run()."""
from __future__ import annotations

import hashlib
import pathlib
import time

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

CACHE = pathlib.Path("data/cache")
CACHE.mkdir(parents=True, exist_ok=True)


def _snapshot_hash(p: pathlib.Path) -> str:
    import blake3
    return "blake3:" + blake3.blake3(p.read_bytes()).hexdigest()


@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=1, max=30))
def _get_json(url: str, params: dict | None = None) -> dict:
    r = requests.get(url, params=params, timeout=30,
                     headers={"User-Agent": "molt-pilot/0.1"})
    r.raise_for_status()
    return r.json()


def fetch_season_pbp(season: str) -> tuple[pd.DataFrame, str]:
    """season e.g. '2023-24'. Returns (df, snapshot_hash)."""
    out = CACHE / f"pbp_{season}.parquet"
    if out.exists():
        return pd.read_parquet(out), _snapshot_hash(out)

    # TODO(PILOT): replace with full game-id enumeration via leaguegamelog endpoint.
    # Days 1–2: enumerate game ids for the season, then fetch playbyplayv3 for each.
    # Rate limit: ~0.6s/game × ~1230 games ≈ 12 min/season.
    games = []  # placeholder
    df = pd.DataFrame(games)
    df.to_parquet(out)
    return df, _snapshot_hash(out)


def fetch_crew_assignments(season: str) -> tuple[pd.DataFrame, str]:
    out = CACHE / f"crews_{season}.parquet"
    if out.exists():
        return pd.read_parquet(out), _snapshot_hash(out)
    # TODO(PILOT): nba officiating assignments (public scoreboard + box score endpoints).
    df = pd.DataFrame()
    df.to_parquet(out)
    return df, _snapshot_hash(out)
