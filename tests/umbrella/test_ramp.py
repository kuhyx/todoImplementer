"""Manager verdict lines and the width rule (the server adjudicates, never the LLM)."""

from __future__ import annotations

from todoimpl.umbrella import ramp
from todoimpl.umbrella.note import Child


def _kid(key: str, repo: str) -> Child:
    return Child(key, 0, f"kuhyx/{repo}", 0, "t", "t", None, None, done=False, cid=f"{key}-0")


KIDS = [_kid("aaaa1111", "a"), _kid("bbbb2222", "b"), _kid("cccc3333", "c")]


def test_lines_are_matched_by_repo() -> None:
    text = (
        "working...\nCHILD kuhyx/a: clean\n**CHILD kuhyx/b: fixed edited the config**\n"
        "CHILD kuhyx/c: escalate worker looped\nD: done"
    )
    got = ramp.parse_verdicts(text, KIDS)
    assert got["aaaa1111-0"] == ramp.Verdict("clean", "")
    assert got["bbbb2222-0"] == ramp.Verdict("fixed", "edited the config")
    assert got["cccc3333-0"] == ramp.Verdict("escalate", "worker looped")


def test_an_id_suffix_picks_the_child_when_a_repo_repeats() -> None:
    twins = [_kid("aaaa1111", "a"), _kid("dddd4444", "a")]
    got = ramp.parse_verdicts("CHILD kuhyx/a (dddd4444): fixed x\nCHILD kuhyx/a: clean", twins)
    assert got["dddd4444-0"].kind == "fixed"
    assert got["aaaa1111-0"].kind == "clean"


def test_a_missing_or_unknown_line_escalates() -> None:
    got = ramp.parse_verdicts("CHILD kuhyx/a: clean\nCHILD kuhyx/zzz: clean", KIDS)
    assert got["aaaa1111-0"].kind == "clean"
    assert got["bbbb2222-0"] == ramp.Verdict("escalate", ramp.NO_LINE)
    assert got["cccc3333-0"].kind == "escalate"


def test_a_repeated_line_keeps_the_worst_verdict() -> None:
    got = ramp.parse_verdicts("CHILD kuhyx/a: clean\nCHILD kuhyx/a: escalate late", KIDS[:1])
    assert got["aaaa1111-0"] == ramp.Verdict("escalate", "late")
    got = ramp.parse_verdicts("CHILD kuhyx/a: fixed x\nCHILD kuhyx/a: clean", KIDS[:1])
    assert got["aaaa1111-0"].kind == "fixed"


def test_every_child_escalates_when_the_manager_failed() -> None:
    got = ramp.all_escalate(KIDS, "turn failed")
    assert {k: v.kind for k, v in got.items()} == dict.fromkeys(
        ("aaaa1111-0", "bbbb2222-0", "cccc3333-0"), "escalate"
    )
    assert got["aaaa1111-0"].detail == "turn failed"


def test_ok_needs_clean_free_and_green_checks() -> None:
    clean = ramp.Verdict("clean", "")
    assert ramp.ok(clean, free=True, checks=True)
    assert not ramp.ok(clean, free=False, checks=True)
    assert not ramp.ok(clean, free=True, checks=False)
    assert not ramp.ok(clean, free=True, checks=None)
    assert not ramp.ok(ramp.Verdict("fixed", "x"), free=True, checks=True)
    assert not ramp.ok(ramp.Verdict("escalate", "x"), free=True, checks=True)


def test_width_doubles_only_when_every_child_is_ok() -> None:
    assert ramp.next_width(1, [True]) == 2
    assert ramp.next_width(4, [True, True, True, True]) == 8
    assert ramp.next_width(4, [True, True, True, False]) == 4
    assert ramp.next_width(2, []) == 2
    assert ramp.next_width(1, [False]) == 1


def test_take_the_next_width_children_in_order() -> None:
    assert ramp.take(["a", "b", "c", "d", "e"], 2) == ["a", "b"]
    assert ramp.take(["a"], 8) == ["a"]
    assert ramp.take([], 4) == []


def test_t2054_coached_parses_with_its_retry_count_and_ranks_between_clean_and_fixed() -> None:
    got = ramp.parse_verdicts("CHILD kuhyx/a: coached 2 prompt rewritten", KIDS[:1])
    assert got["aaaa1111-0"] == ramp.Verdict("coached", "2 prompt rewritten")
    assert (
        ramp.parse_verdicts("CHILD kuhyx/a: coached 1\nCHILD kuhyx/a: clean", KIDS[:1])["aaaa1111-0"].kind
        == "coached"
    )
    assert (
        ramp.parse_verdicts("CHILD kuhyx/a: fixed x\nCHILD kuhyx/a: coached 1", KIDS[:1])["aaaa1111-0"].kind
        == "fixed"
    )


def test_t2054_coached_counts_toward_doubling_unless_it_hit_the_cap() -> None:
    assert ramp.ok(ramp.Verdict("coached", "1"), free=True, checks=True)
    assert ramp.ok(ramp.Verdict("coached", "2 x"), free=True, checks=True)
    assert not ramp.ok(ramp.Verdict("coached", "3"), free=True, checks=True)
    assert not ramp.ok(ramp.Verdict("coached", "many"), free=True, checks=True)
    assert not ramp.ok(ramp.Verdict("coached", "1"), free=False, checks=True)
    assert not ramp.ok(ramp.Verdict("coached", "1"), free=True, checks=False)
