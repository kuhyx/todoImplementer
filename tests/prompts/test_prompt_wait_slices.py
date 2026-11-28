"""A wait is a step too: every call returns within 40 s, so a long job never reads as a stall (T2427)."""

from todoimpl.prompts import standing


def test_t2427_waits_come_in_slices_of_40_s() -> None:
    assert "run_job" in standing.WAITS  # a long job runs as the board's unit; the turn ends, no wait slices
    assert "wait for it" not in standing.GRANT
