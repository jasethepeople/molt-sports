# molt-sports-pilot

Week-one design validation. Not the product.

## Day 1
    pip install -e .
    python -m data.sources          # populate cache (rate-limited, ~2h)

## Day 2
    python run.py                    # canary + determinism check
    # if canary > 0.5% → stop and fix ingestion

## Days 3–7
    Implement the TODOs in data/canonical.py and data/sources.py.
    Re-run. Inspect out/pilot_report.json.
    Fill the human-review sheet from out/labels/.

## Pass criteria
    See conversation §D. Ten items. Any failure is a release blocker.
