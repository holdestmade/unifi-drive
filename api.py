from __future__ import annotations

import aiohttp
import asyncio
from typing import Any, Optional
from contextlib import suppress


class UniFiDriveClient:
    """Minimal UniFi Drive API client (polling only)."""

    def __init__(self, host: str, username: str, password: str, *, verify_ssl: bool = False) -> None:
        self.host = host.rstrip("/")
        if not self.host.startswith("http"):
            self.host = f"https://{self.host}"
        self.username = username
        self.password = password
        self._verify_ssl = verify_ssl
        self._session: Optional[aiohttp.ClientSession] = None
        self._csrf: Optional[str] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        self._session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
        return self._session

    def _base_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "HomeAssistant-UniFiDrive/0.2",
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

    async def login(self) -> None:
        """Perform login to obtain TOKEN cookie and X-Csrf-Token header."""
        sess = await self._ensure_session()

        # Step 1: GET a CSRF (optional)
        csrf_url = f"{self._base}/api/auth/csrf"
        try:
            async with sess.get(csrf_url, ssl=self._verify_ssl) as resp:
                if resp.headers.get("X-Csrf-Token"):
                    self._csrf = resp.headers.get("X-Csrf-Token")
                else:
                    with suppress(Exception):
                        data = await resp.json()
                        if isinstance(data, dict):
                            self._csrf = data.get("csrfToken") or self._csrf
        except Exception:
            pass

        # Step 2: POST login
        login_url = f"{self._base}/api/auth/login"
        payload = {"username": self.username, "password": self.password}
        headers = self._base_headers() | {"Content-Type": "application/json"}

        async with sess.post(login_url, json=payload, headers=headers, ssl=self._verify_ssl) as resp:
            text = await resp.text()
            if resp.status == 429:
                raise RuntimeError(f"RATE_LIMIT: HTTP 429 - {text}")
            if resp.status in (401, 403):
                raise RuntimeError(f"AUTH_FAILED: HTTP {resp.status} - {text}")
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status} - {text}")
            self._csrf = resp.headers.get("X-Csrf-Token") or self._csrf

    async def _get_or_empty(self, path: str, default: Any) -> Any:
        sess = await self._ensure_session()
        url = f"{self._base}{path}"
        headers = self._base_headers()
        async with sess.get(url, headers=headers, ssl=self._verify_ssl) as resp:
            if resp.status == 404:
                return default
            if resp.status in (401, 403):
                raise RuntimeError(f"HTTP {resp.status} Unauthorized")
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}")
            ct = resp.headers.get("Content-Type","")
            if "application/json" in ct:
                return await resp.json()
            return default

    # Endpoints
    async def get_device_info(self) -> dict[str, Any]:
        return await self._get_or_empty("/proxy/drive/api/v2/systems/device-info", {})

    async def get_storage_root(self) -> dict[str, Any]:
        return await self._get_or_empty("/proxy/drive/api/v2/storage", {})

    async def get_storage_shares(self) -> Any:
        return await self._get_or_empty("/proxy/drive/api/v2/shares", {})

    async def get_storage_volumes(self) -> Any:
        return await self._get_or_empty("/proxy/drive/api/v2/volumes", {})

    async def get_drives(self) -> dict[str, Any]:
        return await self._get_or_empty("/proxy/drive/api/v2/drives", {})

    async def get_fan_control(self) -> dict[str, Any]:
        return await self._get_or_empty("/proxy/drive/api/v2/systems/fan-control", {})

    async def get_all(self) -> dict[str, Any]:
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
