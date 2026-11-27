"""Units of the free route (T2531): visibility cache, gateway probe cache, argv, feed line, the mark."""

import json
import threading
from pathlib import Path

import pytest
from todoimpl.board.state import RunState
from todoimpl.runner import chain, freegate, freeok, freeroute, freeverify, freeworker, srcwall


def _cache(text: str) -> None:
    path = Path.home() / freeok.VISIBILITY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    ("text", "repo", "want"),
    [
        ('{"a/b": {"visibility": "PUBLIC"}}', "a/b", True),
        ('{"a/b": {"visibility": "PRIVATE"}}', "a/b", False),
        ('{"a/b": "PUBLIC"}', "a/b", False),
        ("[1]", "a/b", False),
        ("not json", "a/b", False),
        ('{"a/b": {"visibility": "PUBLIC"}}', None, False),
    ],
)
def test_public_reads_the_check_dir_cache(text: str, repo: str | None, *, want: bool) -> None:
    _cache(text)
    assert freeok.public(repo) is want


def test_public_is_false_without_a_cache() -> None:
    (Path.home() / freeok.VISIBILITY).unlink(missing_ok=True)
    assert freeok.public("a/b") is False


def test_gateway_up_probes_off_the_caller_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    probed = threading.Event()

    def fake() -> bool:
        probed.set()
        return True

    monkeypatch.setattr(freegate, "check_gateway", fake)
    monkeypatch.setitem(freeok._gate, "at", float("-inf"))
    monkeypatch.setitem(freeok._gate, "up", value=False)
    assert freeok.gateway_up() is False  # the first answer is the stale one
    assert probed.wait(5)
    for _ in range(100):
        if freeok.gateway_up():
            break
        threading.Event().wait(0.02)
    assert freeok.gateway_up() is True


def test_check_gateway_needs_a_key_and_an_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Path.home() / ".config" / "omniroute" / "api_key"
    key.unlink(missing_ok=True)
    assert freegate.check_gateway() is False  # no key file
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text("k\n", encoding="utf-8")
    monkeypatch.setattr(freegate, "_gateway_error", lambda _k: None)
    assert freegate.check_gateway() is True


def test_eligible_needs_a_run() -> None:
    assert freeroute.eligible(None) is False


def test_free_bin_falls_back_to_local_bin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TODOIMPL_FREE_CLAUDE", raising=False)
    monkeypatch.setenv("PATH", "/nonexistent")
    assert freeroute.free_bin() == str(Path.home() / ".local" / "bin" / "claude-free")


@pytest.mark.parametrize("deny", [None, []])
def test_build_runs_claude_free_behind_the_wall_with_one_deny_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deny: list[str] | None
) -> None:
    from todoimpl.runner import policy  # noqa: PLC0415

    monkeypatch.setenv("TODOIMPL_FREE_CLAUDE", "/x/claude-free")
    monkeypatch.setattr(srcwall, "wrap", lambda _w, _s: (["bwrap", "--"], "no bwrap"))
    if deny is not None:
        real = policy.load
        monkeypatch.setattr(policy, "load", lambda: real().__class__(**{**vars(real()), "deny": ()}))
    inv = freeroute.build("plan", "do it", tmp_path)
    assert inv.argv[:3] == ("bwrap", "--", "/x/claude-free")
    assert inv.argv[inv.argv.index("--model") + 1] == "free-best"
    assert inv.argv.count("--disallowedTools") == 1
    assert "Bash(git push:*)" in inv.argv
    assert inv.route == "free"
    assert any("src wall" in note for note in inv.notes)
    assert freeworker.PREAMBLE in inv.argv[inv.argv.index("-p") + 1]


@pytest.mark.parametrize(
    ("route", "wanted", "ran", "start"),
    [
        ("free", "opus", "free-best", "turn on free models"),
        ("plan", "opus", "opus", "turn on the plan"),
        ("credits", "opus", "sonnet", "turn on free API credits: the plan role"),
        ("credits", "opus", "opus", "turn on free API credits (Agent SDK)"),
    ],
)
def test_banner_names_the_route(route: str, wanted: str, ran: str, start: str) -> None:
    assert freeroute.banner(route, "plan", wanted, ran).startswith(start)


def test_after_turn_marks_clears_and_moves_stray_reports(tmp_path: Path) -> None:
    run_dir, wt = tmp_path / "run", tmp_path / "run" / "wt"
    wt.mkdir(parents=True)
    (wt / "plan.md").write_text("plan", encoding="utf-8")
    (wt / "live_check.md").write_text("new", encoding="utf-8")
    (run_dir / "live_check.md").write_text("kept", encoding="utf-8")
    dirs = (run_dir, wt)
    st = RunState(task_id="a-0", stage="implement")
    freeroute.after_turn(st, "free", "plan", ok=True, dirs=dirs)
    assert st.extra["free_unverified"] is True
    assert (run_dir / "plan.md").read_text(encoding="utf-8") == "plan"
    assert not (wt / "plan.md").exists()
    assert (run_dir / "live_check.md").read_text(encoding="utf-8") == "kept"  # never overwrites
    freeroute.after_turn(st, "plan", "implement", ok=True, dirs=dirs)  # only a live check clears it
    freeroute.after_turn(st, "plan", "live_check", ok=False, dirs=dirs)
    assert st.extra["free_unverified"] is True
    freeroute.after_turn(st, "credits", "live_check", ok=True, dirs=dirs)
    assert "free_unverified" not in st.extra


def test_chain_admits_reads_the_run(tmp_path: Path) -> None:
    assert chain.admits(tmp_path, 0.0, "nope-0") is True  # no limit: the plan takes any card


def test_verify_gate_has_nothing_to_do_without_the_mark() -> None:
    st = RunState(task_id="a-0", stage="checks")
    driver = type("D", (), {"state": st, "ctx": type("C", (), {"now": staticmethod(lambda: 0.0)})()})()
    assert freeverify.gate(driver) is None


def test_visibility_cache_path_matches_free_llm_check_dir() -> None:
    assert json.dumps(str(freeok.VISIBILITY)).endswith('omniroute_offload/visibility.json"')


def test_start_stays_enabled_under_the_limit_for_a_card_that_may_go_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from todoimpl.board import actions as board_actions  # noqa: PLC0415
    from todoimpl.board.types import Credits, Limit  # noqa: PLC0415

    limit = Limit(active=True, until=10.0, credits=Credits())
    monkeypatch.setattr(board_actions, "may_go_free", lambda _repo, _body: True)
    assert board_actions.launch_block(limit, 0.0, free=True) is None
    assert board_actions.launch_block(limit, 0.0) is not None
