from __future__ import annotations

import aiohttp
import asyncio
import time
from typing import Any, Optional
from contextlib import suppress


class UniFiDriveClient:
    """UniFi Drive API client with proactive token refresh + 401 retry."""

    def __init__(self, host: str, username: str, password: str, *, verify_ssl: bool = False) -> None:
        self.host = host.rstrip("/")
        if not self.host.startswith("http"):
            self.host = f"https://{self.host}"
        self.username = username
        self.password = password
        self._verify_ssl = verify_ssl

        self._session: Optional[aiohttp.ClientSession] = None
        self._csrf: Optional[str] = None
        self._token_expire_ms: Optional[int] = None  # epoch ms from X-Token-Expire-Time
        # Newer UniFi OS builds expose the Drive endpoints under ``/api/v2`` while
        # older firmware still responds on ``/api/v1``.  Keep a preference ordered
        # list so we can retry gracefully on 404s and remember the working prefix.
        self._drive_api_versions: list[str] = ["v2", "v1"]

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        self._session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
        return self._session

    def _base_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "HomeAssistant-UniFiDrive/0.2.2",
        }
        if self._csrf:
            headers["X-Csrf-Token"] = self._csrf
        return headers

    @property
    def _base(self) -> str:
        return self.host

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _update_auth_from_headers(self, resp: aiohttp.ClientResponse) -> None:
        # Capture updated CSRF and expiry if present
        self._csrf = resp.headers.get("X-Csrf-Token") or resp.headers.get("x-updated-csrf-token") or self._csrf
        xt = resp.headers.get("X-Token-Expire-Time") or resp.headers.get("x-token-expire-time")
        if xt:
            with suppress(Exception):
                self._token_expire_ms = int(xt)

    def _will_expire_within(self, seconds: int) -> bool:
        if not self._token_expire_ms:
            return False
        # Convert seconds to ms; compare to current epoch ms
        return (self._token_expire_ms - int(time.time() * 1000)) <= (seconds * 1000)

    async def login(self) -> None:
        """Perform login to obtain TOKEN cookie and (updated) X-Csrf-Token."""
        sess = await self._ensure_session()

        # (Optional) warm-up CSRF endpoint
        with suppress(Exception):
            async with sess.get(f"{self._base}/api/auth/csrf", ssl=self._verify_ssl) as r:
                self._update_auth_from_headers(r)
                with suppress(Exception):
                    data = await r.json()
                    if isinstance(data, dict):
                        self._csrf = data.get("csrfToken") or self._csrf

        # Login
        login_url = f"{self._base}/api/auth/login"
        payload = {"username": self.username, "password": self.password}
        headers = self._base_headers() | {"Content-Type": "application/json"}

        async with sess.post(login_url, json=payload, headers=headers, ssl=self._verify_ssl) as resp:
            text = await resp.text()
            self._update_auth_from_headers(resp)
            if resp.status == 429:
                raise RuntimeError(f"RATE_LIMIT: HTTP 429 - {text}")
            if resp.status in (401, 403):
                raise RuntimeError(f"AUTH_FAILED: HTTP {resp.status} - {text}")
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status} - {text}")

    async def ensure_authenticated(self) -> None:
        """Refresh the session if token is within 5 minutes of expiring (or unknown)."""
        # If we have no expiry info, rely on endpoints to 401 and then retry.
        if self._will_expire_within(300):  # 5 minutes
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
        sess = await self._ensure_session()
        url = f"{self._base}{path}"
        headers = self._base_headers()

        async with sess.request(method, url, headers=headers, ssl=self._verify_ssl) as resp:
            self._update_auth_from_headers(resp)
            if resp.status == 401 and retry_on_401:
                # Re-auth once and retry the call
                await self.login()
                return await self._request_json(method, path, retry_on_401=False)
            if resp.status == 404:
                if return_on_404:
                    return {}
                raise RuntimeError(f"HTTP 404 - {url}")
            if resp.status >= 400:
                # Surface full message if possible
                with suppress(Exception):
                    return_text = await resp.text()
                    raise RuntimeError(f"HTTP {resp.status} - {return_text}")
                raise RuntimeError(f"HTTP {resp.status}")

            ct = resp.headers.get("Content-Type", "")
            if "application/json" in ct:
                return await resp.json()
            return {}

    async def _request_drive_json(self, method: str, suffix: str) -> Any:
        """Request a UniFi Drive endpoint trying multiple API versions.

        Some appliances only expose ``/proxy/drive/api/v1`` while others use
        ``/proxy/drive/api/v2``.  Probe the known versions until one responds
        successfully and memoise the working prefix so subsequent calls avoid an
        extra round trip.
        """

        last_error: Optional[RuntimeError] = None
        for version in tuple(self._drive_api_versions):
            path = f"/proxy/drive/api/{version}/{suffix}"
            try:
                result = await self._request_json(method, path, return_on_404=False)
            except RuntimeError as err:
                last_error = err
                # Try the next version if this one is simply missing.
                if "HTTP 404" in str(err):
                    continue
                raise
            else:
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
        # Proactively keep session valid
        await self.ensure_authenticated()
        dev, storage_root, shares, vols, drives, fan = await asyncio.gather(
            self.get_device_info(),
            self.get_storage_root(),
            self.get_storage_shares(),
            self.get_storage_volumes(),
            self.get_drives(),
            self.get_fan_control(),
        )
        return {
            "device": dev,
            "storage": storage_root,
            "shares": shares,
            "volumes": vols,
            "drives": drives,
            "fan_control": fan,
        }
