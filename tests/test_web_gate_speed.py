"""The web gate fits the 60 s cap at the default 10 % CPU on a loaded machine (T2520).

At load 16-20 `make web-lint` ran 60 s+ (eslint alone 52 s on one thread) and `make web-test` 42 s (jsdom
built 90 times on 23 workers sharing 2.4 cores). These pins keep the fixes: one type-check, two eslint threads
with no cache, and vitest reusing one jsdom per worker on a worker count the cap can feed.
"""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _lint_commands() -> list[str]:
    assert json.loads((WEB / "package.json").read_text())["scripts"]["lint"] == "bash dev/lint.sh"
    lines = (WEB / "dev" / "lint.sh").read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def test_t2520_lint_type_checks_once() -> None:
    # `astro check` covers every .ts file `tsc --noEmit` did, plus the .astro files; `astro sync` runs once.
    commands = _lint_commands()
    assert "astro sync" in commands
    assert 'astro check --noSync >"$report" 2>&1 &' in commands
    assert not [c for c in commands if c.startswith("tsc")]


def test_t2520_eslint_runs_two_threads_without_a_cache() -> None:
    # The eslint cache is per file, so a type change in an import leaves a stale green on its users.
    assert [c for c in _lint_commands() if "eslint " in c] == ["eslint --concurrency 2 . || lint_rc=$?"]


def test_t2520_vitest_reuses_one_jsdom_per_worker() -> None:
    config = (WEB / "vitest.config.ts").read_text()
    assert re.search(r'^\s*pool: "vmThreads",$', config, re.MULTILINE)
    assert re.search(r"^\s*maxWorkers: 3,$", config, re.MULTILINE)


def _recipe(target: str) -> str:
    return (ROOT / "Makefile").read_text().split(f"\n{target}:\n", 1)[1].split("\n\n", 1)[0]


def test_t2520_only_web_lint_gets_the_4g_memory_ceiling() -> None:
    # Two eslint threads each hold the TypeScript program and the plugins: 3.1 GB peak, over the 2 GiB cap.
    # vitest fits the default 2 GiB, and the gate keeps it there.
    assert "CAP_MEM=4G $(WEBCAP) lint" in _recipe("web-lint")
    assert "CAP_MEM" not in _recipe("web-test")
    webcap = subprocess.run(
        ["make", "-s", "-C", str(ROOT), "--eval", "print-%: ; @echo $($*)", "print-WEBCAP", "CAP=CAPPED"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "CAP_MEM" not in webcap
