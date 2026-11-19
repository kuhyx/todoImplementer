"""T2134: a hyphen in an ask id no longer drops the whole block; a dropped block says why."""

import pytest
from todoimpl.asks.parse import diagnose, parse_asks

# The reply of card 1d2e8ace-0 (personal-website logo pick): `logo-pick` was rejected, so kuhy saw only
# "Pick one candidate above" with nothing above it.
LOGO = (
    "I can't finish the last step until you pick a logo.\n\n```ask\n"
    "choice logo-pick: Logo for favicon, header mark and og:image | A grid-kuhy | *B k-solo | C wordmark"
    " | D ky-ligature | E glyph | F kr-initials | risk=reversible\n```\n\n"
    "A: Pick one candidate above."
)


def block(*lines: str) -> str:
    return "text\n```ask\n" + "\n".join(lines) + "\n```\nmore"


def test_t2134_a_hyphenated_ask_id_keeps_its_block() -> None:
    (ask,) = parse_asks(LOGO)
    assert ask.id == "logo_pick"
    assert ask.type == "choice"
    assert len(ask.options) == 6
    assert ask.recommended == "B k-solo"


def test_t2134_a_hyphen_and_an_underscore_id_are_the_same_id() -> None:
    assert parse_asks(block("choice a-b: x | *y | z", "choice a_b: x | *y | z")) == []


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("nonsense", "starts with choice, command or screenshot"),
        ("command K: x", "starts with choice, command or screenshot"),
        ("choice c1: only one | *a", "2 to 8 options"),
        ("choice c1: no star | a | b", "exactly one * option"),
        ("choice c1: two stars | *a | *b", "exactly one * option"),
        ("choice c1: bad risk | *a | b | risk=maybe", "risk= is reversible or risky"),
        ("screenshot s1: x | ../evil.png", "shots/<name>.png"),
        ("choice c1: dup | *a | b", "id c1 is used twice"),
        ("choice c2: risk=reversible", "it has no title"),
    ],
)
def test_diagnose_names_the_bad_line_and_why(line: str, reason: str) -> None:
    found = diagnose(block("choice c1: ok | *a | b", line))
    assert found is not None
    assert reason in found
    assert line[:20] in found


def test_diagnose_is_none_for_a_good_block_and_for_no_block() -> None:
    assert diagnose(block("choice c1: ok | *a | b")) is None
    assert diagnose("no block here") is None
    assert diagnose("") is None
