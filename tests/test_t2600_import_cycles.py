"""Every command-line module of the server imports first, alone, in a fresh interpreter (T2600).

2026-11-27: `python -m todoimpl.nolimit.tick` died on an import cycle (`nolimit.context` -> `runner.checks`
-> ... -> `prompts.nolimitctx` -> `nolimit.context`, half initialised) while every test passed: pytest had
already imported the modules in another order. Importing each `python -m` module first, alone, finds such a
cycle in any package. (A library module may sit in a cycle the entry points resolve; an entry point must
not.)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "server"
PROBE = """
import importlib, sys, traceback
bad = []
for name in sys.argv[1:]:
    for key in [k for k in sys.modules if k == "todoimpl" or k.startswith("todoimpl.")]:
        del sys.modules[key]
    try:
        importlib.import_module(name)
    except ImportError:
        bad.append(name + ": " + traceback.format_exc().strip().splitlines()[-1])
print("\\n".join(bad))
"""


def _entry_points() -> list[str]:
    """Return every module with a `__main__` guard: the ones `python -m` runs first."""
    return [
        ".".join(path.relative_to(SERVER).with_suffix("").parts)
        for path in sorted((SERVER / "todoimpl").rglob("*.py"))
        if '__name__ == "__main__"' in path.read_text(encoding="utf-8")
    ]


def test_t2600_every_entry_point_imports_first_without_a_cycle() -> None:
    modules = _entry_points()
    assert "todoimpl.nolimit.tick" in modules
    done = subprocess.run(
        [sys.executable, "-c", PROBE, *modules],
        env={"PYTHONPATH": str(SERVER), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
        timeout=50,
    )
    assert done.stdout.strip() == ""
