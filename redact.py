"""Redaction helper shared by the diagnostics platform and ``tools/dump_api.py``.

This module deliberately has no Home Assistant or intra-package imports so the
standalone dump script can import it directly from a git checkout.
"""
from __future__ import annotations

from typing import Any

REDACTED = "**REDACTED**"

# Keys whose values are scrubbed.  Compared after lowercasing and stripping
# ``_`` and ``-``, so ``macAddress``, ``mac_address`` and ``mac-address`` all
# match the same entry.
REDACT_KEYS: frozenset[str] = frozenset(
    {
        "apikey",
        "cookie",
        "csrftoken",
        "dns",
        "domain",
        "email",
        "firstname",
        "gateway",
        "hostname",
        "ip",
        "ip4",
        "ip6",
        "ipaddress",
        "ipv4",
        "ipv6",
        "lastname",
        "mac",
        "macaddress",
        "netmask",
        "owner",
        "password",
        "privatekey",
        "publickey",
        "secret",
        "serial",
        "serialnumber",
        "ssid",
        "token",
        "username",
        "wwn",
    }
)


def _normalise(key: str) -> str:
    return key.lower().replace("_", "").replace("-", "")


def _placeholder(value: Any) -> Any:
    """Replace the leaves of ``value`` while preserving its shape.

    Keeping the container structure (and dict keys) intact means a redacted
    dump still documents every field the controller returns.
    """
    if isinstance(value, str):
        return REDACTED
    if isinstance(value, list):
        return [_placeholder(item) for item in value]
    if isinstance(value, dict):
        return {key: _placeholder(item) for key, item in value.items()}
    # Numbers, booleans and null carry no identifying information.
    return value


def redact_payload(value: Any, keys: frozenset[str] = REDACT_KEYS) -> Any:
    """Return ``value`` with the values of sensitive keys replaced."""
    if isinstance(value, dict):
        return {
            key: _placeholder(item)
            if _normalise(key) in keys
            else redact_payload(item, keys)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item, keys) for item in value]
    return value
