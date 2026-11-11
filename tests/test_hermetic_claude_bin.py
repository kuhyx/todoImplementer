"""Tests reach the fake `claude` on PATH, never the real one a board session sets `$TODOIMPL_CLAUDE` to."""

import os


def test_t1927_inherited_todoimpl_claude_does_not_reach_tests() -> None:
    # The gate runs inside board sessions, whose env carries TODOIMPL_CLAUDE=~/.local/bin/claude.
    assert "TODOIMPL_CLAUDE" not in os.environ
