"""Where the relay connects and as whom, all from ~/.config, none in git (the tutor's tutor/relay/config.py).

The database URL and API key come from crdt-sync's shared ~/.config/crdt-sync/firebase.json; the signed-in
session is this app's own, ~/.config/todoImplementer/firebase_auth.json (seed it once with crdt-sync: `python3
-m tool.seed_session --client-id ... --client-secret ... --app todoImplementer`). The sealing passphrase is
~/.config/crdt-sync/password, read on every attempt so fixing the file needs no restart.
"""

from __future__ import annotations

import asyncio
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

    from rtdb_relay.seal import Sealer

APP: Final = "todoImplementer"


@dataclass(frozen=True)
class Endpoint:
    """The database and an id-token getter; `client` builds an Rtdb on them (sealed when given a sealer)."""

    database_url: str
    token: Callable[[], Awaitable[str]]

    def client(self, root: str = "", sealer: Sealer | None = None) -> Rtdb:
        """Build an RTDB client under `root`."""
        return Rtdb(self.database_url, self.token, root=root, sealer=sealer)


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
    return Endpoint(config.database_url, token_source(provider))


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
