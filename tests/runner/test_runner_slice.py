"""Every board unit (turn, gate, deploy) runs in the capped todoimpl.slice (T1982)."""

from __future__ import annotations

from pathlib import Path

from todoimpl.runner import deploy, gate, launch

REPO = Path(__file__).resolve().parents[2]
SLICE_FILE = REPO / "deploy" / launch.SLICE
FLAG = "--slice=todoimpl-"  # a card's own slice, one level below todoimpl.slice (T2405)


def _slice_settings() -> dict[str, str]:
    """Read the key=value lines of the slice file; systemd keys are case-sensitive."""
    lines = SLICE_FILE.read_text(encoding="utf-8").splitlines()
    pairs = (line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
    return {key.strip(): value.strip() for key, value in pairs}


def _gib(value: str) -> float:
    assert value.endswith("G"), value
    return float(value[:-1])


def test_t1982_turn_gate_and_deploy_units_join_the_capped_slice(tmp_path: Path) -> None:
    turn = launch.systemd_argv("u1", tmp_path, "implement-1.000")
    check = gate.systemd_argv("u2", tmp_path, tmp_path / "wt")
    ship = deploy.systemd_argv("u3", tmp_path, tmp_path / "wt", "scripts/deploy.sh")
    for argv in (turn, check, ship):
        assert any(arg.startswith(FLAG) for arg in argv[: argv.index("--")])


def test_t1982_the_slice_caps_memory_swap_and_cpu() -> None:
    cfg = _slice_settings()
    # Swap is capped too: with RAM full and swap open, the slice thrashed the whole desktop to a freeze.
    assert _gib(cfg["MemoryMax"]) <= 20  # no MemoryHigh: its throttling froze every card at once (T2400)
    assert 0 < _gib(cfg["MemorySwapMax"]) <= 8
    assert cfg["CPUQuota"].endswith("%")
    assert int(cfg["CPUQuota"][:-1]) <= 1600
    assert int(cfg["CPUWeight"]) < 100
    assert int(cfg["TasksMax"]) > 0


def test_t1982_deploy_installs_the_slice_before_the_restart() -> None:
    script = (REPO / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert f"readonly SLICE={launch.SLICE}\n" in script
    install = script.index('install_unit "$SLICE"')
    assert install < script.index("systemctl --user daemon-reload")
