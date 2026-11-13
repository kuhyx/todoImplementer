"""One-time pairing codes: 300 s, five pending at most, single use."""

import pytest
from todoimpl.http.pairing import CODE_TTL, MAX_PENDING, PairCodes


class Clock:
    def __init__(self) -> None:
        self.now = 5_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


def test_a_minted_code_redeems_once(clock: Clock) -> None:
    codes = PairCodes(clock)
    code, expires = codes.mint()
    assert expires == 5_000 + CODE_TTL
    assert len(code) >= 22
    assert codes.redeem(code)
    assert not codes.redeem(code)


def test_codes_are_random(clock: Clock) -> None:
    codes = PairCodes(clock)
    assert codes.mint()[0] != codes.mint()[0]


@pytest.mark.parametrize("bad", [None, "", "nope", "é" * 22])
def test_unknown_codes_fail(clock: Clock, bad: str | None) -> None:
    codes = PairCodes(clock)
    codes.mint()
    assert not codes.redeem(bad)


def test_a_code_expires_after_300_seconds(clock: Clock) -> None:
    codes = PairCodes(clock)
    code, _ = codes.mint()
    clock.now += CODE_TTL
    assert not codes.redeem(code)


def test_the_last_second_still_works(clock: Clock) -> None:
    codes = PairCodes(clock)
    code, _ = codes.mint()
    clock.now += CODE_TTL - 1
    assert codes.redeem(code)


def test_the_sixth_code_drops_the_oldest(clock: Clock) -> None:
    codes = PairCodes(clock)
    minted = [codes.mint()[0] for _ in range(MAX_PENDING + 1)]
    assert not codes.redeem(minted[0])
    assert all(codes.redeem(code) for code in minted[1:])


def test_expired_codes_do_not_count_towards_the_limit(clock: Clock) -> None:
    codes = PairCodes(clock)
    old = [codes.mint()[0] for _ in range(MAX_PENDING)]
    clock.now += CODE_TTL
    fresh = codes.mint()[0]
    assert codes.redeem(fresh)
    assert not any(codes.redeem(code) for code in old)
