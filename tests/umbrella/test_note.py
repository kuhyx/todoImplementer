"""The umbrella note format: recognition, children, ease order, ticking."""

from __future__ import annotations

from todoimpl.umbrella import note
from umbrellafakes import HEADER, child_text, sample, umbrella_body


def test_marker_in_header_makes_an_umbrella() -> None:
    assert note.is_umbrella(sample())
    assert note.is_umbrella("# t\numbrella:  Per-Repo \n- [ ] kuhyx/a (aaaa1111)")


def test_marker_elsewhere_is_not_an_umbrella() -> None:
    assert not note.is_umbrella("# t\nplain note")
    assert not note.is_umbrella("# t\n## kuhyx/a (aaaa1111)\nUmbrella: per-repo")
    assert not note.is_umbrella("# t\n```\nUmbrella: per-repo\n```\n")
    assert not note.is_umbrella("")


def test_tier_is_read_from_the_header() -> None:
    assert note.tier(sample()) == "cheap"
    assert note.tier("# t\nUmbrella: per-repo\n") is None


def test_children_in_file_order_with_fields() -> None:
    kids = note.children(sample())
    assert [(c.key, c.repo) for c in kids] == [
        ("aaaa1111", "kuhyx/alpha"),
        ("bbbb2222", "kuhyx/beta"),
        ("cccc3333", "kuhyx/gamma"),
    ]
    first = kids[0]
    assert (first.scan, first.title, first.done_check, first.done) == (5, "Alpha text", "true", False)
    assert kids[2].scan is None
    assert kids[2].title == "gamma"
    assert kids[2].index == 2


def test_checkbox_marks_a_child_done() -> None:
    kids = note.children(umbrella_body(("a", "aaaa1111", "x"), ("b", "bbbb2222", "y"), done=("bbbb2222",)))
    assert [c.done for c in kids] == [False, True]


def test_original_headings_stay_inside_their_child() -> None:
    inner = child_text("T", extra="## Sub heading\nmore\n```\n## kuhyx/z (zzzz9999)\n```")
    kids = note.children(umbrella_body(("a", "aaaa1111", inner), ("b", "bbbb2222", "y")))
    assert [c.key for c in kids] == ["aaaa1111", "bbbb2222"]
    assert "## Sub heading" in kids[0].text


def test_a_done_marked_heading_still_parses() -> None:
    body = HEADER + "- [x] kuhyx/a (aaaa1111)\n## [x] kuhyx/a (aaaa1111)\ntext\n"
    assert [c.key for c in note.children(body)] == ["aaaa1111"]


def test_ease_order_scan_first_then_shortest_text() -> None:
    order = [c.key for c in note.ordered(note.children(sample()))]
    assert order == ["bbbb2222", "aaaa1111", "cccc3333"]


def test_ease_uses_the_smallest_scan_number_and_ties_keep_file_order() -> None:
    body = umbrella_body(
        ("a", "aaaa1111", "Scan one: 9 items\nScan two: 3 items"),
        ("b", "bbbb2222", "Scan x: 3 items"),
        ("c", "cccc3333", "no scan at all but long enough text"),
        ("d", "dddd4444", "short"),
    )
    assert [c.key for c in note.ordered(note.children(body))] == [
        "aaaa1111",
        "bbbb2222",
        "dddd4444",
        "cccc3333",
    ]


def test_tick_marks_the_checkbox_and_is_idempotent() -> None:
    body = sample()
    once = note.tick(body, "bbbb2222-0")
    assert "- [x] kuhyx/beta (bbbb2222)" in once
    assert "- [ ] kuhyx/alpha (aaaa1111)" in once
    assert note.tick(once, "bbbb2222-0") == once
    assert note.tick(body, "nope0000-0") == body
    assert [c.done for c in note.children(once)] == [False, True, False]


def test_tick_ignores_a_checkbox_line_inside_a_child_section() -> None:
    inner = "- [ ] kuhyx/a (aaaa1111)"
    body = umbrella_body(("a", "aaaa1111", inner))
    ticked = note.tick(body, "aaaa1111-0")
    assert ticked.count("- [x]") == 1
    assert ticked.index("- [x]") < ticked.index("## kuhyx/a")


def test_sections_of_one_source_note_get_distinct_ids() -> None:
    body = umbrella_body(("a", "aaaa1111", "one"), ("a", "aaaa1111", "two"), done=())
    kids = note.children(body)
    assert [c.label for c in kids] == ["aaaa1111-0", "aaaa1111-1"]
    second = note.tick(body, "aaaa1111-1")
    assert [c.done for c in note.children(second)] == [False, True]
    assert note.tick(body, "aaaa1111-2") == body
    assert note.tick(body, "garbage") == body
