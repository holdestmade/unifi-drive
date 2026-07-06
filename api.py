"""Async client for the UniFi Drive (UNAS) API on UniFi OS."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)
USER_AGENT = "HomeAssistant-UniFiDrive"


class UniFiDriveError(RuntimeError):
    """Base error raised by the UniFi Drive client."""


class UniFiDriveAuthError(UniFiDriveError):
    """Authentication failed (bad credentials or session rejected)."""


class UniFiDriveRateLimitError(UniFiDriveError):
    """The controller rate limited the login attempt."""


class UniFiDriveNotFoundError(UniFiDriveError):
    """The requested endpoint does not exist on this appliance."""


class UniFiDriveClient:
    """UniFi Drive API client with proactive token refresh + 401 retry."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self.host = host.rstrip("/")
        if not self.host.startswith("http"):
            self.host = f"https://{self.host}"
        self.username = username
        self.password = password
        self._session = session
        self._csrf: str | None = None
        self._token_expire_ms: int | None = None  # epoch ms from X-Token-Expire-Time
        self._login_lock = asyncio.Lock()
        # Newer UniFi OS builds expose the Drive endpoints under ``/api/v2`` while
        # older firmware still responds on ``/api/v1``.  Keep a preference ordered
        # list so we can retry gracefully on 404s and remember the working prefix.
        self._drive_api_versions: list[str] = ["v2", "v1"]

    def _base_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": USER_AGENT,
        }
        if self._csrf:
            headers["X-Csrf-Token"] = self._csrf
        return headers

    async def close(self) -> None:
        if not self._session.closed:
            await self._session.close()

    def _update_auth_from_headers(self, resp: aiohttp.ClientResponse) -> None:
        # Capture updated CSRF and expiry if present (header lookups are
        # case-insensitive in aiohttp).
        self._csrf = (
            resp.headers.get("X-Csrf-Token")
            or resp.headers.get("X-Updated-Csrf-Token")
            or self._csrf
        )
        expire = resp.headers.get("X-Token-Expire-Time")
        if expire:
            with suppress(TypeError, ValueError):
                self._token_expire_ms = int(expire)

    def _will_expire_within(self, seconds: int) -> bool:
        if not self._token_expire_ms:
            return False
        return (self._token_expire_ms - int(time.time() * 1000)) <= seconds * 1000

    async def login(self) -> None:
        """Perform login to obtain TOKEN cookie and (updated) X-Csrf-Token."""
        async with self._login_lock:
            # (Optional) warm-up CSRF endpoint
            with suppress(aiohttp.ClientError, asyncio.TimeoutError):
                async with self._session.get(f"{self.host}/api/auth/csrf") as resp:
                    self._update_auth_from_headers(resp)
                    with suppress(Exception):
                        data = await resp.json()
                        if isinstance(data, dict):
                            self._csrf = data.get("csrfToken") or self._csrf

            headers = self._base_headers() | {"Content-Type": "application/json"}
            async with self._session.post(
                f"{self.host}/api/auth/login",
                json={"username": self.username, "password": self.password},
                headers=headers,
            ) as resp:
                text = await resp.text()
                self._update_auth_from_headers(resp)
                if resp.status == 429:
                    raise UniFiDriveRateLimitError(f"RATE_LIMIT: HTTP 429 - {text}")
                if resp.status in (401, 403):
                    raise UniFiDriveAuthError(f"AUTH_FAILED: HTTP {resp.status} - {text}")
                if resp.status >= 400:
                    raise UniFiDriveError(f"HTTP {resp.status} - {text}")

    async def ensure_authenticated(self) -> None:
        """Log in again if the token expires within the next 5 minutes.

        When the expiry is unknown we rely on the single 401 retry in
        ``_request_json`` instead of logging in proactively.
        """
        if self._will_expire_within(300):
            await self.login()

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        retry_on_401: bool = True,
        return_on_404: bool = True,
    ) -> Any:
        """Generic JSON request with single 401 reauth + retry.

        ``return_on_404`` allows callers that know about version fallbacks to
        distinguish genuine missing endpoints from ``{}`` payloads.
        """
        url = f"{self.host}{path}"

        async with self._session.request(method, url, headers=self._base_headers()) as resp:
            self._update_auth_from_headers(resp)
            if resp.status == 401:
                if retry_on_401:
                    # Re-auth once and retry the call
                    await self.login()
                    return await self._request_json(
                        method, path, retry_on_401=False, return_on_404=return_on_404
                    )
                raise UniFiDriveAuthError(f"HTTP 401 - {url}")
            if resp.status == 404:
                if return_on_404:
                    return {}
                raise UniFiDriveNotFoundError(f"HTTP 404 - {url}")
            if resp.status >= 400:
                try:
                    text = await resp.text()
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    text = ""
                message = f"HTTP {resp.status} - {text}" if text else f"HTTP {resp.status}"
                raise UniFiDriveError(message)

            if "application/json" in resp.headers.get("Content-Type", ""):
                return await resp.json()
            return {}

    async def _request_drive_json(self, method: str, suffix: str) -> Any:
        """Request a UniFi Drive endpoint trying multiple API versions.

        Some appliances only expose ``/proxy/drive/api/v1`` while others use
        ``/proxy/drive/api/v2``.  Probe the known versions until one responds
        successfully and memoise the working prefix so subsequent calls avoid an
        extra round trip.
        """
        last_error: UniFiDriveNotFoundError | None = None
        for version in tuple(self._drive_api_versions):
            path = f"/proxy/drive/api/{version}/{suffix}"
            try:
                result = await self._request_json(method, path, return_on_404=False)
            except UniFiDriveNotFoundError as err:
                # Try the next version if this one is simply missing.
                last_error = err
                continue
            # Cache the working version at the front for faster lookups
            if version != self._drive_api_versions[0]:
                self._drive_api_versions.remove(version)
                self._drive_api_versions.insert(0, version)
            return result

        # If every version failed with 404, surface the last error so callers can
        # handle it (coordinator will wrap into UpdateFailed/AuthFailed as
        # appropriate).
        if last_error:
            raise last_error
        return {}

    # --- Endpoints ---
    async def get_device_info(self) -> dict[str, Any]:
        return await self._request_drive_json("GET", "systems/device-info")

    async def get_storage_root(self) -> dict[str, Any]:
        return await self._request_drive_json("GET", "storage")

    async def get_storage_shares(self) -> Any:
        return await self._request_drive_json("GET", "shares")

    async def get_storage_volumes(self) -> Any:
        return await self._request_drive_json("GET", "volumes")

    async def get_drives(self) -> dict[str, Any]:
        return await self._request_drive_json("GET", "drives")

    async def get_fan_control(self) -> dict[str, Any]:
        return await self._request_drive_json("GET", "systems/fan-control")

    async def get_all(self) -> dict[str, Any]:
        """Fetch all endpoints, tolerating individual endpoint failures.

        Auth errors are always raised; other per-endpoint errors degrade to an
        empty payload for that key unless every endpoint failed.
        """
        # Proactively keep session valid
        await self.ensure_authenticated()

        keys = ("device", "storage", "shares", "volumes", "drives", "fan_control")
        results = await asyncio.gather(
            self.get_device_info(),
            self.get_storage_root(),
            self.get_storage_shares(),
            self.get_storage_volumes(),
            self.get_drives(),
            self.get_fan_control(),
            return_exceptions=True,
        )

        data: dict[str, Any] = {}
        errors: list[BaseException] = []
        for key, result in zip(keys, results, strict=True):
            if isinstance(result, BaseException):
                if isinstance(result, (asyncio.CancelledError, UniFiDriveAuthError)):
                    raise result
                _LOGGER.debug("Error fetching %s: %s", key, result)
                errors.append(result)
                data[key] = {}
            else:
                data[key] = result
        if errors and len(errors) == len(keys):
            raise errors[0]
        return data
