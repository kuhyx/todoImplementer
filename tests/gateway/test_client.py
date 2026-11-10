"""The gateway client: two auth tiers, a 2 s timeout, and no secret in any error."""

from __future__ import annotations

from pathlib import Path

import pytest
from gatewayfakes import API_KEY, PASSWORD, SESSION, Gateway
from todoimpl.gateway.client import TIMEOUT, Client, GatewayError, secret_dir


def test_the_bearer_call_sends_the_key(gateway: Gateway) -> None:
    body = Client().bearer("/api/v1/models/health")
    assert len(body["data"]) == 2
    assert gateway.requests == [("/api/v1/models/health", f"Bearer {API_KEY}")]


def test_an_admin_call_logs_in_once_and_keeps_the_cookie(gateway: Gateway) -> None:
    client = Client()
    client.admin("/api/providers")
    client.admin("/api/combos")
    assert gateway.logins == 1
    assert [seen for path, seen in gateway.requests if path.startswith("/api/p")] == [f"auth={SESSION}"]


def test_a_refused_session_logs_in_again_once(gateway: Gateway) -> None:
    client = Client()
    client.admin("/api/providers")
    gateway.denied = 1
    assert client.admin("/api/combos")["combos"]
    assert gateway.logins == 2


def test_a_session_refused_twice_is_an_error(gateway: Gateway) -> None:
    client = Client()
    client.admin("/api/providers")
    gateway.denied = 2
    with pytest.raises(GatewayError, match="HTTP 401"):
        client.admin("/api/combos")


def test_other_http_errors_are_not_retried(gateway: Gateway) -> None:
    with pytest.raises(GatewayError, match="HTTP 400"):
        Client().admin("/api/usage/nobody")
    assert gateway.logins == 1


def test_a_wrong_password_never_reaches_the_message(gateway: Gateway, secrets: Path) -> None:
    (secrets / "admin_password").write_text("wrong-pw-xyz\n", encoding="utf-8")
    with pytest.raises(GatewayError) as caught:
        Client().admin("/api/providers")
    assert str(caught.value) == "HTTP 401"
    assert "wrong-pw-xyz" not in repr(caught.value)
    assert gateway.logins == 0


@pytest.mark.parametrize("name", ["api_key", "admin_password"])
def test_a_missing_secret_names_the_file_not_its_content(gateway: Gateway, secrets: Path, name: str) -> None:
    (secrets / name).unlink()
    client = Client()
    with pytest.raises(GatewayError, match=f"no {name} file"):
        client.bearer("/api/v1/models/health") if name == "api_key" else client.admin("/api/providers")


def test_an_empty_secret_is_an_error(gateway: Gateway, secrets: Path) -> None:
    (secrets / "api_key").write_text("\n", encoding="utf-8")
    with pytest.raises(GatewayError, match="api_key is empty"):
        Client().bearer("/api/v1/models/health")


def test_a_dead_gateway_is_unreachable_not_a_traceback(secrets: Path) -> None:
    with pytest.raises(GatewayError, match=r"unreachable \(\w+\)"):
        Client("http://127.0.0.1:1").bearer("/api/v1/models/health")


def test_a_slow_gateway_times_out_within_two_seconds(gateway: Gateway) -> None:
    gateway.delay = 0.5
    assert TIMEOUT <= 2.0
    with pytest.raises(GatewayError, match="unreachable"):
        Client(timeout=0.1).bearer("/api/v1/models/health")


def test_an_answer_that_is_not_json_is_an_error(gateway: Gateway) -> None:
    gateway.garbage = True
    with pytest.raises(GatewayError, match="not JSON"):
        Client().bearer("/api/v1/models/health")


def test_an_empty_answer_reads_as_an_empty_object(gateway: Gateway) -> None:
    gateway.answers["/api/v1/models/health"] = b""
    assert Client().bearer("/api/v1/models/health") == {}


def test_the_secret_dir_defaults_to_the_users_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TODOIMPL_OMNIROUTE_DIR")
    assert secret_dir() == Path.home() / ".config" / "omniroute"
    assert PASSWORD  # the fake password is a constant of the fakes, never of kuhy's machine
