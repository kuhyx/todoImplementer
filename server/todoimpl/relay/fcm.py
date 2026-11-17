"""FCM HTTP v1 sender: service-account key -> RS256 assertion -> OAuth access token -> data-only message.

The key is the Firebase service-account JSON at ~/.config/todoImplementer/fcm-service-account.json (0600,
never in git; scripts/fcm_key.sh puts it there). It is read on every token fetch, so dropping the file in
needs no restart. Messages carry `data` only (never a `notification` payload): the app draws icon + counts.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

if TYPE_CHECKING:
    from collections.abc import Callable

SCOPE: Final = "https://www.googleapis.com/auth/firebase.messaging"
SEND_URL: Final = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
GRANT: Final = "urn:ietf:params:oauth:grant-type:jwt-bearer"
LIFETIME_S: Final = 3600
MARGIN_S: Final = 60.0  # fetch a new token in the last minute of the old one
TIMEOUT_S: Final = 10.0


class FcmError(RuntimeError):
    """A ping could not be sent; the text is for the board banner."""


class BadKeyError(FcmError):
    """The service-account key is missing or unusable: notifications are off until it is fixed."""


class UnregisteredError(FcmError):
    """FCM no longer knows this device token (app uninstalled or token rotated)."""


def key_path() -> Path:
    """Return where the service-account key lives."""
    return Path.home() / ".config" / "todoImplementer" / "fcm-service-account.json"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@dataclass(frozen=True)
class Account:
    """The parts of the service-account key the sender needs."""

    email: str
    key: rsa.RSAPrivateKey
    project: str
    token_uri: str

    @classmethod
    def load(cls, path: Path) -> Account:
        """Read the key file; BadKeyError names what is wrong with it."""
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            msg = f"no Firebase service-account key at {path}"
            raise BadKeyError(msg) from None
        except (OSError, ValueError) as err:
            msg = f"unreadable Firebase service-account key {path.name}: {err}"
            raise BadKeyError(msg) from None
        fields = ("client_email", "private_key", "project_id", "token_uri")
        if not isinstance(info, dict) or not all(isinstance(info.get(f), str) for f in fields):
            msg = f"incomplete Firebase service-account key {path.name}"
            raise BadKeyError(msg)
        try:
            key = serialization.load_pem_private_key(info["private_key"].encode(), password=None)
        except ValueError as err:
            msg = f"bad private key in {path.name}: {err}"
            raise BadKeyError(msg) from None
        if not isinstance(key, rsa.RSAPrivateKey):
            msg = f"bad private key in {path.name}: not RSA"
            raise BadKeyError(msg)
        return cls(info["client_email"], key, info["project_id"], info["token_uri"])

    def assertion(self, now: int) -> str:
        """Return the signed JWT that trades for an access token."""
        header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = {
            "iss": self.email,
            "scope": SCOPE,
            "aud": self.token_uri,
            "iat": now,
            "exp": now + LIFETIME_S,
        }
        body = _b64(json.dumps(claims).encode())
        signature = self.key.sign(f"{header}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{header}.{body}.{_b64(signature)}"


def _error_of(response: httpx.Response) -> tuple[str, str]:
    """Return (errorCode or status, message) from a Google error body, empty strings when absent."""
    try:
        error = response.json().get("error")
    except ValueError:
        error = None
    if not isinstance(error, dict):
        return "", ""
    details = error.get("details")
    codes = [d.get("errorCode") for d in details if isinstance(d, dict)] if isinstance(details, list) else []
    code = next((c for c in codes if isinstance(c, str)), str(error.get("status", "")))
    return code, str(error.get("message", ""))


class Sender:
    """Sends data-only messages, keeping one access token until its last minute."""

    def __init__(
        self, http: httpx.AsyncClient, *, path: Path | None = None, clock: Callable[[], float] = time.time
    ) -> None:
        """Send through `http` with the key at `path` (default: key_path())."""
        self._http, self._path, self._clock = http, path or key_path(), clock
        self._token: tuple[str, float] | None = None
        self._account: Account | None = None

    def check(self) -> Account:
        """Load the key now; BadKeyError when it is missing or unusable."""
        self._account = Account.load(self._path)
        return self._account

    async def _access(self) -> tuple[Account, str]:
        now = self._clock()
        if self._account is not None and self._token is not None and self._token[1] - MARGIN_S > now:
            return self._account, self._token[0]
        account = self.check()
        form = {"grant_type": GRANT, "assertion": account.assertion(int(now))}
        response = await self._post(account.token_uri, data=form)
        if response.status_code != httpx.codes.OK:
            msg = f"Google token endpoint said {response.status_code}"
            raise FcmError(msg)
        body = response.json()
        self._token = (str(body["access_token"]), now + float(body.get("expires_in", LIFETIME_S)))
        return account, self._token[0]

    async def access_token(self) -> str:
        """Return a valid access token (the key check of scripts/fcm_key.sh --verify-only)."""
        return (await self._access())[1]

    async def _post(
        self,
        url: str,
        *,
        data: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            return await self._http.post(url, data=data, json=body, headers=headers, timeout=TIMEOUT_S)
        except httpx.HTTPError as err:
            msg = f"cannot reach Google: {err}"
            raise FcmError(msg) from None

    async def send(self, token: str, data: dict[str, str]) -> None:
        """Send one data-only, high-priority message to the device `token`."""
        account, access = await self._access()
        message = {"message": {"token": token, "data": data, "android": {"priority": "high"}}}
        url = SEND_URL.format(project=account.project)
        response = await self._post(url, body=message, headers={"Authorization": f"Bearer {access}"})
        if response.status_code == httpx.codes.OK:
            return
        code, text = _error_of(response)
        msg = f"FCM said {response.status_code} {code} {text}".rstrip()
        if response.status_code == httpx.codes.NOT_FOUND or code == "UNREGISTERED":
            raise UnregisteredError(msg)
        raise FcmError(msg)
