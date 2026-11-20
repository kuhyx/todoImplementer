"""`make test` in shards: each is one call under 60 s; together they run every test file once (T2416)."""

import runpy
import sys
from pathlib import Path

import pytest
import test_shard


def _tree(tmp_path: Path) -> Path:
    sizes = {"tests/a/test_big.py": 900, "tests/test_mid.py": 500, "tests/b/test_s1.py": 100}
    sizes |= {"tests/b/test_s2.py": 90, "tests/b/helper.py": 5000, "tests/c/conftest.py": 10}
    for rel, size in sizes.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x" * size)
    return tmp_path


def test_t2416_the_shards_split_every_test_file_once_by_size(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    shards = [test_shard.files(root, k, 2) for k in (1, 2)]
    assert shards == [
        ["tests/a/test_big.py"],
        ["tests/b/test_s1.py", "tests/b/test_s2.py", "tests/test_mid.py"],
    ]


@pytest.mark.parametrize("argv", [["0", "2"], ["3", "2"], ["1"], ["x", "2"]])
def test_t2416_a_bad_shard_number_exits_2(argv: list[str]) -> None:
    assert test_shard.main(argv) == 2


def test_t2416_main_prints_the_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_tree(tmp_path))
    monkeypatch.setattr(sys, "argv", ["test_shard.py", "1", "2"])
    with pytest.raises(SystemExit) as done:
        runpy.run_path(test_shard.__file__, run_name="__main__")
    assert (done.value.code, capsys.readouterr().out) == (0, "tests/a/test_big.py\n")
