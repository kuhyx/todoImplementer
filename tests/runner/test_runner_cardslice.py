"""Each card runs in its own capped slice, so one card's job can never freeze every other card (T2405-T2401).

2026-11-20: an SD3.5-Large render (16 GB RAM + 8 GB swap) pushed the shared todoimpl.slice over MemoryHigh;
the kernel throttled every process in the slice, claude included, and all five running cards sat 47 min with
no activity. Now every card gets `todoimpl-<card>.slice` (a hard cap, no MemoryHigh), the parent has no
MemoryHigh either, and a session's own `systemd-run --slice=todoimpl.slice` job joins its card's slice.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from todoimpl.runner import buildlock, cardslice, deploy, gate, launch

REPO = Path(__file__).resolve().parents[2]
DROPIN = REPO / "deploy" / cardslice.DROPIN_DIR / cardslice.DROPIN_FILE
CARD = "21b9c44a-0"


def _settings(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    pairs = (line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
    return {key.strip(): value.strip() for key, value in pairs}


def _gib(value: str) -> float:
    assert value.endswith("G"), value
    return float(value[:-1])


def test_t2405_card_slice_is_one_level_below_the_board_slice() -> None:
    assert cardslice.card_slice(CARD) == "todoimpl-21b9c44a_0.slice"
    assert cardslice.card_slice("a.b-1") == "todoimpl-a_b_1.slice"


def test_t2405_turn_gate_and_deploy_units_join_their_cards_slice(tmp_path: Path) -> None:
    run_dir = tmp_path / CARD
    turn = launch.systemd_argv("u1", run_dir, "implement-1.000")
    check = gate.systemd_argv("u2", run_dir, run_dir / "wt")
    ship = deploy.systemd_argv("u3", run_dir, run_dir / "wt", "scripts/deploy.sh")
    for argv in (turn, check, ship):
        assert "--slice=todoimpl-21b9c44a_0.slice" in argv[: argv.index("--")]
    # An OOM kill of a build below claude must not stop the whole turn: claude sees the failed command.
    assert "OOMPolicy=continue" in turn[: turn.index("--")]


def test_t2400_card_slices_are_hard_capped_and_nothing_throttles_the_whole_board() -> None:
    card = _settings(DROPIN)
    parent = _settings(REPO / "deploy" / launch.SLICE)
    assert "MemoryHigh" not in card
    assert "MemoryHigh" not in parent  # memory.high throttled every card at once (2026-11-20)
    assert _gib(card["MemoryMax"]) < _gib(parent["MemoryMax"])
    assert 0 < _gib(card["MemorySwapMax"]) <= 2


def test_t2400_deploy_installs_the_card_dropin_before_the_reload() -> None:
    script = (REPO / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    install = script.index(f'install_unit "{cardslice.DROPIN_DIR}/{cardslice.DROPIN_FILE}"')
    assert install < script.index("systemctl --user daemon-reload")


def test_t2401_turn_env_names_the_cards_slice() -> None:
    assert buildlock.turn_env(CARD)[cardslice.SLICE_VAR] == "todoimpl-21b9c44a_0.slice"


@pytest.fixture
def shim(tmp_path: Path) -> tuple[Path, Path]:
    """Return the board's shim dir plus a fake real systemd-run that prints its argv, one per line."""
    shims = buildlock.ensure(tmp_path / "root")
    real = tmp_path / "bin"
    real.mkdir()
    fake = real / "systemd-run"
    fake.write_text('#!/bin/bash\nprintf "%s\\n" "$@"\n', encoding="utf-8")
    fake.chmod(0o755)
    return shims, real


def _run(shim: tuple[Path, Path], *args: str, slice_: str | None = "todoimpl-c_0.slice") -> list[str]:
    shims, real = shim
    env = {"PATH": f"{shims}:{real}:/usr/bin:/bin", "HOME": os.environ["HOME"]}
    if slice_ is not None:
        env[cardslice.SLICE_VAR] = slice_
    done = subprocess.run(
        [str(shims / "systemd-run"), *args], env=env, capture_output=True, text=True, check=True
    )
    return done.stdout.splitlines()


def test_t2401_a_sessions_board_slice_job_joins_its_cards_slice(shim: tuple[Path, Path]) -> None:
    assert _run(shim, "--user", "--slice=todoimpl.slice", "--wait", "make") == [
        "--user", "--slice=todoimpl-c_0.slice", "--wait", "make",
    ]  # fmt: skip
    assert _run(shim, "--user", "--slice", "todoimpl.slice", "x") == [
        "--user",
        "--slice",
        "todoimpl-c_0.slice",
        "x",
    ]


def test_t2401_other_units_pass_through_untouched(shim: tuple[Path, Path]) -> None:
    # No slice: a session deploying a real service must not put it in its card (a Cancel would stop it).
    assert _run(shim, "--user", "--unit=web", "node", "s.js") == ["--user", "--unit=web", "node", "s.js"]
    assert _run(shim, "--user", "--slice=app.slice", "x") == ["--user", "--slice=app.slice", "x"]
    assert _run(shim, "--user", "--", "x", "--slice=todoimpl.slice") == [
        "--user",
        "--",
        "x",
        "--slice=todoimpl.slice",
    ]
    assert _run(shim, "--user", "--slice=todoimpl.slice", "x", slice_=None) == [
        "--user",
        "--slice=todoimpl.slice",
        "x",
    ]


def test_t2401_cancel_stops_the_cards_whole_slice(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv(launch.LAUNCH_VAR, "systemd")

    def fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(launch, "_run", fake_run)
    cardslice.stop(CARD)
    assert calls == [["systemctl", "--user", "stop", "todoimpl-21b9c44a_0.slice"]]
    monkeypatch.setenv(launch.LAUNCH_VAR, "direct")
    cardslice.stop(CARD)
    assert len(calls) == 1  # tests never touch systemd
