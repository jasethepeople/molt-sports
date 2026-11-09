"""NBA Stats API fetchers with caching, rate limiting, and provenance.

Run:  python -m data.sources 2024-25

Writes:
  data/cache/games_{season}_{season_type}.parquet
  data/cache/pbp_{season}.parquet
  data/cache/crews_{season}.parquet

Design rules:
  - Never re-fetch a cached file. Cache is the source of truth.
  - Every fetch is rate-limited (~0.6s between requests).
  - Every response is retried ×5 with backoff.
  - Crew codes are role-only (sorted official IDs joined); names never leave this module.
  - Unparseable or missing data is returned as empty, not raised, so one bad game
    doesn't kill a 10-season fetch. Callers emit COVERAGE_GAP.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

import blake3
import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

CACHE = pathlib.Path("data/cache")
CACHE.mkdir(parents=True, exist_ok=True)

RATE_LIMIT_SEC = 0.6
STATS_BASE = "https://stats.nba.com/stats"

HEADERS = {
    # The NBA Stats API rejects requests without these four headers.
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://www.nba.com/",
    "Accept": "application/json, text/plain, */*",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}


class _RateLimited:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        elapsed = time.time() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.time()


_limiter = _RateLimited(RATE_LIMIT_SEC)


@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=2, max=60))
def _get_json(endpoint: str, params: dict) -> dict:
    _limiter.wait()
    r = requests.get(f"{STATS_BASE}/{endpoint}", params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def _result_set(j: dict, name: str | None = None) -> pd.DataFrame:
    """Extract a named result set from v2 (resultSets list) or v3 (resultSet dict)."""
    sets = j.get("resultSets")
    if isinstance(sets, list):
        for s in sets:
            if name is None or s.get("name") == name:
                return pd.DataFrame(s.get("rowSet", []), columns=s.get("headers", []))
    rs = j.get("resultSet")
    if rs:
        return pd.DataFrame(rs.get("rowSet", []), columns=rs.get("headers", []))
    return pd.DataFrame()


def _snapshot_hash(p: pathlib.Path) -> str:
    return "blake3:" + blake3.blake3(p.read_bytes()).hexdigest()


# ----------------------------------------------------------------------------
# games: metadata per (game_id, team-side) — deduped to one row per game
# ----------------------------------------------------------------------------

def fetch_season_games(season: str, season_type: str = "Regular Season") -> tuple[pd.DataFrame, str]:
    """One row per game with home/away IDs resolved from MATCHUP."""
    out = CACHE / f"games_{season}_{season_type.replace(' ', '_')}.parquet"
    if out.exists():
        return pd.read_parquet(out), _snapshot_hash(out)

    j = _get_json("leaguegamelog", {
        "Counter": 1000, "Direction": "DESC", "LeagueID": "00",
        "PlayerOrTeam": "T", "Season": season, "SeasonType": season_type,
        "Sorter": "DATE", "DateFrom": "", "DateTo": "",
    })
    raw = _result_set(j, "LeagueGameLog")
    if raw.empty:
        raise RuntimeError(f"No games for {season} {season_type}")

    raw = raw[[
        "GAME_ID", "GAME_DATE", "TEAM_ID", "TEAM_ABBREVIATION",
        "MATCHUP", "SEASON_ID", "WL", "PTS",
    ]].copy()
    raw["GAME_ID"] = raw["GAME_ID"].astype(str)
    raw["TEAM_ID"] = raw["TEAM_ID"].astype(int)
    raw["PTS"] = pd.to_numeric(raw["PTS"], errors="coerce").fillna(0).astype(int)
    raw["IS_HOME"] = raw["MATCHUP"].str.contains(r"vs\.", regex=True)

    rows = []
    for gid, g in raw.groupby("GAME_ID"):
        if len(g) != 2 or not (g["IS_HOME"].sum() == 1):
            # malformed game — skip with a warning
            print(f"  skip malformed {gid}", file=sys.stderr)
            continue
        h = g[g["IS_HOME"]].iloc[0]
        a = g[~g["IS_HOME"]].iloc[0]
        rows.append({
            "game_id": gid,
            "game_date": h["GAME_DATE"],
            "season_id": h["SEASON_ID"],
            "season_type": season_type,
            "home_team_id": int(h["TEAM_ID"]),
            "home_team_abbr": h["TEAM_ABBREVIATION"],
            "home_score": int(h["PTS"]),
            "away_team_id": int(a["TEAM_ID"]),
            "away_team_abbr": a["TEAM_ABBREVIATION"],
            "away_score": int(a["PTS"]),
            "home_won": h["WL"] == "W",
        })
    df = pd.DataFrame(rows)
    df.to_parquet(out, index=False)
    return df, _snapshot_hash(out)


# ----------------------------------------------------------------------------
# play-by-play: v3 actions, one row per event
# ----------------------------------------------------------------------------

def fetch_season_pbp(
    season: str,
    season_types: tuple[str, ...] = ("Regular Season", "Playoffs"),
    max_games: int | None = None,
) -> tuple[pd.DataFrame, str]:
    """Concatenate PBP for every game in the season."""
    out = CACHE / f"pbp_{season}.parquet"
    if out.exists():
        return pd.read_parquet(out), _snapshot_hash(out)

    game_frames = []
    for st in season_types:
        try:
            g, _ = fetch_season_games(season, st)
            game_frames.append(g)
        except RuntimeError:
            continue
    if not game_frames:
        raise RuntimeError(f"No games for {season}")
    all_games = pd.concat(game_frames, ignore_index=True)
    if max_games:
        all_games = all_games.head(max_games)

    dfs = []
    total = len(all_games)
    for i, gid in enumerate(all_games["game_id"]):
        try:
            df = _fetch_one_pbp(gid)
            if not df.empty:
                dfs.append(df)
        except Exception as e:
            print(f"  pbp skip {gid}: {type(e).__name__}: {e}", file=sys.stderr)
        if (i + 1) % 50 == 0:
            print(f"  pbp {i + 1}/{total}", file=sys.stderr)

    if not dfs:
        raise RuntimeError(f"No PBP rows for {season}")
    pbp = pd.concat(dfs, ignore_index=True)
    pbp.to_parquet(out, index=False)
    return pbp, _snapshot_hash(out)


def _fetch_one_pbp(game_id: str) -> pd.DataFrame:
    j = _get_json("playbyplayv3", {"GameID": game_id, "StartPeriod": 0, "EndPeriod": 0})
    actions = (j.get("game") or {}).get("actions") or []
    rows = []
    for a in actions:
        rows.append({
            "game_id": game_id,
            "action_number": a.get("actionNumber"),
            "period": a.get("period"),
            "clock": a.get("clock"),
            "action_type": a.get("actionType"),
            "sub_type": a.get("subType"),
            "team_id": a.get("teamId"),
            "person_id": a.get("personId"),
            "description": a.get("description"),
            "shot_result": a.get("shotResult"),
            "shot_value": a.get("shotValue"),
            "points_total": a.get("pointsTotal"),
            "score_home": a.get("scoreHome"),
            "score_away": a.get("scoreAway"),
        })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# crews: officials per game
# ----------------------------------------------------------------------------

def fetch_crew_assignments(season: str) -> tuple[pd.DataFrame, str]:
    """Officials for every game. Crew code = sorted official IDs, joined.

    Names never leave this function. Only the role code (CREW-<id1>-<id2>-<id3>)
    is written to disk.
    """
    out = CACHE / f"crews_{season}.parquet"
    if out.exists():
        return pd.read_parquet(out), _snapshot_hash(out)

    games_list = []
    for st in ("Regular Season", "Playoffs"):
        try:
            g, _ = fetch_season_games(season, st)
            games_list.append(g)
        except RuntimeError:
            continue
    if not games_list:
        raise RuntimeError(f"No games for {season}")
    all_games = pd.concat(games_list, ignore_index=True)

    rows = []
    total = len(all_games)
    for i, gid in enumerate(all_games["game_id"]):
        try:
            ids = _fetch_officials(gid)
            if ids:
                rows.append({
                    "game_id": gid,
                    "crew_code": "CREW-" + "-".join(str(x) for x in sorted(ids)),
                    "n_officials": len(ids),
                })
        except Exception as e:
            print(f"  crew skip {gid}: {type(e).__name__}", file=sys.stderr)
        if (i + 1) % 100 == 0:
            print(f"  crews {i + 1}/{total}", file=sys.stderr)

    df = pd.DataFrame(rows)
    df.to_parquet(out, index=False)
    return df, _snapshot_hash(out)


def _fetch_officials(game_id: str) -> list[int]:
    """Extract OFFICIAL_ID list from boxscoresummaryv2. Returns [] if not present."""
    j = _get_json("boxscoresummaryv2", {"GameID": game_id})
    df = _result_set(j, "Officials")
    if df.empty or "OFFICIAL_ID" not in df.columns:
        return []
    return [int(x) for x in df["OFFICIAL_ID"].dropna().tolist()]


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def _main() -> int:
    ap = argparse.ArgumentParser(description="Fetch NBA data for one season.")
    ap.add_argument("season", help="e.g. 2024-25")
    ap.add_argument("--max-games", type=int, default=None,
                    help="Limit PBP fetch to first N games (debug only)")
    args = ap.parse_args()

    print(f"[games] {args.season}")
    for st in ("Regular Season", "Playoffs"):
        try:
            g, h = fetch_season_games(args.season, st)
            print(f"  {st}: {len(g)} games  {h[:24]}…")
        except RuntimeError as e:
            print(f"  {st}: {e}")

    print(f"[pbp] {args.season} (this is the slow part — ~13 min/season)")
    pbp, h = fetch_season_pbp(args.season, max_games=args.max_games)
    print(f"  {len(pbp):,} events  {h[:24]}…")

    print(f"[crews] {args.season} (~2 min/season)")
    cr, h = fetch_crew_assignments(args.season)
    print(f"  {len(cr)} crew assignments  {h[:24]}…")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
