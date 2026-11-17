"""[T2043] The worker seals with the key's blob cipher, the same one the phone app uses."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest
from todoimpl.relay import worker


class _StopError(Exception):
    """Ends serve() once the sealer is built."""


def test_t2043_worker_seals_with_key_cipher_not_master(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blob_cipher = object()

    class Key:
        master = b"m" * 32

        def cipher(self) -> object:
            return blob_cipher

    async def right(raw: Any, secret: str, layout: Any) -> Key:
        return Key()

    seen: list[object] = []

    def sealer(cipher: object, layout: Any) -> None:
        seen.append(cipher)
        raise _StopError

    class Raw:
        async def aclose(self) -> None:
            return None

    class Endpoint:
        def client(self, *args: Any) -> Raw:
            return Raw()

    monkeypatch.setattr(worker, "unlock", right)
    monkeypatch.setattr(worker, "Sealer", sealer)
    with pytest.raises(_StopError):
        asyncio.run(
            worker.serve(
                cast("Any", Endpoint()),
                "pw",
                cast("Any", None),
                worker="w1",
                ready=asyncio.Event(),
            )
        )
    assert seen == [blob_cipher]
