from datetime import UTC, date, datetime, timedelta

import pytest
from apikeyfakes import KEY, USER_KEY
from todoimpl.apikey import keystatus as status
from todoimpl.apikey import store
from todoimpl.apikey.verify import Verdict

TODAY = date(2026, 11, 8)


def run(verdict: Verdict | None = None, *, today: date = TODAY) -> status.KeyStatus:
    def check(_key: str) -> Verdict:
        assert verdict is not None, "no live call expected"
        return verdict

    return status.status(today=today, check=check)


VALID = Verdict("valid", "ok")


def test_missing_key_file() -> None:
    result = run()
    assert (result.state, result.usable, result.expires) == ("missing", False, None)
    assert "anthropic_api_key" in result.detail


def test_malformed_key_is_invalid_without_a_live_call() -> None:
    store.key_path().parent.mkdir(parents=True)
    store.key_path().write_text("not a key\n")
    result = run()
    assert (result.state, result.usable) == ("invalid", False)
    assert "format" in result.detail


def test_valid_key_with_far_expiry_is_ok() -> None:
    store.save(KEY, TODAY, TODAY + timedelta(days=30))
    result = run(VALID)
    assert (result.state, result.usable, result.expires) == ("ok", True, TODAY + timedelta(days=30))


@pytest.mark.parametrize("days", [3, 1, 0])
def test_expiry_within_three_days_warns_and_stays_usable(days: int) -> None:
    store.save(KEY, TODAY, TODAY + timedelta(days=days))
    result = run(VALID)
    assert (result.state, result.usable) == ("expiring", True)
    assert str(TODAY + timedelta(days=days)) in result.detail


def test_four_days_left_is_still_ok() -> None:
    store.save(KEY, TODAY, TODAY + timedelta(days=4))
    assert run(VALID).state == "ok"


def test_past_expiry_is_expired_and_needs_no_network() -> None:
    store.save(KEY, TODAY - timedelta(days=30), TODAY - timedelta(days=1))
    result = run()
    assert (result.state, result.usable) == ("expired", False)
    assert str(TODAY - timedelta(days=1)) in result.detail


def test_live_rejection_is_invalid() -> None:
    store.save(KEY, TODAY, TODAY + timedelta(days=20))
    result = run(Verdict("invalid", "HTTP 401"))
    assert (result.state, result.usable) == ("invalid", False)
    assert "expired or revoked" in result.detail


def test_network_failure_is_check_failed_not_ok() -> None:
    store.save(KEY, TODAY, TODAY + timedelta(days=20))
    result = run(Verdict("check_failed", "timed out"))
    assert (result.state, result.usable) == ("check_failed", False)
    assert "timed out" in result.detail


def test_no_meta_but_live_valid_is_ok_with_unknown_expiry() -> None:
    store.key_path().parent.mkdir(parents=True)
    store.key_path().write_text(KEY)
    result = run(VALID)
    assert (result.state, result.expires) == ("ok", None)
    assert "expiry" in result.detail


def test_defaults_use_todays_date_and_the_real_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(tz=UTC).date()
    store.save(KEY, now, now + timedelta(days=30))
    seen: list[str] = []

    def check(key: str) -> Verdict:
        seen.append(key)
        return VALID

    monkeypatch.setattr(status, "verify", check)
    assert status.status().state == "ok"
    assert seen == [KEY]


def test_banner_levels_and_text() -> None:
    expires = date(2026, 12, 1)
    cases = {
        "ok": "ok",
        "expiring": "warn",
        "expired": "error",
        "invalid": "error",
        "missing": "error",
        "check_failed": "error",
    }
    for state, level in cases.items():
        field = status.board_field(status.KeyStatus(state, expires, "why"))  # type: ignore[arg-type]
        assert field["level"] == level
        assert field["state"] == state
        assert field["expires"] == "2026-12-01"
        assert "why" in field["text"]
        assert (status.ROTATE_COMMAND in field["text"]) == (level != "ok")
    assert status.board_field(status.KeyStatus("missing", None, "x"))["expires"] is None


def test_a_user_linked_key_is_checked_like_any_other() -> None:
    store.save(USER_KEY, TODAY, TODAY + timedelta(days=30))
    seen: list[str] = []

    def check(key: str) -> Verdict:
        seen.append(key)
        return VALID

    assert status.status(today=TODAY, check=check).state == "ok"
    assert seen == [USER_KEY]
