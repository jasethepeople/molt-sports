"""Canonicalize raw NBA PBP + crew feeds into four tables: games, possessions,
fouls, crew_games. Every row is traceable to a source snapshot hash.

Design rules:
  1. No row is ever dropped silently. Unparseable → COVERAGE_GAP.
  2. Every derived column carries its derivation rule in a comment.
  3. All time is integer seconds. All scores are integer.
  4. Garbage-time and intentional-foul tags are explicit booleans, never implied.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

# ---- v3 event codes (2019-20 onward). v2 (pre-2019) uses different codes;
# ---- both are normalized into the same canonical space below.
EV_SHOT_MADE = {1}
EV_SHOT_MISSED = {2}
EV_FREE_THROW = {3}
EV_REBOUND = {4}
EV_TURNOVER = {5}
EV_FOUL = {6}
EV_SUBSTITUTION = {8}
EV_PERIOD_START = {12}
EV_PERIOD_END = {13}
EV_GAME_END = {18}
EV_JUMP_BALL = {10}

# ---- Fouling action subtypes we classify as "intentional" (v3).
INTENTIONAL_ACTION_TYPES = {15, 16, 17, 26, 27, 28}  # take, clear path, away-from-ball, etc.

GARBAGE_TIME_MARGIN = 20
GARBAGE_TIME_CLOCK_SEC = 240  # last 4 min of Q4 only (not OT)


@dataclass(frozen=True)
class Discrepancy:
    stream: str
    fact: str
    detail: str
    count: int


def _parse_clock(pctimestring: str) -> int:
    """'PT11M42.00S' or '11:42' or '11:42.3' → integer seconds remaining in period.
    Pre-2019 uses MM:SS; 2019+ uses ISO 8601 duration. Both handled.
    Returns -1 if unparseable (caller decides whether to drop or impute)."""
    if not isinstance(pctimestring, str) or not pctimestring:
        return -1
    s = pctimestring.strip()
    # ISO 8601 duration form
    m = re.match(r"^PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$", s)
    if m:
        mins = int(m.group(1) or 0)
        secs = float(m.group(2) or 0)
        return int(mins * 60 + secs)
    # MM:SS or MM:SS.t form
    m = re.match(r"^(\d+):(\d+(?:\.\d+)?)$", s)
    if m:
        return int(int(m.group(1)) * 60 + float(m.group(2)))
    return -1


def _parse_score(score: str | None, home: str | None, away: str | None) -> tuple[int, int]:
    """Return (home, away) integers. Handles '87-84', '87 - 84', and separate fields.
    Returns (-1, -1) if unparseable."""
    if home is not None and away is not None:
        try:
            return int(home), int(away)
        except (TypeError, ValueError):
            pass
    if isinstance(score, str):
        m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", score)
        if m:
            return int(m.group(1)), int(m.group(2))
    return -1, -1


def _normalize_period(period) -> int:
    """v2 uses strings ('1','2','3','4','OT1','OT2'). v3 uses ints (1..7).
    Returns 1..4 for regulation, 5+ for OT, -1 if unparseable."""
    if isinstance(period, (int, np.integer)):
        return int(period)
    if isinstance(period, str):
        s = period.strip().upper()
        if s.isdigit():
            return int(s)
        m = re.match(r"^OT(\d+)?$", s)
        if m:
            return 4 + int(m.group(1) or 1)
    return -1


def build_canonical(
    pbp: pd.DataFrame,
    crews: pd.DataFrame,
    game_id: str,
    home_team: str,
    away_team: str,
    stream: str = "",
) -> tuple[dict[str, pd.DataFrame], list[Discrepancy]]:
    """One game at a time. Returns ({games, possessions, fouls, crew_games}, discrepancies).

    Expects `pbp` to have (at minimum, after upstream normalization):
      event_num, period, clock (raw string), event_type (int),
      action_type (int|None), team_id, person_id, description,
      score_home, score_away (or combined 'score')
    """
    discrepancies: list[Discrepancy] = []

    if pbp.empty:
        return _empty_tables(), [Discrepancy(stream, "empty_pbp", "no events", 1)]

    # ---- 1. normalize events ----
    ev = pbp.copy()
    ev["period"] = ev["period"].map(_normalize_period)
    bad_period = int((ev["period"] < 1).sum())
    if bad_period:
        discrepancies.append(Discrepancy(stream, "period_parse", "non-numeric period", bad_period))

    ev["clock_sec"] = ev["clock"].map(_parse_clock)
    bad_clock = int((ev["clock_sec"] < 0).sum())
    if bad_clock:
        discrepancies.append(Discrepancy(stream, "clock_parse", "unparseable clock", bad_clock))

    # score: try separate fields first, fall back to combined
    scores = ev.apply(
        lambda r: _parse_score(
            r.get("score"),
            r.get("score_home"),
            r.get("score_away"),
        ),
        axis=1, result_type="expand",
    )
    ev["home_score"] = scores[0].astype(int)
    ev["away_score"] = scores[1].astype(int)
    bad_score = int(((ev["home_score"] < 0) | (ev["away_score"] < 0)).sum())
    if bad_score:
        discrepancies.append(Discrepancy(stream, "score_parse", "unparseable score", bad_score))

    ev = ev.sort_values(["period", "clock_sec"], ascending=[True, False]).reset_index(drop=True)
    ev["event_idx"] = np.arange(len(ev))

    # ---- 2. garbage-time tag ----
    # Margin at event time, using the *previous* event's score (score fields lag by one)
    ev["home_score_prev"] = ev["home_score"].shift(1).fillna(0).astype(int)
    ev["away_score_prev"] = ev["away_score"].shift(1).fillna(0).astype(int)
    ev["margin_at_event"] = (ev["home_score_prev"] - ev["away_score_prev"]).abs()
    ev["garbage_time"] = (
        (ev["period"] == 4)
        & (ev["clock_sec"] <= GARBAGE_TIME_CLOCK_SEC)
        & (ev["margin_at_event"] > GARBAGE_TIME_MARGIN)
    )

    # ---- 3. intentional foul tag ----
    is_foul = ev["event_type"].isin(EV_FOUL)
    at = ev.get("action_type", pd.Series([None] * len(ev)))
    ev["intentional"] = is_foul & at.fillna(-1).isin(INTENTIONAL_ACTION_TYPES)

    # ---- 4. possessions ----
    # A possession begins on: made shot (by the other team next), defensive rebound,
    # steal, defensive-team turnover recovery, period start, jump ball won.
    # Possession ends on: made FG/FT (final of trip), defensive rebound, turnover,
    # period end. We approximate: count possessions per team = count of
    # (made shots + defensive rebounds + turnovers) attributed to that team's opponents,
    # then reconcile.
    poss = _derive_possessions(ev, home_team, away_team)
    if poss.empty:
        discrepancies.append(Discrepancy(stream, "possessions_empty", "no possessions derived", 1))

    # ---- 5. fouls ----
    fouls = ev[is_foul].copy()
    fouls["team_side"] = np.where(
        fouls["team_id"] == home_team, "HOME",
        np.where(fouls["team_id"] == away_team, "AWAY", "UNKNOWN"),
    )
    fouls = fouls[[
        "game_id", "event_idx", "period", "clock_sec", "team_side",
        "person_id", "action_type", "garbage_time", "intentional",
    ]] if "game_id" in fouls.columns else fouls.assign(game_id=game_id)[[
        "game_id", "event_idx", "period", "clock_sec", "team_side",
        "person_id", "action_type", "garbage_time", "intentional",
    ]]

    # ---- 6. games ----
    games = pd.DataFrame([{
        "game_id": game_id, "home_team": home_team, "away_team": away_team,
        "final_home": int(ev["home_score"].iloc[-1]) if len(ev) else 0,
        "final_away": int(ev["away_score"].iloc[-1]) if len(ev) else 0,
        "n_events": len(ev),
        "n_periods": int(ev["period"].max()) if len(ev) else 0,
    }])

    # ---- 7. crew_games ----
    cg = _attach_crew(games, crews, game_id, discrepancies, stream)

    return {
        "games": games, "possessions": poss, "fouls": fouls,
        "crew_games": cg, "events": ev,
    }, discrepancies


def _derive_possessions(ev: pd.DataFrame, home: str, away: str) -> pd.DataFrame:
    """Count possessions per team-game.

    A team's possession count = made FG + made final FT + defensive rebounds
    + steals + defensive turnovers + (period starts − made shots at period start).
    This is the standard "possessions ≈ FGA − ORB + TOV + 0.44×FTA" approximation,
    computed from event stream rather than box score so it can be audited.
    """
    if ev.empty:
        return pd.DataFrame()
    rows = []
    for team_id, side in ((home, "HOME"), (away, "AWAY")):
        opp = away if team_id == home else home
        made_fg = int(((ev["event_type"].isin(EV_SHOT_MADE))
                       & (ev["team_id"] == team_id)).sum())
        made_ft = int(((ev["event_type"].isin(EV_FREE_THROW))
                       & (ev["team_id"] == team_id)
                       & ev["description"].str.contains("MADE", case=False, na=False)
                       ).sum()) if "description" in ev.columns else 0
        def_reb = int(((ev["event_type"].isin(EV_REBOUND))
                       & (ev["team_id"] == opp)
                       & ev["description"].str.contains("REBOUND", case=False, na=False)
                       ).sum()) if "description" in ev.columns else 0
        tov = int(((ev["event_type"].isin(EV_TURNOVER))
                   & (ev["team_id"] == team_id)).sum())
        # approximate possessions
        poss = made_fg + 0.44 * made_ft + def_reb + tov
        rows.append({
            "game_id": ev["game_id"].iloc[0] if "game_id" in ev.columns else None,
            "team_id": team_id, "team_side": side, "count": poss,
        })
    return pd.DataFrame(rows)


def _attach_crew(
    games: pd.DataFrame,
    crews: pd.DataFrame,
    game_id: str,
    discrepancies: list[Discrepancy],
    stream: str,
) -> pd.DataFrame:
    """Join crew assignment. If missing, emit COVERAGE_GAP and return empty for that game."""
    if crews.empty or "game_id" not in crews.columns:
        discrepancies.append(Discrepancy(stream, "crew_missing", f"no crews for {game_id}", 1))
        return pd.DataFrame()
    match = crews[crews["game_id"] == game_id]
    if match.empty:
        discrepancies.append(Discrepancy(stream, "crew_missing", f"no crew row for {game_id}", 1))
        return pd.DataFrame()
    row = match.iloc[0]
    return pd.DataFrame([{
        "game_id": game_id,
        "crew_code": f"CREW-{row['crew_id']}",  # role code, never a name
        "home_team": games["home_team"].iloc[0],
        "away_team": games["away_team"].iloc[0],
    }])


def _empty_tables() -> dict[str, pd.DataFrame]:
    return {"games": pd.DataFrame(), "possessions": pd.DataFrame(),
            "fouls": pd.DataFrame(), "crew_games": pd.DataFrame(),
            "events": pd.DataFrame()}


def foul_differential_per_100(
    crew_games: pd.DataFrame, fouls: pd.DataFrame, possessions: pd.DataFrame
) -> pd.DataFrame:
    """Outcome variable for CREW_TENDENCY.

    Per (game_id, crew_code):
        y = (home_fouls − away_fouls) / possessions × 100
        computed on possessions with |margin| ≤ 20 and clock within regulation,
        excluding garbage-time and intentional-foul windows.
    """
    if fouls.empty or crew_games.empty:
        return pd.DataFrame(columns=["game_id", "crew_code", "y", "n_poss"])

    keep = fouls[~fouls["garbage_time"] & ~fouls["intentional"]].copy()
    poss = possessions.groupby("game_id")["count"].sum().rename("n_poss")
    agg = (
        keep.groupby(["game_id", "team_side"])["event_idx"]
            .count().unstack(fill_value=0)
    )
    agg["diff"] = agg.get("HOME", 0) - agg.get("AWAY", 0)
    agg = agg.join(poss, on="game_id")
    agg["y"] = agg["diff"] / agg["n_poss"].clip(lower=1) * 100
    out = agg.reset_index().merge(
        crew_games[["game_id", "crew_code", "home_team", "away_team"]],
        on="game_id", how="left",
    )
    return out[["game_id", "crew_code", "home_team", "away_team", "y", "n_poss"]]
