"""Setup and autofix steps come from the repo's own lockfiles and config."""

from __future__ import annotations

import json
from pathlib import Path

from todoimpl.nolimit import fixes


def write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (root / rel).write_text(text, encoding="utf-8")
    return root


def test_nothing_configured_means_no_steps(tmp_path: Path) -> None:
    assert fixes.setup(tmp_path) == []
    assert fixes.autofix(tmp_path) == []


def test_a_uv_repo_with_ruff(tmp_path: Path) -> None:
    write(tmp_path, {"uv.lock": "", "pyproject.toml": "[tool.ruff]\nline-length = 110\n"})
    assert fixes.setup(tmp_path) == [("setup-uv", fixes.UV_SETUP)]
    [(name, command)] = fixes.autofix(tmp_path)
    assert name == "fix-ruff"
    assert command.startswith("uv run --frozen ruff check --fix-only")


def test_a_ruff_toml_without_uv_and_a_bad_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_bytes(b"\xff")
    write(tmp_path, {"ruff.toml": ""})
    [(_, command)] = fixes.autofix(tmp_path)
    assert command.startswith("ruff check")


def test_t2550_eslint_and_prettier_fix_only_what_the_repos_scripts_lint(tmp_path: Path) -> None:
    scripts = {
        "lint": "astro sync && tsc --noEmit && eslint src && astro check",
        "fmt": "prettier --check src",
    }
    package = {"scripts": scripts, "devDependencies": {"eslint": "1", "prettier": "1"}}
    write(tmp_path, {"pnpm-lock.yaml": "", "package.json": json.dumps(package)})
    assert fixes.setup(tmp_path) == [("setup-pnpm", fixes.PNPM_SETUP)]
    assert fixes.autofix(tmp_path) == [
        ("fix-eslint", "pnpm exec eslint --fix --quiet src ; test $? -le 1"),
        ("fix-prettier", "pnpm exec prettier --write --log-level warn src"),
    ]


def test_eslint_named_by_no_script_or_no_lockfile_is_not_run(tmp_path: Path) -> None:
    write(tmp_path, {"package.json": '{"scripts": {"lint": "eslint ."}}'})
    assert fixes.autofix(tmp_path) == []  # no lockfile
    write(tmp_path, {"pnpm-lock.yaml": "", "package.json": '{"devDependencies": {"eslint": "1"}}'})
    assert fixes.autofix(tmp_path) == []  # no script runs it
    write(tmp_path, {"package.json": '{"scripts": {"lint": "tsc && pnpm exec eslint --max-warnings 0 web"}}'})
    assert fixes.autofix(tmp_path) == [
        ("fix-eslint", "pnpm exec eslint --fix --quiet --max-warnings 0 web ; test $? -le 1")
    ]
    for bad in ("[]", "{", '{"scripts": []}', '{"scripts": {"lint": 3, "x": "prettier"}}'):
        write(tmp_path, {"package.json": bad})
        assert fixes.autofix(tmp_path) == []
