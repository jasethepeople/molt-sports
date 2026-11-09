"""T01–T10 conformance suite. A family that fails any test cannot ship."""
from __future__ import annotations

import ast
import inspect
import pathlib

FORBIDDEN_IMPORTS = {"time", "os", "socket", "requests", "urllib", "secrets"}
ALLOWED_NONDET = {"numpy.random.Generator"}


def t03_no_forbidden_imports(family_cls) -> list[str]:
    src = inspect.getsource(inspect.getmodule(family_cls))
    tree = ast.parse(src)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in FORBIDDEN_IMPORTS:
                    violations.append(f"forbidden import: {a.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FORBIDDEN_IMPORTS:
                violations.append(f"forbidden import: {node.module}")
    return violations


def t02_deterministic_3x(family_cls, ctx, df, runner) -> list[str]:
    """Run the family three times with identical seed; require identical output hash."""
    from verify.replay import result_hash
    hashes = set()
    for _ in range(3):
        r = family_cls().run(ctx, df)
        hashes.add(result_hash(r))
    return [] if len(hashes) == 1 else [f"non-deterministic: {hashes}"]


def t10_notes_not_in_output_path(family_cls) -> list[str]:
    """`notes` may never be parsed by the engine. Static scan for .notes usage."""
    src = inspect.getsource(inspect.getmodule(family_cls))
    bad = [ln for ln in src.splitlines() if ".notes" in ln and "notes=" not in ln and "notes:" not in ln]
    return [f"notes referenced: {b.strip()}" for b in bad]


def run_conformance(family_cls, ctx, df) -> list[str]:
    failures: list[str] = []
    failures += t03_no_forbidden_imports(family_cls)
    failures += t02_deterministic_3x(family_cls, ctx, df, runner=None)
    failures += t10_notes_not_in_output_path(family_cls)
    # TODO(PILOT): T01 schema, T04 validate-catches, T05 power gate,
    # T06 null-on-underpower, T07 replay manifest, T08 holdout, T09 adjustment set
    return failures
