"""A board turn gets its own PYTHONUSERBASE: pip in a worktree leaves kuhy's real user site alone (T2495)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from runnerfakes import Env
from todoimpl.runner import claude, userbase

PY = "/usr/bin/python3"  # what a worker runs; the suite's own venv python reads no user site
pytestmark = pytest.mark.skipif(not Path(PY).exists(), reason="needs the system python3")


def _tag() -> str:
    """Return the `pythonX.Y` dir name of the interpreter the tests drive."""
    out = subprocess.run(
        [PY, "-c", "import sys; print('python%d.%d' % sys.version_info[:2])"],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return out.stdout.strip()


def _real_site(world: Env, tag: str | None = None) -> Path:
    site = world.home / ".local" / "lib" / (tag or _tag()) / "site-packages"
    site.mkdir(parents=True, exist_ok=True)
    return site


def _worker(world: Env, card: str = "c1-0") -> tuple[dict[str, str], Path]:
    wt = world.root / card / "wt"
    wt.mkdir(parents=True, exist_ok=True)
    return claude.build("implement", "p", wt).env, wt.parent


def _py(env: dict[str, str], code: str) -> str:
    done = subprocess.run(
        [PY, "-c", code],
        env={**env, "PYTHONDONTWRITEBYTECODE": "1"},
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return done.stdout.strip()


def _snapshot(root: Path) -> list[tuple[str, int]]:
    return sorted((str(p.relative_to(root)), p.stat().st_mtime_ns) for p in root.rglob("*"))


def test_t2495_a_turn_gets_a_python_user_base_of_its_own_in_its_run_dir(world: Env) -> None:
    _real_site(world)
    env, run_dir = _worker(world)
    assert env["PYTHONUSERBASE"] == str(run_dir / "userbase")
    assert env["PYTHONUSERBASE"] != str(world.home / ".local")


def test_t2495_each_card_has_its_own_base(world: Env) -> None:
    first, _ = _worker(world, "c1-0")
    second, _ = _worker(world, "c2-0")
    assert first["PYTHONUSERBASE"] != second["PYTHONUSERBASE"]


def test_the_base_mirrors_each_real_site_with_a_pth_that_adds_it(world: Env) -> None:
    real = _real_site(world, "python3.99")
    _real_site(world, "python3.98")
    (world.home / ".local" / "lib" / "python3.97").mkdir()  # no site-packages: nothing to mirror
    _, run_dir = _worker(world)
    lib = run_dir / "userbase" / "lib"
    assert sorted(p.name for p in lib.iterdir()) == ["python3.98", "python3.99"]
    pth = lib / "python3.99" / "site-packages" / userbase.PTH
    assert pth.read_text(encoding="utf-8") == f"import site; site.addsitedir({str(real)!r})\n"


def test_a_second_turn_of_the_card_rewrites_nothing(world: Env) -> None:
    _real_site(world)
    _, run_dir = _worker(world)
    before = _snapshot(run_dir / "userbase")
    _worker(world)
    assert _snapshot(run_dir / "userbase") == before


def test_a_user_base_the_server_already_has_is_the_real_one(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = world.tmp / "kuhys-base"
    (other / "lib" / "python3.99" / "site-packages").mkdir(parents=True)
    monkeypatch.setenv("PYTHONUSERBASE", str(other))
    _, run_dir = _worker(world)
    pth = run_dir / "userbase" / "lib" / "python3.99" / "site-packages" / userbase.PTH
    assert str(other) in pth.read_text(encoding="utf-8")


def test_the_worker_still_sees_the_real_site_and_its_pth_files(world: Env) -> None:
    real = _real_site(world)
    (real / "onlyreal.py").write_text("MARK = 'real'\n", encoding="utf-8")
    (world.tmp / "elsewhere").mkdir()
    (world.tmp / "elsewhere" / "viapth.py").write_text("MARK = 'pth'\n", encoding="utf-8")
    (real / "editable.pth").write_text(f"{world.tmp / 'elsewhere'}\n", encoding="utf-8")
    env, _ = _worker(world)
    assert _py(env, "import onlyreal, viapth; print(onlyreal.MARK, viapth.MARK)") == "real pth"


def test_a_package_the_worker_installs_shadows_the_real_one_only_there(world: Env) -> None:
    real = _real_site(world)
    (real / "shadowme.py").write_text("MARK = 'real'\n", encoding="utf-8")
    env, run_dir = _worker(world)
    mine = run_dir / "userbase" / "lib" / _tag() / "site-packages"
    (mine / "shadowme.py").write_text("MARK = 'worker'\n", encoding="utf-8")
    before = _snapshot(real)
    assert _py(env, "import shadowme; print(shadowme.MARK)") == "worker"
    outside = {**env, "PYTHONUSERBASE": str(world.home / ".local")}
    assert _py(outside, "import shadowme; print(shadowme.MARK)") == "real"
    assert _snapshot(real) == before


def _scratch_package(root: Path) -> Path:
    pkg = root / "probe_pkg"
    (pkg / "probe_pkg").mkdir(parents=True)
    (pkg / "probe_pkg" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\nbuild-backend = "setuptools.build_meta"\n'
        '[project]\nname = "probe_pkg"\nversion = "0.0.1"\n[tool.setuptools]\npackages = ["probe_pkg"]\n',
        encoding="utf-8",
    )
    return pkg


def _pip_install(env: dict[str, str], pkg: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    argv = [PY, "-m", "pip", "install", "-q", "--no-build-isolation", "--no-deps", *flags, "-e", str(pkg)]
    return subprocess.run(argv, env=env, capture_output=True, text=True, timeout=50, check=False)


@pytest.mark.skipif(
    subprocess.run([PY, "-c", "import pip, setuptools"], capture_output=True, check=False).returncode != 0,
    reason="needs pip and setuptools in python3",
)
@pytest.mark.parametrize("flags", [("--break-system-packages",), ("--break-system-packages", "--user")])
def test_t2495_pip_install_in_a_worker_leaves_the_real_user_site_alone(
    world: Env, flags: tuple[str, ...]
) -> None:
    real = _real_site(world)
    env, run_dir = _worker(world)
    before = _snapshot(world.home / ".local")
    done = _pip_install(env, _scratch_package(world.tmp), *flags)
    assert done.returncode == 0, done.stderr
    assert _snapshot(world.home / ".local") == before
    assert any(run_dir.joinpath("userbase").rglob("*probe_pkg*"))
    assert not list(real.glob("*probe_pkg*"))


@pytest.mark.skipif(
    subprocess.run([PY, "-c", "import pip, setuptools"], capture_output=True, check=False).returncode != 0,
    reason="needs pip and setuptools in python3",
)
def test_control_without_the_base_the_same_install_lands_in_the_real_site(world: Env) -> None:
    real = _real_site(world)
    env = {**os.environ, "HOME": str(world.home)}
    env.pop("PYTHONUSERBASE", None)
    done = _pip_install(env, _scratch_package(world.tmp), "--break-system-packages", "--user")
    assert done.returncode == 0, done.stderr
    assert list(real.glob("*probe_pkg*"))


def test_turn_env_takes_an_explicit_real_base(world: Env) -> None:
    real = world.tmp / "fakereal"
    (real / "lib" / "python3.99" / "site-packages").mkdir(parents=True)
    got = userbase.turn_env(world.root / "c9-0", {"HOME": str(world.home)}, real=real)
    assert got == {"PYTHONUSERBASE": str(world.root / "c9-0" / "userbase")}
    assert (world.root / "c9-0" / "userbase" / "lib" / "python3.99" / "site-packages" / userbase.PTH).exists()
