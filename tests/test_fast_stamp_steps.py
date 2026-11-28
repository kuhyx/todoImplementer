"""The sharded gate a board session runs counts as a green `make fast` for pre-commit (T2485).

A session runs the gate one step per call (`make lines ...`, `make types`, web steps, six test shards, then
`make test-cov`): none of them recorded the T2410 stamp, so `git commit` and the board's `pre-commit run
--all-files` ran the whole `make fast` again and held a build slot 92-96 s. Every step now marks the tree it
passed on; a tree with every step marked is fresh.
"""

from pathlib import Path

import fast_stamp
import pytest
from test_fast_stamp import make_repo

ROOT = Path(__file__).resolve().parents[1]
SHARDS = [f"shard{k}of6" for k in range(1, 7)]


def mark_all(repo: Path, tree: str, steps: list[str]) -> None:
    for step in steps:
        fast_stamp.mark(repo, step, tree)


def test_t2485_every_step_plus_every_shard_and_the_combined_coverage_is_fresh(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    tree = fast_stamp.key(repo)
    mark_all(repo, tree, [*fast_stamp.BASE, *SHARDS])
    assert not fast_stamp.fresh(repo)  # the shards alone do not prove the whole sharding passed
    fast_stamp.mark(repo, "cov-of-6", tree)
    assert fast_stamp.fresh(repo)
    (repo / "a.txt").write_text("edited after the gate\n")
    assert not fast_stamp.fresh(repo)


def test_t2485_one_shard_of_an_older_tree_is_not_fresh(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    old = fast_stamp.key(repo)
    fast_stamp.mark(repo, "shard3of6", old)
    (repo / "a.txt").write_text("edited between shards\n")
    tree = fast_stamp.key(repo)
    mark_all(repo, tree, [*fast_stamp.BASE, *[s for s in SHARDS if s != "shard3of6"], "cov-of-6"])
    assert not fast_stamp.fresh(repo)


def test_t2485_a_single_test_run_replaces_the_shards(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    tree = fast_stamp.key(repo)
    mark_all(repo, tree, list(fast_stamp.BASE))
    assert not fast_stamp.fresh(repo)
    fast_stamp.mark(repo, "test", tree)
    assert fast_stamp.fresh(repo)


def test_t2485_parallel_keys_use_their_own_scratch_index(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / ".git" / f"{fast_stamp.SCRATCH}.lock").write_text("")  # another step's key in flight
    assert fast_stamp.key(repo)


def test_t2485_mark_main(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    tree = fast_stamp.key(repo)
    for step in [*fast_stamp.BASE, "test"]:
        assert fast_stamp.main(["mark", str(repo), step, tree]) == 0
    assert fast_stamp.main(["check", str(repo)]) == 0


@pytest.mark.parametrize(
    "target", ["private", "md", "web-build", "web-test", "test", "test-shard", "test-cov"],
)  # fmt: skip
def test_t2485_every_gate_target_marks_its_step(target: str) -> None:
    recipe = (ROOT / "Makefile").read_text().split(f"\n{target}:\n", 1)[1].split("\n\n", 1)[0]
    assert "$(MARK)" in recipe or "$(STAMP_MARK)" in recipe


def test_t2485_the_base_steps_are_the_fast_steps() -> None:
    steps = (ROOT / "Makefile").read_text().split("\nfast-steps: ", 1)[1].split("\n", 1)[0].split()
    assert [s for s in steps if s != "web"] + ["web-build", "web-test"] == list(fast_stamp.BASE)


def test_t2485_tested_tells_whether_the_suite_passed_on_the_tree(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    tree = fast_stamp.key(repo)
    assert fast_stamp.main(["tested", str(repo), tree]) == 1
    mark_all(repo, tree, [*SHARDS, "cov-of-6"])
    assert fast_stamp.main(["tested", str(repo), tree]) == 0
    assert fast_stamp.main(["tested", str(repo), "0" * 40]) == 1


def test_t2485_make_fast_skips_a_suite_the_board_already_ran() -> None:
    # The board runs `make test`, then `pre-commit run --all-files` on the same tree: the hook's `make fast`
    # reruns only the cheap steps, not the whole suite a second time.
    recipe = (ROOT / "Makefile").read_text().split("\nfast:\n", 1)[1].split("\n\n", 1)[0]
    assert 'fast_stamp.py tested . "$$k" || $(MAKE)' in recipe
