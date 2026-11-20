"""Where the relay connects and as whom, all from ~/.config, none in git (the tutor's tutor/relay/config.py).

The database URL and API key come from crdt-sync's shared ~/.config/crdt-sync/firebase.json; the signed-in
session is this app's own, ~/.config/todoImplementer/firebase_auth.json (seed it once with crdt-sync: `python3
-m tool.seed_session --client-id ... --client-secret ... --app todoImplementer`). The sealing passphrase is
~/.config/crdt-sync/password, read on every attempt so fixing the file needs no restart.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from crdt_sync import (
    ConfigError,
    FirebaseAuthError,
    FirebaseConfig,
    FirebaseTokenProvider,
    credential_store_for,
    load_device_identity,
)
from rtdb_relay.rtdb import Rtdb, RtdbError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from rtdb_relay.seal import Sealer

APP: Final = "todoImplementer"
NAMESPACE_VAR: Final = "TODOIMPL_RELAY_NAMESPACE"  # a slot build's SYNC_NAMESPACE: live checks only (T2354)
_NAMESPACE: Final = re.compile(r"sandbox/[a-z0-9_-]+")


@dataclass(frozen=True)
class Endpoint:
    """The database and an id-token getter; `client` builds an Rtdb on them (sealed when given a sealer)."""

    database_url: str
    token: Callable[[], Awaitable[str]]
    namespace: str = ""
    http: httpx.AsyncClient | None = None  # tests pass the fake's transport

    def client(self, root: str = "", sealer: Sealer | None = None) -> Rtdb:
        """Build an RTDB client under `root`, inside the namespace when one is set."""
        if self.namespace:
            return NsRtdb(
                self.database_url, self.token, self.http, root=root, sealer=sealer, space=self.namespace
            )
        return Rtdb(self.database_url, self.token, self.http, root=root, sealer=sealer)


class NsRtdb(Rtdb):
    """An Rtdb kept inside one sandbox namespace, `at()` included (T2354).

    rtdb_relay's `unlock` reads the key header through `rtdb.at("")`, a client on the bare root: a plain
    Rtdb rooted at `sandbox/slotN` then read the production header and sealed with the production key.
    """

    def __init__(  # noqa: PLR0913 - Rtdb's own arguments plus the namespace
        self,
        database_url: str,
        token: Callable[[], Awaitable[str]],
        client: httpx.AsyncClient | None = None,
        *,
        root: str,
        sealer: Sealer | None = None,
        space: str,
    ) -> None:
        """Root every path at `space/root`; the sealer's AAD stays the plain layout root, as the app's."""
        inside = root == space or root.startswith(f"{space}/")  # rtdb_relay hands back `rtdb.root`
        full = root if inside else "/".join(p for p in (space, root) if p)
        super().__init__(database_url, token, client, root=full, sealer=sealer)
        self.namespace = space

    def at(self, root: str) -> Rtdb:
        """Return a raw client on `root` inside the namespace, sharing this one's connection."""
        return NsRtdb(self._base, self._token, self.client, root=root, space=self.namespace)


def namespace() -> str:
    """Return `$TODOIMPL_RELAY_NAMESPACE` ("" = production); RelaySetupError unless it is `sandbox/<slot>`."""
    value = os.environ.get(NAMESPACE_VAR, "")
    if value and not _NAMESPACE.fullmatch(value):
        msg = f"{NAMESPACE_VAR} must be empty or sandbox/<lowercase name>, got {value!r}"
        raise RelaySetupError(msg)
    return value


class RelaySetupError(RuntimeError):
    """The relay cannot start: no config, no signed-in session or no passphrase."""


def token_source(provider: FirebaseTokenProvider) -> Callable[[], Awaitable[str]]:
    """Wrap the provider as an async id-token getter (the provider is sync and refreshes itself)."""

    async def token() -> str:
        try:
            return await asyncio.to_thread(provider.id_token)
        except FirebaseAuthError as err:
            msg = f"firebase auth failed: {err}"
            raise RtdbError(msg) from None

    return token


def connect() -> Endpoint:
    """Return the database, signed in as this app; RelaySetupError when that is impossible."""
    try:
        config = FirebaseConfig.load()
    except ConfigError as err:
        msg = f"no crdt-sync firebase config ({err})"
        raise RelaySetupError(msg) from err
    provider = FirebaseTokenProvider(config.api_key, credential_store_for(APP))
    if not provider.has_session():
        msg = f"no Firebase sign-in in ~/.config/{APP}/firebase_auth.json"
        raise RelaySetupError(msg)
    return Endpoint(config.database_url, token_source(provider), namespace())


def passphrase(path: Path | None = None) -> str:
    """Read the shared crdt-sync passphrase; RelaySetupError when the file is missing or empty."""
    path = path or Path.home() / ".config" / "crdt-sync" / "password"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as err:
        msg = f"no crdt-sync password ({path.name}: {err.strerror})"
        raise RelaySetupError(msg) from err
    if not text:
        msg = "the crdt-sync password file is empty"
        raise RelaySetupError(msg)
    return text


def device_id(root: Path) -> str:
    """Return the worker's persisted per-install uuid (<run root>/relay/device_id)."""
    folder = root / "relay"
    folder.mkdir(parents=True, exist_ok=True)
    return str(load_device_identity(folder / "device_id").device_id)
