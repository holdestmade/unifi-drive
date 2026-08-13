"""Probe the UniFi Drive controller API and write the responses to JSON files.

Backs the ``unifi_drive.dump_api`` action.  Output is deliberately *not*
redacted: the point is a faithful record of everything the appliance returns,
which is what new sensors get built from.  The diagnostics download
(``diagnostics.py``) is the redacted view.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .api import UniFiDriveClient

_LOGGER = logging.getLogger(__name__)

# Drive endpoints, relative to ``/proxy/drive/api/<version>/``.  Each is tried
# against every API version until one answers with something other than 404.
# Entries flagged ``True`` are polled by the integration itself; the rest are
# probed for discovery and are expected to 404 on some firmware.
DRIVE_ENDPOINTS: tuple[tuple[str, bool], ...] = (
    ("systems/device-info", True),
    ("systems/fan-control", True),
    ("storage", True),
    ("shares", True),
    ("volumes", True),
    ("drives", True),
    ("systems/info", False),
    ("systems/network", False),
    ("systems/time", False),
    ("systems/notifications", False),
    ("storage/disks", False),
    ("storage/pools", False),
    ("storage/smart", False),
    ("users", False),
    ("groups", False),
    ("settings", False),
    ("activities", False),
    ("snapshots", False),
    ("protocols", False),
)

# Absolute UniFi OS paths, used as-is.
CORE_ENDPOINTS: tuple[str, ...] = (
    "/api/users/self",
    "/api/system",
)

DRIVE_API_VERSIONS: tuple[str, ...] = ("v2", "v1")

INDEX_FILE = "_index.json"


def _filename(prefix: str, target: str) -> str:
    """Build a flat file name that stays stable across API versions.

    The name comes from the logical endpoint rather than the resolved path, so
    a Drive endpoint that moves from ``v2`` to ``v1`` (or back) still lands in
    the same file; the path that actually answered is recorded inside.
    """
    cleaned = target.strip("/").replace("/", "_")
    return f"{prefix}_{cleaned}.json"


def _summarise(payload: Any) -> Any:
    """Describe the shape of a payload for the index file."""
    if isinstance(payload, dict):
        return sorted(payload)
    if isinstance(payload, list):
        first = payload[0] if payload else None
        return {
            "count": len(payload),
            "item_keys": sorted(first) if isinstance(first, dict) else None,
        }
    return type(payload).__name__


async def _probe_drive(client: UniFiDriveClient, suffix: str) -> tuple[str, int, Any]:
    """Try each API version for a Drive endpoint, returning the first hit."""
    path = ""
    status = 404
    payload: Any = None
    for version in DRIVE_API_VERSIONS:
        path = f"/proxy/drive/api/{version}/{suffix}"
        status, payload = await client.request_raw("GET", path)
        if status != 404:
            break
    return path, status, payload


def _write_files(out_dir: Path, documents: dict[str, Any]) -> None:
    """Create the output directory and write each document (blocking)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, document in documents.items():
        (out_dir / name).write_text(
            json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


async def async_dump_api(
    hass: HomeAssistant,
    client: UniFiDriveClient,
    out_dir: Path,
    extra_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Probe every endpoint, write one JSON file each, and return a summary."""
    targets: list[tuple[str, str, bool]] = [
        ("drive", suffix, used) for suffix, used in DRIVE_ENDPOINTS
    ]
    targets.extend(("core", path, False) for path in CORE_ENDPOINTS)

    known = {target for _, target, _ in targets}
    for path in extra_paths or []:
        if path not in known:
            targets.append(("core", path, False))
            known.add(path)

    documents: dict[str, Any] = {}
    index: list[dict[str, Any]] = []

    for kind, target, used in targets:
        if kind == "drive":
            path, status, payload = await _probe_drive(client, target)
        else:
            path = target
            status, payload = await client.request_raw("GET", path)

        entry: dict[str, Any] = {
            "endpoint": path,
            "status": status,
            "used_by_integration": used,
        }

        if status >= 400 or payload is None:
            _LOGGER.debug("Dump: %s returned %s", path, status)
            index.append(entry | {"file": None, "keys": None})
            continue

        name = _filename(kind, target)
        documents[name] = entry | {"redacted": False, "data": payload}
        index.append(entry | {"file": name, "keys": _summarise(payload)})

    documents[INDEX_FILE] = {"redacted": False, "endpoints": index}

    await hass.async_add_executor_job(_write_files, out_dir, documents)

    written = sum(1 for item in index if item["file"])
    _LOGGER.info(
        "Wrote %s of %s UniFi Drive endpoints to %s", written, len(index), out_dir
    )
    return {
        "output_dir": str(out_dir),
        "written": written,
        "probed": len(index),
        "endpoints": index,
    }
