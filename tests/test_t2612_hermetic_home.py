"""[T2612] No test sees kuhy's real HOME: a suite run deleted his visibility cache and his gateway key."""

import os
from pathlib import Path

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
