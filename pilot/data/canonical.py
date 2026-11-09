"""Canonicalize raw feeds into per-game tables with derived variables.

Handles:
  - clock formats across the v2 (MM:SS) / v3 (ISO 8601) eras
  - score fields: v3 "scoreHome"/"scoreAway" as strings, lagged by one event
  - possession derivation with team rebounds, shot-clock violations, heaves
  - series state for SERIES_EXTENSION (is_elimination, trailing_team_won)
  - timing_delta_sec = 0.0 for pilot (canary fires only on real video deltas)

Emits discrepancy strings for the caller to convert to INGEST events. Every
discrepancy includes the game_id, so failures are traceable.
"""
from __future__ import annotations

import re
import numpy as np
import pandas as pd

GARBAGE_TIME_MARGIN = 20
GARBAGE_TIME_CLOCK_SEC = 240


# ---- parsers ----------------------------------------------------------------

def _parse_clock(raw) -> int:
    """Return seconds remaining in period, or -1 if unparseable.
    Handles:
      ISO 8601 duration:  'PT11M42.00S', 'PT0M00.00S'
      legacy MM:SS:        '11:42', '0:03.4'
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return -1
    s = str(raw).strip()
    if not s:
        return -1
    m = re.match(r"^PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$", s)
    if m:
        return int(int(m.group(1) or 0) * 60 + float(m.group(2) or 0))
    m = re.match(r"^(\d+):(\d+(?:\.\d+)?)$", s)
    if m:
        return int(int(m.group(1)) * 60 + float(m.group(2)))
    return -1


def _to_int(v) -> int:
    if v is None:
        return -1
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, float):
        return -1 if np.isnan(v) else int(v)
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return -1


def _normalize_period(p) -> int:
    """1..4 = regulation, 5+ = OT, -1 = unparseable."""
    if isinstance(p, (int, np.integer)):
        return int(p)
    if isinstance(p, str):
        s = p.strip().upper()
        if s.isdigit():
            return int(s)
        m = re.match(r"^OT(\d+)?$", s)
        if m:
            return 4 + int(m.group(1) or 1)
    return -1


def _classify_event(action_type, sub_type, shot_result) -> str:
    """Canonical event codes.

    v2 uses numeric codes (1=made shot, 2=missed, 3=FT, 4=rebound, 5=TOV, 6=foul,
    8=sub, 12=period start, 13=period end).
    v3 uses strings ('2pt', '3pt', 'freethrow', 'rebound', 'turnover', 'foul',
    'substitution', 'period', 'game', 'jumpball').
    """
    if action_type is None:
        return "other"
    if isinstance(action_type, (int, np.integer)):
        return {
            1: "shot_made", 2: "shot_missed", 3: "freethrow",
            4: "rebound", 5: "turnover", 6: "foul",
            8: "substitution", 10: "jumpball", 12: "period_start",
            13: "period_end", 18: "game_end",
        }.get(int(action_type), "other")

    at = str(action_type).strip().lower()
    if not at:
        return "other"
    if "made" in at and "shot" in at:
        return "shot_made"
    if "miss" in at and "shot" in at:
        return "shot_missed"
    if at in ("2pt", "3pt"):
        return "shot_made" if str(shot_result or "").lower() == "made" else "shot_missed"
    if "free" in at and "throw" in at:
        return "freethrow"
    if "rebound" in at:
        return "rebound"
    if "turnover" in at:
        return "turnover"
    if at == "foul" or (at.startswith("foul") and "personal" not in at and "shooting" not in at):
        return "foul"
    if "substitution" in at:
        return "substitution"
    if at == "period" or at == "period start" or at == "period end":
        return "period_start" if "start" in at else "period_end"
    if at == "game":
        return "game_end"
    if "jump" in at:
        return "jumpball"
    return "other"


def _is_intentional_foul(sub_type) -> bool:
    if sub_type is None:
        return False
    st = str(sub_type).lower()
    return any(k in st for k in (
        "clear path", "away from play", "take foul", "transition take",
        "away-from-ball",
    ))


# ---- series state -----------------------------------------------------------

def build_series_state(playoff_games: pd.DataFrame) -> pd.DataFrame:
    """For each playoff game, whether it is an elimination game and whether the
    trailing team won.

    Elimination = one team has 3 wins in a best-of-7, the other is behind.
    Play-in games are NOT included here (different season_type in source data).
    """
    if playoff_games.empty:
        return pd.DataFrame(columns=["game_id", "is_elimination", "trailing_team_won"])

    g = playoff_games.copy()
    g["series_key"] = g.apply(
        lambda r: tuple(sorted([int(r["home_team_id"]), int(r["away_team_id"])])),
        axis=1,
    )
    g = g.sort_values(["series_key", "game_date"])

    rows = []
    for _sk, sg in g.groupby("series_key", sort=False):
        wins: dict[int, int] = {}
        for _, game in sg.iterrows():
            home = int(game["home_team_id"])
            away = int(game["away_team_id"])
            hw = wins.get(home, 0)
            aw = wins.get(away, 0)
            is_elim = (hw == 3) ^ (aw == 3)
            trailing_won = None
            if is_elim:
                trailing = home if aw == 3 else away
                winner = home if bool(game["home_won"]) else away
                trailing_won = 1 if winner == trailing else 0
            rows.append({
                "game_id": game["game_id"],
                "is_elimination": bool(is_elim),
                "trailing_team_won": trailing_won,
            })
            if bool(game["home_won"]):
                wins[home] = hw + 1
            else:
                wins[away] = aw + 1

    return pd.DataFrame(rows)


# ---- per-game derivation ----------------------------------------------------

def _possessions_per_team(ev: pd.DataFrame, home_id: int, away_id: int) -> pd.DataFrame:
    """Standard approximation: poss = FGA + 0.44*FTA − ORB + TOV, per team.

    Team rebounds (dead-ball, description contains 'TEAM') count as ORB for the
    opposing team — they end possessions even if not attributed to a player.
    Heaves (end-of-period shots) count as FGA; they are possessions.
    """
    rows = []
    for team_id, side in ((home_id, "HOME"), (away_id, "AWAY")):
        t = ev[ev["team_id"] == team_id]
        fga = int(t["canon_type"].isin(["shot_made", "shot_missed"]).sum())
        fta = int((t["canon_type"] == "freethrow").sum())
        tov = int((t["canon_type"] == "turnover").sum())
        sub = t["sub_type"].fillna("").str.lower()
        orb = int(((t["canon_type"] == "rebound") & sub.str.contains("off", na=False)).sum())
        poss = max(0.0, float(fga + 0.44 * fta - orb + tov))
        rows.append({
            "game_id": ev["game_id"].iloc[0],
            "team_side": side,
            "count": poss,
        })
    return pd.DataFrame(rows)


def _empty_game_tables() -> dict[str, pd.DataFrame]:
    return {k: pd.DataFrame() for k in (
        "events", "fouls", "possessions", "crew_games", "games",
    )}


def _build_one_game(
    pbp_game: pd.DataFrame,
    game_row: pd.Series,
    crew_row: pd.Series | None,
    series_row: pd.Series | None,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    discrepancies: list[str] = []
    gid = str(game_row["game_id"])
    home_id = int(game_row["home_team_id"])
    away_id = int(game_row["away_team_id"])

    ev = pbp_game.copy().reset_index(drop=True)
    if ev.empty:
        return _empty_game_tables(), [f"{gid}: empty_pbp"]

    # 1. period, clock, score
    ev["period_norm"] = ev["period"].map(_normalize_period)
    bad_p = int((ev["period_norm"] < 1).sum())
    if bad_p:
        discrepancies.append(f"{gid}: period_parse_failed={bad_p}")

    ev["clock_sec"] = ev["clock"].map(_parse_clock)
    bad_c = int((ev["clock_sec"] < 0).sum())
    if bad_c:
        discrepancies.append(f"{gid}: clock_parse_failed={bad_c}")
        ev = ev[ev["clock_sec"] >= 0].reset_index(drop=True)

    ev["home_score_int"] = ev["score_home"].map(_to_int).where(
        ev["score_home"].map(_to_int) >= 0, 0).astype(int)
    ev["away_score_int"] = ev["score_away"].map(_to_int).where(
        ev["score_away"].map(_to_int) >= 0, 0).astype(int)

    # 2. canonical order
    ev = ev.sort_values(
        ["period_norm", "clock_sec", "action_number"],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    ev["event_idx"] = np.arange(len(ev))

    # 3. previous-event score (for margin at event time)
    ev["home_score_prev"] = ev["home_score_int"].shift(1).fillna(0).astype(int)
    ev["away_score_prev"] = ev["away_score_int"].shift(1).fillna(0).astype(int)

    # 4. canonical type
    ev["canon_type"] = [
        _classify_event(r.action_type, r.sub_type, r.shot_result)
        for r in ev.itertuples(index=False)
    ]

    # 5. garbage-time and intentional tags
    margin_prev = (ev["home_score_prev"] - ev["away_score_prev"]).abs()
    ev["garbage_time"] = (
        (ev["period_norm"] == 4)
        & (ev["clock_sec"] <= GARBAGE_TIME_CLOCK_SEC)
        & (margin_prev > GARBAGE_TIME_MARGIN)
    )
    ev["intentional"] = [
        (ct == "foul" and _is_intentional_foul(st))
        for ct, st in zip(ev["canon_type"], ev["sub_type"].fillna(""))
    ]

    # 6. timing_delta_sec — zero for the pilot unless video is loaded
    ev["timing_delta_sec"] = 0.0

    # 7. fouls table
    fouls = ev[ev["canon_type"] == "foul"].copy()
    fouls["team_side"] = np.where(
        fouls["team_id"] == home_id, "HOME",
        np.where(fouls["team_id"] == away_id, "AWAY", "UNKNOWN"),
    )
    fouls = fouls[[
        "game_id", "event_idx", "period_norm", "clock_sec", "team_side",
        "person_id", "sub_type", "garbage_time", "intentional",
    ]].rename(columns={"period_norm": "period"})

    # 8. possessions
    poss = _possessions_per_team(ev, home_id, away_id)

    # 9. crew_games
    cg = pd.DataFrame()
    if crew_row is not None and pd.notna(crew_row.get("crew_code")):
        cg = pd.DataFrame([{
            "game_id": gid,
            "crew_code": crew_row["crew_code"],
            "home_team_id": home_id,
            "away_team_id": away_id,
        }])
    else:
        discrepancies.append(f"{gid}: crew_missing")

    # 10. games (one row)
    is_elim = bool(series_row["is_elimination"]) if series_row is not None else False
    trailing_won = (
        series_row["trailing_team_won"] if series_row is not None else None
    )
    games_out = pd.DataFrame([{
        "game_id": gid,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_score": int(ev["home_score_int"].iloc[-1]),
        "away_score": int(ev["away_score_int"].iloc[-1]),
        "n_events": len(ev),
        "n_periods": int(ev["period_norm"].max()),
        "is_elimination": is_elim,
        "trailing_team_won": (
            trailing_won if trailing_won is not None else np.nan
        ),
    }])

    return {
        "events": ev[[
            "game_id", "event_idx", "period_norm", "clock_sec", "canon_type",
            "team_id", "person_id", "description", "shot_value", "shot_result",
            "home_score_int", "away_score_int", "garbage_time", "intentional",
            "timing_delta_sec",
        ]].rename(columns={"period_norm": "period"}),
        "fouls": fouls,
        "possessions": poss,
        "crew_games": cg,
        "games": games_out,
    }, discrepancies


# ---- top-level --------------------------------------------------------------

def build_canonical(
    pbp_season: pd.DataFrame,
    crews_season: pd.DataFrame,
    games_season: pd.DataFrame,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Process every game in a season. Returns aggregated tables + discrepancies."""
    all_tables: dict[str, list[pd.DataFrame]] = {
        k: [] for k in ("events", "fouls", "possessions", "crew_games", "games")
    }
    all_discrepancies: list[str] = []

    if games_season.empty or pbp_season.empty:
        return {k: pd.DataFrame() for k in all_tables}, ["season: empty inputs"]

    crew_map = (
        crews_season.set_index("game_id").to_dict("index")
        if not crews_season.empty else {}
    )
    game_map = games_season.set_index("game_id", drop=False).to_dict("index")

    playoffs = games_season[games_season["season_type"] == "Playoffs"].copy()
    series_state = build_series_state(playoffs) if not playoffs.empty else pd.DataFrame()
    series_map = series_state.set_index("game_id").to_dict("index") if not series_state.empty else {}

    for gid, pbp_g in pbp_season.groupby("game_id"):
        gid = str(gid)
        if gid not in game_map:
            all_discrepancies.append(f"{gid}: no_game_meta")
            continue
        tables, discs = _build_one_game(
            pbp_g,
            pd.Series(game_map[gid]),
            pd.Series(crew_map[gid]) if gid in crew_map else None,
            pd.Series(series_map[gid]) if gid in series_map else None,
        )
        all_discrepancies.extend(discs)
        for k, df in tables.items():
            if not df.empty:
                all_tables[k].append(df)

    result = {
        k: (pd.concat(v, ignore_index=True) if v else pd.DataFrame())
        for k, v in all_tables.items()
    }
    return result, all_discrepancies


def foul_differential_per_100(
    crew_games: pd.DataFrame,
    fouls: pd.DataFrame,
    possessions: pd.DataFrame,
) -> pd.DataFrame:
    """Outcome variable for CREW_TENDENCY.

    y = (home_fouls − away_fouls) / total_poss × 100, excluding garbage-time
    and intentional-foul events. Total possessions = home + away.
    """
    if fouls.empty or crew_games.empty or possessions.empty:
        return pd.DataFrame(columns=["game_id", "crew_code", "y", "n_poss"])

    keep = fouls[~fouls["garbage_time"] & ~fouls["intentional"]]
    poss = possessions.groupby("game_id")["count"].sum().rename("n_poss")
    agg = keep.groupby(["game_id", "team_side"]).size().unstack(fill_value=0)
    agg["diff"] = agg.get("HOME", 0) - agg.get("AWAY", 0)
    agg = agg.join(poss, on="game_id")
    agg["y"] = agg["diff"] / agg["n_poss"].clip(lower=1) * 100

    out = agg.reset_index().merge(
        crew_games[["game_id", "crew_code"]],
        on="game_id", how="left",
    )
    return (
        out[["game_id", "crew_code", "y", "n_poss"]]
        .dropna(subset=["crew_code"])
        .reset_index(drop=True)
    )
