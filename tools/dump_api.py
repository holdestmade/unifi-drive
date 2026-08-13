#!/usr/bin/env python3
"""Dump the UniFi Drive controller API responses to JSON files.

Runs against a live appliance, probes every known endpoint (plus a handful of
speculative ones) and writes one JSON file per endpoint into ``api_samples/``.
The result is a record of exactly what data the controller exposes on a given
firmware, which is what new sensors get built from.

Only the ``aiohttp`` library is needed, so this can be run from a checkout
without a Home Assistant install::

    python tools/dump_api.py --host 192.168.1.211 --username unifi-ro

The password is read from ``--password``, then ``UNIFI_DRIVE_PASSWORD``, and
finally an interactive prompt.  Host and username fall back to
``UNIFI_DRIVE_HOST`` and ``UNIFI_DRIVE_USERNAME``.

Values of identifying keys (serials, MACs, IPs, hostnames, ...) are replaced
with ``**REDACTED**`` unless ``--no-redact`` is passed; dict keys and the
structure around them are always kept, so a redacted dump still shows every
available field.  Review the output before committing it either way.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from getpass import getpass
from pathlib import Path
from typing import Any

import aiohttp

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from api import DEFAULT_TIMEOUT, UniFiDriveClient, UniFiDriveError  # noqa: E402
from redact import redact_payload  # noqa: E402

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


async def _probe_drive(
    client: UniFiDriveClient, suffix: str
) -> tuple[str, int, Any]:
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


async def dump(args: argparse.Namespace, password: str) -> int:
    """Write one file per endpoint and return a process exit code."""
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    connector = aiohttp.TCPConnector(ssl=args.verify_ssl)
    # UniFi OS sets cookies against a bare IP, hence the unsafe cookie jar.
    async with aiohttp.ClientSession(
        connector=connector,
        cookie_jar=aiohttp.CookieJar(unsafe=True),
        timeout=aiohttp.ClientTimeout(total=args.timeout),
    ) as session:
        client = UniFiDriveClient(args.host, args.username, password, session)
        try:
            await client.login()
        except UniFiDriveError as err:
            print(f"Login failed: {err}", file=sys.stderr)
            return 2

        targets: list[tuple[str, str, bool]] = []
        for suffix, used in DRIVE_ENDPOINTS:
            targets.append(("drive", suffix, used))
        for path in CORE_ENDPOINTS:
            targets.append(("core", path, False))
        known = {target for _, target, _ in targets}
        for path in args.extra:
            if path not in known:
                targets.append(("core", path, False))
                known.add(path)

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
                print(f"  {status}  {path}")
                index.append(entry | {"file": None, "keys": None})
                continue

            body = payload if args.no_redact else redact_payload(payload)
            document = entry | {"redacted": not args.no_redact, "data": body}

            name = _filename(kind, target)
            (out_dir / name).write_text(
                json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"  {status}  {path} -> {out_dir / name}")
            index.append(entry | {"file": name, "keys": _summarise(body)})

    (out_dir / "_index.json").write_text(
        json.dumps(
            {"redacted": not args.no_redact, "endpoints": index},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    found = sum(1 for item in index if item["file"])
    print(f"\n{found}/{len(index)} endpoints returned data; index written to {out_dir}/_index.json")
    return 0 if found else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--host",
        default=os.environ.get("UNIFI_DRIVE_HOST"),
        help="IP address or hostname of the UniFi OS console",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("UNIFI_DRIVE_USERNAME"),
        help="Local UniFi OS account (no 2FA)",
    )
    parser.add_argument("--password", default=os.environ.get("UNIFI_DRIVE_PASSWORD"))
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        help="Validate the HTTPS certificate (off by default, as with the integration)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(REPO_ROOT / "api_samples"),
        help="Directory to write the JSON files into (default: api_samples/)",
    )
    parser.add_argument(
        "--no-redact",
        action="store_true",
        help="Keep serials, MACs, IPs and hostnames in the output",
    )
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        metavar="PATH",
        help="Additional absolute path to probe, e.g. /api/system (repeatable)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT.total,
        help="Per-request timeout in seconds",
    )

    args = parser.parse_args(argv)
    if not args.host:
        parser.error("--host is required (or set UNIFI_DRIVE_HOST)")
    if not args.username:
        parser.error("--username is required (or set UNIFI_DRIVE_USERNAME)")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    password = args.password or getpass(f"Password for {args.username}: ")
    return asyncio.run(dump(args, password))


if __name__ == "__main__":
    raise SystemExit(main())
