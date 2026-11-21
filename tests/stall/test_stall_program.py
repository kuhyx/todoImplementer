"""A job's stall signature names the program it really runs, read from its whole script (T2438-T2441)."""

from __future__ import annotations

import pytest
from todoimpl.stall import program

RUN = "/home/kuhy/.cache/todoImplementer"


@pytest.mark.parametrize(
    ("script", "word"),
    [
        (
            f"PYTHONPATH=/x/server /x/.venv/bin/python -m todoimpl.repotask.tick {RUN}/21b9c44a-0 done k",
            "python",
        ),
        ('s=$(date +%s); make fast > ../fast.log 2>&1; echo "rc=$? $(( $(date +%s) - s ))"', "make"),
        (f'L={RUN}/d3142f69-0/logs/gd_full.log; godot --headless --path wt > "$L" 2>&1', "godot"),
        ("X=1", "shell"),
        ("", "shell"),
        ("cd /x", "shell"),
        ("for f in a b; do :; done", "shell"),
    ],
)
def test_t2438_no_stall_is_job_unknown(script: str, word: str) -> None:
    assert program.name(script) == word


@pytest.mark.parametrize(
    ("script", "word"),
    [
        (f"cd {RUN}/f3c4d316-0/children/f3c4d316-1/wt && make fast", "make"),
        (f"cat > {RUN}/ba5c3ff1-0/scratch/r <<'EOF'\nimport os\nrm -rf x\nEOF\npython3 r", "python3"),
        ("rm -f tests/chips/a.gd tests/chips/b.gd; pytest -q", "pytest"),
        ("rm -rf /big/tree", "rm"),
        ("export A=1; set -e; nice -n 19 ionice -c 3 cargo build", "cargo"),
        ("python3 - <<'PY'\nprint(1)\nPY", "python3"),
        (".venv/bin/ruff format -q tests/x.py && git diff --stat", "ruff"),
        ("pnpm --dir web -s remove uqr 2>&1 | tail -2; git diff --stat", "pnpm"),
        ("journalctl --user -f -o cat -u kartka-deploy 2>&1 | tail", "journalctl"),
        ("timeout -k 5 50s tail --pid=1 -f /dev/null", "tail"),
        ("timeout 58 ~/.claude/scripts/capped.sh make test-shard SHARD=1 COV_DIR=/x", "make"),
        ("SKIP=pytest timeout 58 ~/.claude/scripts/capped.sh make web-test", "make"),
        ("CAP_MEM=4G ~/.claude/scripts/capped.sh pytest -q", "pytest"),
        ('bash -lc "cd /x && pnpm test"', "pnpm"),
        ("if [ -f x ]; then make -s; fi", "make"),
        ("( cd x; cargo test )", "cargo"),
        ('make "unbalanced', "make"),
        ("sudo -u root <<< x pacman -Syu", "pacman"),
    ],
)
def test_t2439_setup_and_chores_in_front_name_the_real_program(script: str, word: str) -> None:
    assert program.name(script) == word


@pytest.mark.parametrize(
    "script",
    [
        f"{RUN}/ba5c3ff1-0/scratch/sh.sh 4",
        f"{RUN}/ba5c3ff1-0/scratch/shs.sh",
        "bash scratch/gate.sh",
        (
            "systemd-run --user --collect --slice=todoimpl.slice --wait -p MemoryMax=4G -E PATH "
            f"bash {RUN}/a/scratch/x.sh"
        ),
    ],
)
def test_t2440_a_cards_throwaway_scripts_share_one_signature(script: str) -> None:
    assert program.name(script) == "script"


def test_t2440_a_repo_script_keeps_its_name() -> None:
    assert program.name("systemd-run --user --wait --unit=x make -s test") == "make"
    assert program.name("bash scripts/test.sh 3") == "test.sh"
    assert program.name("bash") == "bash"
    assert program.name("bash -c") == "bash"
    assert program.name('"" ; make') == "make"  # an empty word names nothing
