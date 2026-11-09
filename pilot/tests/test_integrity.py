"""Sanity tests for the integrity module. Run: pytest tests/ -q"""
import pandas as pd
import pytest

from synth.integrity import frame_hash, IntegrityError, verify_report_integrity
import json, pathlib, tempfile


def _toy_df(seed: int = 0) -> pd.DataFrame:
    return pd.DataFrame({
        "game_id": ["G1", "G2", "G3"],
        "crew_code": ["C1", "C2", "C3"],
        "y": [0.5 + seed * 0.01, -0.2, 1.1],
    })


def test_frame_hash_deterministic():
    assert frame_hash(_toy_df()) == frame_hash(_toy_df())


def test_frame_hash_row_order_insensitive():
    a = _toy_df()
    b = a.sample(frac=1, random_state=42).reset_index(drop=True)
    assert frame_hash(a) == frame_hash(b)


def test_frame_hash_detects_change():
    assert frame_hash(_toy_df()) != frame_hash(_toy_df(seed=1))


def test_verify_refuses_when_hold_df_changes(tmp_path):
    # Build a minimal fake report with one scenario
    from synth.inject import inject
    hold = _toy_df()
    hold["is_elimination"] = [False, False, False]
    hold["trailing_team_won"] = [0, 0, 0]

    inj, label_hash = inject(hold, "T-NULL", seed=100)
    report = {
        "hold_df_hash": frame_hash(hold),
        "pandas_version": pd.__version__,
        "n_holdout_rows": len(hold),
        "injections": {
            "T-NULL": {
                "label_hash": label_hash,
                "frame_hash": frame_hash(inj),
                "seed": 100,
            }
        },
    }
    p = tmp_path / "pilot_report.json"
    p.write_text(json.dumps(report))

    # Correct frame → passes
    r = verify_report_integrity(p, hold, tmp_path)
    assert r.ok and r.scenarios_checked == 1

    # Tampered frame → refuses
    bad = hold.copy()
    bad.loc[0, "y"] = 99.0
    with pytest.raises(IntegrityError, match="HOLDOUT FRAME CHANGED"):
        verify_report_integrity(p, bad, tmp_path)
