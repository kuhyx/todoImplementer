"""The merged note texts: combined same-repo body, the exact umbrella format, tier and done_check handling."""

from todoimpl.merge import text
from todoimpl.service.cards import CardTask
from todoimpl.todo_mcp.items import Item


def card(
    note: str, index: int, title: str, body: str = "", *, repo: str = "kuhyx/a", check: str | None = None
) -> CardTask:
    item = Item(note, index, title, body, repo, "todo", check)
    return CardTask(f"{note}-{index}", title, body, repo, "todo", "medium", check, item)


def test_fingerprint_ignores_order_and_is_twelve_hex() -> None:
    assert text.fingerprint(["b-0", "a-0"]) == text.fingerprint(["a-0", "b-0"])
    assert len(text.fingerprint(["a-0"])) == 12
    assert text.fingerprint(["a-0"]) != text.fingerprint(["a-1"])


def test_tier_line_is_found_case_insensitively_on_its_own_line() -> None:
    assert text.has_tier(card("11111111", 0, "t", "x\nTier: cheap\ny"))
    assert text.has_tier(card("11111111", 0, "t", "tier:  CHEAP  "))
    assert not text.has_tier(card("11111111", 0, "t", "Tier: expensive"))
    assert not text.has_tier(card("11111111", 0, "t", "not a Tier: cheap line"))


def test_member_text_is_title_then_body_and_done_check_stops_being_one() -> None:
    plain = card("11111111", 0, "Title")
    assert text.member_text(plain) == "Title"
    c = card("11111111", 0, "Title", "line\ndone_check: `make x`\nend", check="make x")
    out = text.member_text(c)
    assert out == "Title\n\nline\nmember done_check: `make x`\nend"
    assert not any(x.strip().startswith("done_check:") for x in out.splitlines())


def test_note_level_done_check_is_kept_as_a_member_line() -> None:
    c = card("11111111", 0, "Title", "body", check="make y")
    assert text.member_text(c).endswith("body\nmember done_check: make y")


def test_labels_use_the_note_id_unless_two_members_share_a_note() -> None:
    a, b, c = card("11111111", 0, "a"), card("22222222", 0, "b"), card("22222222", 1, "c")
    assert text.labels([a, b, c]) == {
        "11111111-0": "11111111",
        "22222222-0": "22222222-0",
        "22222222-1": "22222222-1",
    }


def test_combined_body_keeps_tier_first_and_sub_headings_do_not_split_the_card() -> None:
    a = card("11111111", 0, "A", "Tier: cheap\nbody a")
    b = card("22222222", 0, "B", "body b")
    body = text.combined_body([a, b])
    assert body.splitlines()[0] == "Tier: cheap"
    assert "### 11111111\nA\n\nTier: cheap\nbody a" in body
    assert "### 22222222\nB\n\nbody b" in body
    assert not any(line.startswith("## ") for line in body.splitlines())
    assert not text.combined_body([b]).startswith("Tier:")


def test_umbrella_text_has_the_exact_shape() -> None:
    a = card("11111111", 0, "A", "body a", repo="kuhyx/one")
    b = card("22222222", 0, "B", "Tier: cheap", repo="kuhyx/two")
    assert text.umbrella_text("Both", [a, b]) == (
        "# Both\nUmbrella: per-repo\nTier: cheap\n"
        "- [ ] kuhyx/one (11111111)\n- [ ] kuhyx/two (22222222)\n"
        "## kuhyx/one (11111111)\nA\n\nbody a\n"
        "## kuhyx/two (22222222)\nB\n\nTier: cheap"
    )


def test_umbrella_without_tier_has_no_tier_line_and_the_text_free_title_forces_it() -> None:
    a = card("11111111", 0, "Make x text-free (textgate-rework)", repo="kuhyx/one")
    b = card("22222222", 0, "B", repo="kuhyx/two")
    assert "Tier: cheap" in text.umbrella_text("T", [a, b])
    plain = card("11111111", 0, "A", repo="kuhyx/one")
    assert "Tier:" not in text.umbrella_text("T", [plain, b])


def test_a_text_free_title_makes_the_combined_note_cheap_too() -> None:
    a = card("11111111", 0, "Make a Text-Free (textgate-rework)")
    assert text.combined_body([a, card("22222222", 0, "B")]).startswith("Tier: cheap\n\n###")
