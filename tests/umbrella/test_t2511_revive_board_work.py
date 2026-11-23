"""T2510-T2511: failed children whose failure the board retries itself go back to work, not to kuhy."""

from __future__ import annotations

from pathlib import Path

import pytest
from runnerfakes import Env, make_repo
from todoimpl.board import state as store
from todoimpl.runner import deployheal
from todoimpl.runner.deployheal import DirtyCheckoutError
from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.restart import INTERRUPTED
from todoimpl.umbrella import revive

LOCK_LINE = "waiting for build lock held by ? (java -jar emulator.jar) since 2026-11-22 18:14:08; 5 ahead"


def _failed(error: str, repo: str = "kuhyx/demo") -> store.RunState:
    extra = {"failed_stage": "shipping", "ship_resumes": 2, "retries": 12, "deploy_fixes": 2}
    return store.RunState(task_id="abcd1234-1", stage="failed", error=error, repo=repo, extra=extra)


def test_t2510_a_child_a_restart_cut_three_times_ships_again(tmp_path: Path) -> None:
    st = _failed(f"{INTERRUPTED} 3 times in a row: check origin and the note, then Retry")
    assert revive.revive(st, tmp_path, 0.0)
    assert (st.stage, st.error) == ("shipping", None)
    assert "ship_resumes" not in st.extra


def test_t2511_a_child_whose_deploy_refused_kuhys_edits_redeploys_once_the_checkout_is_clean(
    world: Env, tmp_path: Path
) -> None:
    checkout = make_repo(world, files={"lib.txt": "old\n"})
    st = _failed(DirtyCheckoutError("pushed, not deployed", checkout, ["lib.txt"]).text)
    (checkout / "lib.txt").write_text("his\n", encoding="utf-8")
    assert not revive.revive(st, tmp_path, 0.0)  # still dirty: his step is still the one
    assert st.stage == "failed"
    (checkout / "lib.txt").write_text("old\n", encoding="utf-8")
    assert revive.revive(st, tmp_path, 0.0)
    assert (st.stage, st.error) == ("shipping", None)
    assert "retries" not in st.extra  # the ladder starts afresh


def test_t2511_a_red_deploy_that_only_refused_a_dirty_checkout_goes_back_to_ship(
    world: Env, tmp_path: Path
) -> None:
    make_repo(world, files={"lib.txt": "old\n"})
    tail = f"{LOCK_LINE}\ndeploy: ~/src/demo is dirty (before the pull); commit or revert there first"
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "exit.json").write_text(
        f'{{"tail": {tail!r}}}'.replace("'", '"'), encoding="utf-8"
    )
    st = _failed(f"pushed, not deployed: deploy failed (exit 1): {tail}")
    assert revive.revive(st, tmp_path, 0.0)  # its own Ship now waits for the edits, no fix turn
    assert st.stage == "shipping"


def test_t2511_a_child_parked_on_the_old_dirty_text_ships_again_once(tmp_path: Path) -> None:
    st = _failed("pushed, not deployed: the deploy's pull into ~/src/demo stops on uncommitted edits to a")
    assert revive.revive(st, tmp_path, 0.0)  # its Ship now sets the strays aside itself (T2512)
    assert st.stage == "shipping"


def test_t2511_a_dirty_child_with_no_checkout_stays(tmp_path: Path) -> None:
    st = _failed(DirtyCheckoutError("pushed, not deployed", tmp_path / "gone", ["a"]).text, repo="kuhyx/gone")
    assert not revive.revive(st, tmp_path, 0.0)


def test_t2511_a_git_failure_in_kuhys_checkout_leaves_the_child_for_next_time(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = make_repo(world, files={"lib.txt": "old\n"})
    st = _failed(DirtyCheckoutError("pushed, not deployed", checkout, []).text)

    def locked(_checkout: Path, _files: list[str]) -> bool:
        raise NeedsYouError("fatal: Unable to create '.git/index.lock': File exists.")

    monkeypatch.setattr(deployheal, "still_dirty", locked)
    assert not revive.revive(st, tmp_path, 0.0)
    assert st.stage == "failed"


def test_t2511_a_red_deploy_that_refused_a_dirty_checkout_ships_again_only_once(
    world: Env, tmp_path: Path
) -> None:
    make_repo(world, files={"lib.txt": "old\n"})
    tail = "deploy: ~/src/demo is dirty (before the pull)"
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "exit.json").write_text(f'{{"tail": "{tail}"}}', encoding="utf-8")
    st = _failed(f"pushed, not deployed: deploy failed (exit 1): {tail}")
    st.extra[revive.REFUSALS] = 1
    assert not revive.revive(st, tmp_path, 0.0)
