from typing import Any

import pytest
from runnerfakes import Env, task
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, wait_stage
from todoimpl.board.actions import actions
from todoimpl.board.status import Status, needs
from todoimpl.board.types import Limit
from todoimpl.http.backend import BackendError
from todoimpl.service import permission


def blocked(
    tool: str, tool_input: dict[str, Any], *, hook: bool = False, reason: str = "rule", tag: str = "A"
) -> Any:
    """Build a turn that ends on a refused tool call."""
    uid = "toolu_p1"
    text = f"PreToolUse:{tool} hook error: nope" if hook else "Claude requested permissions to use it"
    return (
        {"_fake": "tool", "name": tool, "id": uid, "input": tool_input},
        {"_fake": "denied", "tool": tool, "id": uid, "reason": reason},
        {"_fake": "tool_result", "id": uid, "error": True, "text": text},
        {
            "_fake": "result",
            "text": f"stuck\n\n{tag}: blocked",
            "denials": [{"tool_name": tool, "tool_use_id": uid, "tool_input": tool_input}],
        },
    )


MCP_ADD = blocked("Bash", {"command": "claude mcp add foo"})
SUDO = blocked("Bash", {"command": "sudo pacman -S foo"})


def argv_of(world: Env, n: int) -> list[str]:
    return list(world.calls()[n]["argv"])


def test_t1620_denied_bash_is_learned_and_the_stage_reruns_by_itself(world: Env) -> None:
    sched, _ = boot(world, PLAN, MCP_ADD, IMPL, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        calls = world.calls()
        assert "--allowedTools" not in calls[1]["argv"]
        assert argv_of(world, 2)[argv_of(world, 2).index("--allowedTools") + 1] == "Bash(claude mcp add:*)"
        assert "Permission is granted now for: Bash(claude mcp add:*)" in calls[2]["prompt"]
        assert calls[2]["resume"] == st.sessions["implement"]["session_id"]
        assert "Bash(claude mcp add:*)" in (world.root / "allow.json").read_text(encoding="utf-8")
        texts = [e["text"] for e in sched.bus.history(CARD, 0)]
        assert any("permission auto-allowed (repo): Bash(claude mcp add:*)" in t for t in texts)
        assert "perm_reruns" not in st.extra
        assert "Permission is granted" not in calls[3]["prompt"]
    finally:
        sched.close()


def test_t1621_two_reruns_then_kuhy_gets_a_settings_command(world: Env) -> None:
    sched, _ = boot(world, PLAN, MCP_ADD, MCP_ADD, MCP_ADD, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        assert len(world.calls()) == 4
        assert st.error is not None
        assert st.error.startswith("Still denied after 2 reruns: Bash(claude mcp add:*)")
        got = needs(st)
        assert got.kind == "permission"
        assert got.command is not None
        assert got.command.startswith("jq ")
        assert '"Bash(claude mcp add:*)"' in got.command
    finally:
        sched.close()


def test_t1622_sudo_is_never_auto_allowed_and_offers_a_terminal_command(world: Env) -> None:
    sched, _ = boot(world, PLAN, SUDO, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        assert len(world.calls()) == 2
        assert not (world.root / "allow.json").exists()
        got = needs(st)
        assert (got.kind, got.command) == ("permission", f"cd {st.worktree} && sudo pacman -S foo")
        assert got.to_dict()["command"] == got.command
        assert "uses sudo/chattr" in got.text
        shown = {a.id: a for a in actions(_task(), st, Status.NEEDS_YOU, Limit())}
        assert list(shown)[:4] == ["go", "copy-fix", "rerun", "cancel"]
        assert shown["go"].reason == "needs a terminal: copy it"
        assert shown["copy-fix"].value == got.command
    finally:
        sched.close()


def test_t1623_done_rerun_continues_the_failed_stage(world: Env) -> None:
    sched, _ = boot(world, PLAN, SUDO, IMPL, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "failed")
        permission.rerun(world.root, sched, CARD)
        st = wait_stage(world, sched, "gate")
        assert "kuhy ran `cd " in world.calls()[2]["prompt"]
        assert "permission" not in st.extra
    finally:
        sched.close()


def test_t1624_go_runs_the_command_and_reruns_on_success_only(world: Env) -> None:
    sched, _ = boot(world, PLAN, SUDO, IMPL, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "failed")
        ran: list[str] = []

        def record(command: str) -> tuple[int, str]:
            ran.append(command)
            return 0, "done"

        with pytest.raises(BackendError, match="exited 3: boom"):
            permission.go(world.root, sched, CARD, lambda _c: (3, "boom"), 1.0)
        assert wait_stage(world, sched, "failed").error is not None
        permission.go(world.root, sched, CARD, record, 2.0)
        wait_stage(world, sched, "gate")
        assert ran[0].endswith("sudo pacman -S foo")
        assert "kuhy clicked Go: ran" in world.calls()[2]["prompt"]
        with pytest.raises(BackendError, match="no command"):
            permission.go(world.root, sched, CARD, lambda _c: (0, ""), 3.0)
    finally:
        sched.close()


def test_t1625_a_hook_block_has_no_command_and_offers_retry(world: Env) -> None:
    hook = blocked("Write", {"file_path": "x.md", "content": "c"}, hook=True)
    sched, _ = boot(world, PLAN, hook, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        got = needs(st)
        assert (got.kind, got.command) == ("permission", None)
        assert "a hook blocked it" in got.text
        assert [a.id for a in actions(_task(), st, Status.NEEDS_YOU, Limit())][:2] == ["start", "cancel"]
    finally:
        sched.close()


def test_t1626_a_sensitive_file_in_the_worktree_reruns_with_the_bash_advice(world: Env) -> None:
    edit = blocked("Edit", {"file_path": ".pre-commit-config.yaml"}, reason="safetyCheck")
    sched, _ = boot(world, PLAN, edit, IMPL, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        prompt = world.calls()[2]["prompt"]
        assert "refused as a sensitive file, write it with a Bash command" in prompt
        assert "--allowedTools" not in argv_of(world, 2)
    finally:
        sched.close()


def test_t1627_a_question_stop_is_not_a_permission_stop(world: Env) -> None:
    asked = blocked("Bash", {"command": "claude mcp add foo"}, tag="Q")
    sched, _ = boot(world, PLAN, asked, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "implement", tag="Q")
        assert needs(st).kind == "claude_question"
        assert len(world.calls()) == 2
    finally:
        sched.close()


def test_t1628_a_refused_push_is_not_a_permission_gap(world: Env) -> None:
    refused = blocked("Bash", {"command": "git " + "push origin x"})
    sched, _ = boot(world, PLAN, refused, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "implement", tag="A")
        assert needs(st).kind == "claude_action"
        assert "permission" not in st.extra
    finally:
        sched.close()


def _task() -> Any:
    return task()
