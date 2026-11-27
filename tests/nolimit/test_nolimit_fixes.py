"""Setup and autofix steps come from the repo's own lockfiles and config."""

from __future__ import annotations

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


def test_a_pnpm_repo_with_eslint_and_prettier(tmp_path: Path) -> None:
    write(
        tmp_path,
        {"pnpm-lock.yaml": "", "package.json": '{"devDependencies": {"eslint": "1", "prettier": "1"}}'},
    )
    assert fixes.setup(tmp_path) == [("setup-pnpm", fixes.PNPM_SETUP)]
    assert [name for name, _ in fixes.autofix(tmp_path)] == ["fix-eslint", "fix-prettier"]


def test_eslint_without_a_lockfile_is_not_run(tmp_path: Path) -> None:
    write(tmp_path, {"package.json": '{"devDependencies": {"eslint": "1"}}'})
    assert fixes.autofix(tmp_path) == []
