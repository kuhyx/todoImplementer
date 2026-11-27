"""A part holding two signatures keeps one `Seen:` line per signature (T2571).

A merged card (T2408) or a same-issue part carries several `Error-Signature:` blocks. The count of the second
one used to overwrite the first block's `Seen:` line, the first one in the section.
"""

from __future__ import annotations

from todoimpl.errors import ticket

NOTE = """\
## Kartka fixes
### e77a1029-1
Error: perf.slow: slow wait: browse.nextpage
Seen: 2x, first a, last b
Error-Signature: kartka:aaaa
### e77a1029-2
Error: perf.slow: slow wait: browse.nextpage
Seen: 3x, first c, last d
Error-Signature: kartka:bbbb
## [x] Fix kartka: perf.slow slow wait: reader.page [cccc]
Seen: 1x, first e, last f
Error-Signature: kartka:cccc
## Fix kartka: perf.slow slow wait: reader.page [cccc]
Seen: 4x, first e, last f
Error-Signature: kartka:cccc"""


def test_t2571_the_second_signature_rewrites_its_own_seen_line() -> None:
    text = ticket.refresh(NOTE, "kartka:bbbb", "Seen: 9x, first c, last z")
    assert text is not None
    assert "Seen: 2x, first a, last b" in text
    assert "Seen: 9x, first c, last z" in text
    assert "Seen: 3x" not in text


def test_t2571_a_block_with_no_seen_line_gets_its_own() -> None:
    bare = NOTE.replace("Seen: 3x, first c, last d\n", "")
    text = ticket.refresh(bare, "kartka:bbbb", "Seen: 9x, first c, last z")
    assert text is not None
    lines = text.split("\n")
    assert lines[lines.index("Error-Signature: kartka:bbbb") - 1] == "Seen: 9x, first c, last z"
    assert "Seen: 2x, first a, last b" in lines


def test_t2571_a_closed_twin_is_never_the_one_refreshed() -> None:
    text = ticket.refresh(NOTE, "kartka:cccc", "Seen: 5x, first e, last g")
    assert text is not None
    assert "Seen: 1x, first e, last f" in text  # the closed section keeps its text
    assert "Seen: 5x, first e, last g" in text
    assert "Seen: 4x" not in text
