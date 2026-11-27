"""[T2612] No test sees kuhy's real HOME: a suite run deleted his visibility cache and his gateway key."""

import os
from pathlib import Path

import home_guard
from todoimpl.runner import freeok

REAL_HOME = Path.home()  # read at import, before the autouse fixtures run


def test_t2612_every_test_runs_in_a_temp_home() -> None:
    assert Path.home() != REAL_HOME
    assert not str(Path.home()).startswith(f"{REAL_HOME}/")


def test_t2612_xdg_dirs_leave_the_real_home_alone() -> None:
    for name in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        value = os.environ.get(name)
        assert value is None or not value.startswith(f"{REAL_HOME}/"), name


def test_t2612_free_route_files_sit_in_the_temp_home() -> None:
    assert not str(Path.home() / freeok.VISIBILITY).startswith(f"{REAL_HOME}/")


def test_t2612_a_write_under_the_real_home_is_caught() -> None:
    real, repo = f"{REAL_HOME}/.config/x", str(Path(__file__).resolve().parents[1] / "x")
    home_guard.take()
    for event, args in [
        ("open", (real, "w", 0)),
        ("open", (real, None, os.O_WRONLY)),
        ("os.remove", (real, None)),
        ("open", (real, "r", 0)),  # a read
        ("open", (real, None, os.O_RDONLY)),
        ("open", (repo, "w", 0)),  # the repo's own dir
        ("open", ("/elsewhere/x", "w", 0)),
        ("open", (3, "w", 0)),  # a file descriptor
        ("os.listdir", (real,)),  # not a write
        ("os.symlink", (real, "/elsewhere/link", None)),  # a link that points into HOME writes elsewhere
        ("os.rename", ("/elsewhere/x", real, None, None)),
    ]:
        home_guard.hook(event, args)
    assert home_guard.take() == [f"open {real}", f"open {real}", f"os.remove {real}", f"os.rename {real}"]
