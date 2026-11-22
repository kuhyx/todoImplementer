"""A task's title is its first line of real text: an `[Image #N]` placeholder never names it (T2481)."""

import pytest
from todoimpl.newtask.titles import retitle, split

FIX = "fix the new task from repo resurrects old tasks"


@pytest.mark.parametrize(
    ("text", "title", "body"),
    [
        ("  Fix it \nmore\n\nlines ", "Fix it", "more\n\nlines"),  # plain text splits as before
        (
            f"[Image #1]\n{FIX}\n1. details",
            FIX,
            f"[Image #1]\n{FIX}\n1. details",
        ),  # the ref stays in the body
        (f"[Image #1] \n\n[Image #2]\n{FIX}", FIX, f"[Image #1] \n\n[Image #2]\n{FIX}"),
        ("see [Image #1]  crash\nmore", "see crash", "see [Image #1]  crash\nmore"),
        ("[Image #1]", "[Image #1]", ""),  # no text at all: the placeholder stays the title
        ("[Image #1]\n[Image #2]", "[Image #1]", "[Image #2]"),
        ("", "", ""),
    ],
)
def test_t2481_the_title_is_the_first_line_of_real_text(text: str, title: str, body: str) -> None:
    assert split(text, 200) == (title, body)


def test_t2481_a_long_line_is_cut_and_the_body_keeps_everything() -> None:
    text = f"[Image #1]\n{'x' * 300}\nmore"
    assert split(text, 200) == ("x" * 200, text)


def test_t2481_the_server_retitles_what_a_client_split_the_old_way() -> None:
    assert retitle("[Image #1]", f"{FIX}\n1. details", 200) == (FIX, f"[Image #1]\n{FIX}\n1. details")
    assert retitle("[Image #1]", "", 200) == ("[Image #1]", "")
    assert retitle(FIX, f"[Image #1]\n{FIX}", 200) == (
        FIX,
        f"[Image #1]\n{FIX}",
    )  # a new client's split stays
    assert retitle("Fix it", "more", 200) == ("Fix it", "more")
