import json
from typing import Any

from todoimpl.runner.stream import Activity, StreamParser, parse_tag, short_input, state_tag


def _line(obj: dict[str, Any]) -> str:
    return json.dumps(obj) + "\n"


def _assistant(*blocks: dict[str, Any]) -> str:
    return _line({"type": "assistant", "message": {"content": list(blocks)}, "session_id": "s1"})


def test_parse_tag_takes_last_tag_line_and_long_forms() -> None:
    assert parse_tag("work\n\nD: done") == "D"
    assert parse_tag("Q: which?\nmore\nA: run `x`") == "A"
    assert parse_tag("**QUESTION**: pick one") == "Q"
    assert parse_tag("NEEDS ACTION: click") == "A"
    assert parse_tag("CONTINUING in new session: /tmp/h.md") == "C"
    assert parse_tag("- **R**: still building") == "R"
    assert parse_tag("N: a note only") is None
    assert parse_tag("A : not a tag\nno tag here") is None


def test_state_tag_maps_continuing_to_running() -> None:
    assert state_tag("C") == "R"
    assert state_tag("D") == "D"
    assert state_tag(None) is None


def test_short_input_picks_the_telling_field_and_clips() -> None:
    assert short_input({"command": "ls   -la\n/tmp", "description": "list"}) == "ls -la /tmp"
    assert short_input({"skill": "build-game"}) == "build-game"
    assert short_input({"other": 1}) == '{"other": 1}'
    assert short_input("x" * 500).endswith("…")
    assert len(short_input("x" * 500)) == 160


def test_parser_reads_a_real_shaped_stream() -> None:
    parser = StreamParser()
    out: list[Activity] = []
    lines = [
        _line({"type": "system", "subtype": "hook_started", "session_id": "s1"}),
        _line({"type": "system", "subtype": "init", "session_id": "s1", "model": "claude-haiku-5-5"}),
        _line({"type": "system", "subtype": "thinking_tokens", "session_id": "s1"}),
        _assistant({"type": "thinking", "thinking": ""}, {"type": "text", "text": "  "}),
        _assistant({"type": "tool_use", "name": "Bash", "input": {"command": "printf hi > hello.txt"}}),
        _line(
            {
                "type": "rate_limit_event",
                "rate_limit_info": {"status": "allowed_warning", "resetsAt": 5, "overageStatus": "rejected"},
            }
        ),
        _line({"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}}),
        _assistant({"type": "text", "text": "Created hello.txt"}),
        "not json\n",
        _line([1, 2]),  # type: ignore[arg-type]
        _line({"type": "assistant", "message": "odd"}),
        _line({"type": "assistant", "message": {"content": "odd"}}),
        _assistant("odd"),  # type: ignore[arg-type]
        _line(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "Created.\n\nD: done",
                "session_id": "s1",
                "total_cost_usd": 0.0087,
                "num_turns": 2,
            }
        ),
    ]
    for line in lines:
        out += parser.feed(line)
    assert [(a.kind, a.tool, a.text) for a in out] == [
        ("system", None, "session started (claude-haiku-5-5)"),
        ("tool", "Bash", "printf hi > hello.txt"),
        ("text", None, "Created hello.txt"),
        ("result", None, "Created.\n\nD: done"),
    ]
    res = parser.result
    assert (res.session_id, res.cost_usd, res.tag, res.num_turns, res.finished) == (
        "s1",
        0.0087,
        "D",
        2,
        True,
    )
    assert res.limit is not None
    assert res.limit.status == "allowed_warning"


def test_parser_flags_a_rejected_limit_and_an_error_result() -> None:
    parser = StreamParser()
    acts = parser.feed(
        _line({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 0}})
    )
    assert acts[0].kind == "error"
    assert "plan limit reached" in acts[0].text
    acts = parser.feed(
        _line(
            {
                "type": "result",
                "is_error": True,
                "result": "",
                "subtype": "error_during_execution",
                "total_cost_usd": "bad",
            }
        )
    )
    assert [(a.kind, a.text) for a in acts] == [("error", "turn ended (error_during_execution)")]
    assert parser.result.cost_usd == 0.0
    assert parser.result.is_error


def test_parser_ignores_odd_result_fields() -> None:
    parser = StreamParser()
    parser.feed(_line({"type": "result", "result": None, "num_turns": "x", "session_id": ""}))
    assert parser.result.text == ""
    assert parser.result.num_turns == 0
    assert parser.result.session_id is None
    assert parser.feed(_line({"type": "rate_limit_event"})) == []
