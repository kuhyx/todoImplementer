"""A worker's editable install shadows kuhy's plain copy of the same package (T2502).

setuptools' editable finder (flat layout, `pip install -e .` in a gatelock worktree) sits on `sys.meta_path`
after `PathFinder`, so the plain `gatelock/` in kuhy's real site, which the turn's `.pth` puts on `sys.path`,
won: the worker tested the real gatelock, not its own. The turn's `.pth` now moves the turn's own finders
before PathFinder.
"""

from __future__ import annotations

import site
import subprocess
import sys
import types
from importlib.machinery import PathFinder
from pathlib import Path

import pytest
from runnerfakes import Env
from test_runner_userbase import PY, _pip_install, _py, _real_site, _scratch_package, _worker
from todoimpl.runner import userbase_site

pytestmark = pytest.mark.skipif(
    subprocess.run([PY, "-c", "import pip, setuptools"], capture_output=True, check=False).returncode != 0,
    reason="needs pip and setuptools in python3",
)
SHOW = "import probe_pkg; print(probe_pkg.__file__)"


def test_t2502_a_workers_editable_install_beats_the_real_plain_copy(world: Env) -> None:
    real = _real_site(world)
    (real / "probe_pkg").mkdir()
    (real / "probe_pkg" / "__init__.py").write_text("", encoding="utf-8")
    env, _ = _worker(world)
    pkg = _scratch_package(world.tmp)
    done = _pip_install(env, pkg, "--break-system-packages", "--user")
    assert done.returncode == 0, done.stderr
    assert Path(_py(env, SHOW)).is_relative_to(pkg)
    outside = {**env, "PYTHONUSERBASE": str(world.home / ".local")}
    assert Path(_py(outside, SHOW)).is_relative_to(real)


class _Finder:
    """A meta path finder whose module is set per test."""


def _finder_from(module: str, file: Path | None, monkeypatch: pytest.MonkeyPatch) -> type:
    mod = types.ModuleType(module)
    if file is not None:
        mod.__file__ = str(file)
    monkeypatch.setitem(sys.modules, module, mod)
    return type(f"F_{module}", (_Finder,), {"__module__": module})


def test_add_moves_only_the_turns_own_finders_before_pathfinder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mine = tmp_path / "turn"
    added: list[str] = []
    monkeypatch.setattr(site, "addsitedir", added.append)
    own = _finder_from("own_finder", mine / "own_finder.py", monkeypatch)
    real = _finder_from("real_finder", tmp_path / "real" / "real_finder.py", monkeypatch)
    bare = _finder_from("bare_finder", None, monkeypatch)
    first = object()
    monkeypatch.setattr(sys, "meta_path", [first, PathFinder, real, own, bare])
    userbase_site.add("/real/site", mine)
    assert added == ["/real/site"]
    assert sys.meta_path == [first, own, PathFinder, real, bare]


def test_add_without_pathfinder_appends_and_defaults_to_its_own_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(site, "addsitedir", lambda _: None)
    here = Path(userbase_site.__file__).parent
    own = _finder_from("here_finder", here / "here_finder.py", monkeypatch)
    other = object()
    monkeypatch.setattr(sys, "meta_path", [own, other])
    userbase_site.add(str(tmp_path))
    assert sys.meta_path == [other, own]
