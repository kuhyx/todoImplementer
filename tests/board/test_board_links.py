"""T2135: a Needs-you ask that names a page carries an absolute link, or is flagged as not concrete."""

import pytest
from board_helpers import run
from contract_lib import validate
from todoimpl.board.links import scan
from todoimpl.board.needs import needs
from todoimpl.prompts.standing import GRANT

LIVE = "Deployed and live at https://kuhy.duckdns.org, build 50beea1."
LOCAL = "http://127.0.0.1:4321"


def test_t2135_an_absolute_url_in_the_ask_is_a_link() -> None:
    found = scan(f"Open {LOCAL}/logo-lab and pick one.")
    assert found.urls == (f"{LOCAL}/logo-lab",)
    assert found.bare == ()


def test_t2135_trailing_punctuation_is_not_part_of_the_link() -> None:
    found = scan("Pick one (see https://kuhy.duckdns.org/logo-lab), then say which.")
    assert found.urls == ("https://kuhy.duckdns.org/logo-lab",)
    assert scan("Look at `http://localhost:8786/x`.").urls == ("http://localhost:8786/x",)


def test_t2135_a_bare_route_resolves_against_the_own_origin_in_the_reply() -> None:
    found = scan("Open /logo-lab and pick one.", LIVE)
    assert found.urls == ("https://kuhy.duckdns.org/logo-lab",)
    assert found.bare == ()


def test_t2135_a_bare_route_with_no_known_origin_is_not_concrete() -> None:
    found = scan(
        "Open `/logo-lab` and pick one.", "Built it, nothing deployed anywhere. See https://github.com/a/b"
    )
    assert found.urls == ()
    assert found.bare == ("/logo-lab",)


def test_t2135_a_route_only_in_the_reply_counts_too() -> None:
    assert scan("Pick one above.", "Preview them on /logo-lab first.").bare == ("/logo-lab",)
    assert scan("Pick one above.", f"Preview them on /logo-lab. {LIVE}").urls == (
        "https://kuhy.duckdns.org/logo-lab",
    )


def test_t2135_a_route_already_given_as_a_full_url_is_listed_once() -> None:
    found = scan("Open https://kuhy.duckdns.org/logo-lab, or open /logo-lab on that site.")
    assert found.urls == ("https://kuhy.duckdns.org/logo-lab",)


def test_t2135_links_are_unique_and_capped() -> None:
    twice = scan(f"Open {LOCAL}/a, then {LOCAL}/a again.")
    assert twice.urls == (f"{LOCAL}/a",)
    many = " ".join(f"{LOCAL}/p{i}" for i in range(9))
    assert len(scan(many).urls) == 5


@pytest.mark.parametrize(
    "ask",
    [
        "Open /home/kuhy/.cache/todoImplementer/1d2e8ace-0/shots/lab.png and check it.",
        "See /run/ab12cd34/shots/ for the pictures.",
        "Check `/etc/hosts` for the entry.",
        "Open /tmp/probe.png.",
        "Look at /usr/bin/env",
        "Check /api/task/1d2e8ace-0 for the state.",
        "Open ~/src/personal-website and run it.",
        "Open scripts/e2e_focus.py and read it.",
        "See step 1/2 of the part and the tag v1.0/final.",
        "Open /srv/site/index.html",
        "Check /opt/app/run.sh",
        "Approve or reject, and/or send a note.",
    ],
)
def test_t2135_file_paths_and_plain_prose_are_not_routes(ask: str) -> None:
    found = scan(ask)
    assert found.urls == ()
    assert found.bare == ()


def test_t2135_the_standing_prompt_names_no_route() -> None:
    found = scan(GRANT.format(base="main", run_dir="/run/ab12cd34"))
    assert found.bare == ()
    assert found.urls == ()


def test_t2135_needs_carries_the_links_of_its_ask() -> None:
    state = run(last_tag="A", extra={"last_reply": f"Built.\n\nA: Open {LOCAL}/logo-lab and pick one."})
    got = needs(state)
    assert got.links == (f"{LOCAL}/logo-lab",)
    assert got.to_dict()["links"] == [f"{LOCAL}/logo-lab"]


def test_t2135_needs_resolves_a_route_of_the_ask_against_the_reply() -> None:
    state = run(last_tag="A", extra={"last_reply": f"{LIVE}\n\nA: Open /logo-lab and pick one."})
    assert needs(state).links == ("https://kuhy.duckdns.org/logo-lab",)


def test_t2135_needs_without_a_page_has_no_links_key() -> None:
    state = run(last_tag="A", extra={"last_reply": "A: Decide whether to bump the pin."})
    got = needs(state)
    assert got.links == ()
    assert "links" not in got.to_dict()


def test_t2135_the_links_follow_the_common_contract() -> None:
    state = run(last_tag="A", extra={"last_reply": f"Built.\n\nA: Open {LOCAL}/logo-lab and pick one."})
    validate("common", needs(state).to_dict(), "needs")
