"""Synthetic injection generator. Labels are written to a sealed file the
families never see. Deterministic given seed."""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd
import blake3


SYNTH_CREW = "CREW-SYNTH-001"


def _seal(obj: dict, out: pathlib.Path) -> str:
    blob = json.dumps(obj, sort_keys=True).encode()
    h = "blake3:" + blake3.blake3(blob).hexdigest()
    out.write_bytes(blob)
    return h


def inject(
    holdout: pd.DataFrame,
    scenario: str,
    seed: int,
    labels_dir: pathlib.Path = pathlib.Path("out/labels"),
) -> tuple[pd.DataFrame, str]:
    labels_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    df = holdout.copy()
    labels: dict = {"scenario": scenario, "seed": seed, "injected_games": []}

    if scenario == "T-NULL":
        pass

    elif scenario in ("T-SMALL", "T-LARGE"):
        pct = 0.005 if scenario == "T-SMALL" else 0.05
        elig = df.index[df["crew_code"] != SYNTH_CREW].to_numpy()
        pick = rng.choice(elig, size=max(1, int(len(df) * pct)), replace=False)
        df.loc[pick, "crew_code"] = SYNTH_CREW
        df.loc[pick, "y"] = df.loc[pick, "y"] + 1.5
        labels["injected_games"] = pick.tolist()

    elif scenario == "T-DIFFUSE":
        synth_crews = [f"CREW-SYNTH-{i:03d}" for i in range(1, 21)]
        for s in synth_crews:
            elig = df.index[~df["crew_code"].str.startswith("CREW-SYNTH")].to_numpy()
            pick = rng.choice(elig, size=max(1, int(len(df) * 0.003)), replace=False)
            df.loc[pick, "crew_code"] = s
            df.loc[pick, "y"] = df.loc[pick, "y"] + 0.3
            labels["injected_games"] += pick.tolist()

    elif scenario == "T-EXTENSION":
        elig = df.index[df["is_elimination"]].to_numpy()
        n_inject = max(1, int(len(elig) * 0.15))
        pick = rng.choice(elig, size=n_inject, replace=False)
        df.loc[pick, "trailing_team_won"] = 1
        labels["injected_games"] = pick.tolist()

    elif scenario == "T-DEAD":
        elig = df.index[~df["is_elimination"]].to_numpy()
        pick = rng.choice(elig, size=max(1, int(len(elig) * 0.15)), replace=False)
        df.loc[pick, "trailing_team_won"] = 1
        labels["injected_games"] = pick.tolist()

    else:
        raise ValueError(scenario)

    label_hash = _seal(labels, labels_dir / f"{scenario}_seed{seed}.json")
    return df, label_hash
