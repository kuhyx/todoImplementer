"""[T2354] A relay worker on a slot build's sandbox namespace unlocks with that namespace's key header.

rtdb_relay's `unlock` reads the header through `rtdb.at("")`, which dropped a client's root: a scratch
worker on `sandbox/slotN` sealed with the production key while the slot app used the sandbox header, so every
request was "undecryptable" and live checks of the phone app could never load a board.
"""

from __future__ import annotations

import asyncio

import pytest
from rtdb_relay.rtdb import Rtdb
from rtdb_relay.tests._fake_rtdb import DB, FakeRtdb
from rtdb_relay.unlock import unlock
from todoimpl.relay import connect
from todoimpl.relay.layout import E2E

NS = "sandbox/slot3"


async def _token() -> str:
    return FakeRtdb(now_ms=0).token  # every fake accepts the same token


def test_t2354_a_namespaced_worker_unlocks_with_the_namespace_header(fake: FakeRtdb) -> None:
    async def go() -> None:
        prod = Rtdb(DB, _token, client=fake.client(), root="")
        await unlock(prod, "production-pass", E2E)  # the real header, another passphrase
        endpoint = connect.Endpoint(DB, _token, namespace=NS, http=fake.client())
        raw = endpoint.client()
        await unlock(raw, "slot-pass", E2E)  # creates the slot's own header
        await unlock(raw, "slot-pass", E2E)  # and reads it back: the production one refuses this passphrase
        sealed = endpoint.client("todoimpl/v1-e2e")
        assert sealed.root == f"{NS}/todoimpl/v1-e2e"
        assert sealed.at("").root == NS
        assert sealed.at(sealed.root).root == sealed.root  # RelayServer listens on rtdb.at(rtdb.root)
        for client in (prod, raw, sealed):
            await client.aclose()

    asyncio.run(go())
    assert isinstance(fake.get(f"{NS}/todoimpl/e2e"), str)
    assert fake.get(f"{NS}/todoimpl/e2e") != fake.get("todoimpl/e2e")


def test_without_a_namespace_the_client_is_the_plain_production_one() -> None:
    endpoint = connect.Endpoint(DB, _token)
    client = endpoint.client("todoimpl/v1-e2e")
    assert type(client) is Rtdb
    assert client.root == "todoimpl/v1-e2e"
    asyncio.run(client.aclose())


@pytest.mark.parametrize(("value", "want"), [("", ""), (NS, NS), ("sandbox/slot-2_b", "sandbox/slot-2_b")])
def test_the_namespace_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, value: str, want: str
) -> None:
    monkeypatch.setenv(connect.NAMESPACE_VAR, value)
    assert connect.namespace() == want


@pytest.mark.parametrize(
    "value", ["todoimpl", "sandbox/", "sandbox/Slot1", "sandbox/a/b", "/sandbox/x", "prod/slot1"]
)
def test_a_namespace_outside_sandbox_is_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(connect.NAMESPACE_VAR, value)
    with pytest.raises(connect.RelaySetupError, match="sandbox/"):
        connect.namespace()
