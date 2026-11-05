"""Cell formatting, tables, the cap and client-side table params."""

from __future__ import annotations

from typing import Any

import pytest
from todoimpl_mcp import fmt


def test_cap_passes_short_text() -> None:
    assert fmt.cap("abc") == "abc"


def test_cap_cuts_on_a_line_and_says_so() -> None:
    text = ("x" * 99 + "\n") * 300
    out = fmt.cap(text)
    assert len(out) < fmt.CAP_CHARS + 200
    assert "_truncated at ~4k tokens" in out
    assert out.split("\n\n_truncated")[0].endswith("x")


def test_cap_without_newline() -> None:
    out = fmt.cap("y" * (fmt.CAP_CHARS + 5))
    assert out.startswith("y" * fmt.CAP_CHARS + "\n\n_truncated")


def test_as_json_compact() -> None:
    assert fmt.as_json({"a": [1, 2]}) == '{"a":[1,2]}'


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1.234, "$1.23"), (1234.5, "$1,234"), (None, "-"), ("x", "-")],
)
def test_usd(value: object, expected: str) -> None:
    assert fmt.usd(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "-"),
        (True, "True"),
        (0.1234, "0.123"),
        (1234.5, "1,234"),
        (12345, "12,345"),
        ("a|b", "a/b"),
    ],
)
def test_num(value: object, expected: str) -> None:
    assert fmt.num(value) == expected


@pytest.mark.parametrize(("value", "expected"), [(3700, "1h01m"), (125, "2m"), (7.9, "7s"), (None, "-")])
def test_dur(value: object, expected: str) -> None:
    assert fmt.dur(value) == expected


def test_share_and_day() -> None:
    assert fmt.share(0.25) == "25%"
    assert fmt.share(None) == "-"
    assert fmt.day(None) == "-"
    assert len(fmt.day(1760000000)) == 10


def test_text_home_pipes_newlines_and_width() -> None:
    assert fmt.cell(f"{fmt.HOME}/a|b\nc") == "~/a/b c"
    assert fmt.cell(None) == "-"
    assert fmt.cell("abcdef", 4) == "abc…"


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("usd_per_day", 2.0, "$2.00"),
        ("done_share", 0.5, "50%"),
        ("error_rate", 0.5, "50%"),
        ("active_s", 61, "1m"),
        ("first_ts", None, "-"),
        ("ts", None, "-"),
        ("prompts", 3, "3"),
        ("calls", 3, "3"),
    ],
)
def test_auto(key: str, value: object, expected: str) -> None:
    assert fmt.auto(key, value) == expected


def test_table_and_auto_table() -> None:
    assert fmt.table([], []) == "_no rows_"
    rows = [{"name": "a", "usd": 1.0, "nested": [1]}, {"name": "b", "usd": 2.0}]
    out = fmt.auto_table(rows, limit=1)
    assert out.splitlines() == ["| name | usd |", "|---|---|", "| a | $1.00 |"]
    assert fmt.auto_table([]) == "_no rows_"
    custom = fmt.table(rows, [fmt.col("name", "N", lambda v: str(v).upper())])
    assert custom.splitlines()[-1] == "| B |"


def test_counts() -> None:
    meta = {"_tables": {"s": {"returned": 2, "matched": 9}}}
    assert fmt.counts(meta, "s", 2) == "2 of 9 rows"
    assert fmt.counts({}, "s", 4) == "4 rows"


def test_local_table() -> None:
    rows: list[dict[str, Any]] = [
        {"k": "a", "usd": 1.0, "calls": 5, "t": ["x"]},
        {"k": "B", "usd": None, "calls": 1},
        {"k": "c", "usd": 3.0, "calls": 5},
    ]
    assert [r["k"] for r in fmt.local_table(rows, "", "-usd", 0)] == ["c", "a", "B"]
    assert [r["k"] for r in fmt.local_table(rows, "", "usd", 2)] == ["a", "c"]
    assert [r["k"] for r in fmt.local_table(rows, "b", "", 0)] == ["B"]
    assert [r["k"] for r in fmt.local_table(rows, "x", "", 0)] == []
    tied = fmt.local_table(rows, "", "-calls, k", 0)
    assert [r["k"] for r in tied] == ["a", "c", "B"]
