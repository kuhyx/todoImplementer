"""The ask block parser and the fixed risk rule (C1, C12, C13)."""
# ruff: noqa: PT018

import pytest
from todoimpl.asks.parse import parse_asks
from todoimpl.asks.risk import effective_risk


def block(*lines: str) -> str:
    return "text\n```ask\n" + "\n".join(lines) + "\n```\nmore"


def test_choice_command_screenshot_parse() -> None:
    asks = parse_asks(
        block(
            "choice c1: Pick one | a | *b | c | risk=reversible",
            "command k1: ls -la",
            "screenshot s1: Does it look right? | shots/home.png",
            "",
        )
    )
    assert [a.type for a in asks] == ["choice", "command", "screenshot"]
    assert asks[0].options == ("a", "b", "c") and asks[0].recommended == "b" and asks[0].risk == "reversible"
    assert asks[1].command == "ls -la" and asks[1].risk == "risky"
    assert asks[2].shot == "shots/home.png"


def test_screenshot_without_file_is_ok() -> None:
    assert parse_asks(block("screenshot s1: Look at it"))[0].shot is None


@pytest.mark.parametrize(
    "line",
    [
        "choice c1: only one | *a",
        "choice c1: no star | a | b",
        "choice c1: two stars | *a | *b",
        "choice c1: empty option | *a | ",
        "choice c1: bad risk | *a | b | risk=maybe",
        "choice c1: " + " | ".join(["x"] + ["*o"] + [f"o{i}" for i in range(9)]),
        "screenshot s1: x | ../evil.png",
        "screenshot s1: x | a.png | b.png",
        "nonsense",
        "command K: x",
    ],
)
def test_malformed_block_falls_back_to_nothing(line: str) -> None:
    assert parse_asks(block("command k1: ls", line)) == []


def test_duplicate_id_and_no_fence_give_nothing() -> None:
    assert parse_asks(block("command k1: a", "command k1: b")) == []
    assert parse_asks("no fence here") == []
    assert parse_asks("") == []


def test_last_fence_wins() -> None:
    text = block("command k1: old") + "\n" + block("command k2: new")
    assert [a.id for a in parse_asks(text)] == ["k2"]


@pytest.mark.parametrize(
    "word", ["encrypt it", "migrate db", "delete x", "push it", "root", "credentials", "rm -rf"]
)
def test_t_reversible_tag_is_overridden_by_a_risky_word(word: str) -> None:
    assert effective_risk("reversible", "Pick", word) == "risky"


def test_untagged_is_risky_and_clean_reversible_stays() -> None:
    assert effective_risk(None, "Pick a colour") == "risky"
    assert effective_risk("reversible", "Pick a colour", "red") == "reversible"
