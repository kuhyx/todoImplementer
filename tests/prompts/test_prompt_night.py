"""The standing grant tells every session about kuhy's night: no questions, park them for the morning."""

from todoimpl.prompts import standing


def test_grant_carries_the_night_rule() -> None:
    assert "22:55" in standing.NIGHT
    assert "05:55" in standing.NIGHT
    assert standing.NIGHT.rstrip() in standing.GRANT
