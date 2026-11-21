"""A wait is a step too: every call returns within 40 s, so a long job never reads as a stall (T2427)."""

from todoimpl.prompts import standing


def test_t2427_waits_come_in_slices_of_40_s() -> None:
    assert "timeout 40" in standing.WAITS  # T2453
    assert "journalctl -f" in standing.WAITS
    assert "tail -f" in standing.WAITS
    assert "wait for it." not in standing.GRANT
    assert "never starts it again" in standing.WAITS  # a killed client leaves its unit running
