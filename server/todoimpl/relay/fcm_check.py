"""Check the FCM service-account key end to end: load it and trade it for an access token; no message is sent.

`python -m todoimpl.relay.fcm_check` prints `ok <project>` and exits 0, or names the problem and exits 1
(scripts/fcm_key.sh --verify-only runs it).
"""

from __future__ import annotations

import asyncio
import sys

import httpx

from . import fcm


async def project_of(transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Return the key's project once Google has issued a token for it."""
    async with httpx.AsyncClient(transport=transport) as http:
        sender = fcm.Sender(http)
        await sender.access_token()
        return sender.check().project


def main(transport: httpx.AsyncBaseTransport | None = None) -> int:
    """Run the check; 0 when the key works."""
    try:
        project = asyncio.run(project_of(transport))
    except fcm.FcmError as err:
        sys.stderr.write(f"FAIL {err}\n")
        return 1
    sys.stdout.write(f"ok {project}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
