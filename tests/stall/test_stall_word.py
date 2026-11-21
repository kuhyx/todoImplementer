"""A job's signature names its program, not an env assignment in front of it (T2430)."""

import pytest
from todoimpl.stall import cause


@pytest.mark.parametrize(
    ("command", "word"),
    [
        ("CAP_CPU_PCT=20 scripts/test.sh --shard 6/10 2>&1 | tail -n 1", "test.sh"),
        ("A=1 B=x /usr/bin/make -s test", "make"),
        ("systemd-run --user --wait x", "systemd-run"),
        ("X=1", "unknown"),
        ("", "unknown"),
    ],
)
def test_t2430_the_word_skips_env_assignments(command: str, word: str) -> None:
    assert cause._word(command) == word
