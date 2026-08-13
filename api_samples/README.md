# API samples

Captured JSON responses from the UniFi Drive controller — one file per
endpoint, showing every field the appliance exposes. They are reference
material for adding sensors: if a value isn't in here, the integration can't
read it.

The files are generated, not hand-written. Regenerate them from a checkout
with:

```bash
python tools/dump_api.py --host 192.168.1.211 --username unifi-ro
```

`aiohttp` is the only requirement; Home Assistant does not need to be
installed. The password is read from `--password`, then the
`UNIFI_DRIVE_PASSWORD` environment variable, then an interactive prompt.
Host and username also accept `UNIFI_DRIVE_HOST` / `UNIFI_DRIVE_USERNAME`.

Useful flags:

| Flag | Effect |
| --- | --- |
| `--verify-ssl` | Validate the HTTPS certificate (off by default, matching the integration) |
| `-o DIR` | Write somewhere other than `api_samples/` |
| `--extra PATH` | Probe an additional absolute path, e.g. `--extra /api/system` (repeatable) |
| `--no-redact` | Keep serials, MACs, IPs and hostnames in the output |

## File layout

Each file wraps the response with the path that answered it:

```json
{
  "endpoint": "/proxy/drive/api/v2/storage",
  "status": 200,
  "used_by_integration": true,
  "redacted": true,
  "data": { "...": "the controller response, verbatim" }
}
```

File names come from the logical endpoint (`drive_storage.json`), not the
resolved path, so a firmware that answers on `v1` instead of `v2` still
updates the same file. `_index.json` lists every endpoint that was probed,
its status and its top-level keys — including the ones that 404, which is how
you tell what a given firmware does *not* support.

## Redaction

Values of identifying keys — serials, MACs, IPs, hostnames, usernames, emails,
tokens — are replaced with `**REDACTED**` unless `--no-redact` is passed. Keys
and the structure around them are always preserved, so a redacted dump still
documents every available field. **Review the output before committing it**;
share and drive names are not redacted, and neither are unrecognised keys on
firmware newer than this script.

## Endpoints

Endpoints marked *polled* are fetched on every update by `api.py`'s
`get_all()`. The rest are probed for discovery and may not exist on all
firmware.

| Endpoint | Polled | Feeds |
| --- | --- | --- |
| `systems/device-info` | yes | Firmware/app versions, system status, CPU load and temperature, memory, NIC link speed and connectivity |
| `storage` | yes | Pool totals, per-disk temperature, capacity, RPM, state, power-on hours, SMART counters |
| `shares` | yes | Shares count |
| `volumes` | yes | Storage totals fallback when pools are unavailable |
| `drives` | yes | Per-drive usage, status, member count, snapshot protection |
| `systems/fan-control` | yes | Fan profile and the profile options |
| `systems/info`, `systems/network`, `systems/time`, `systems/notifications` | no | — |
| `storage/disks`, `storage/pools`, `storage/smart` | no | — |
| `users`, `groups`, `settings`, `activities`, `snapshots`, `protocols` | no | — |
| `/api/users/self`, `/api/system` | no | UniFi OS core, outside the Drive API |

Drive endpoints are requested under `/proxy/drive/api/<version>/`, trying `v2`
then `v1`.

## Live data from a running Home Assistant

The same raw payloads are available without running the script: open the
integration entry and choose **Download diagnostics**. That file contains the
last polled response for each endpoint under `raw`, plus the normalised view
the entities are built from under `processed`, with the same redaction applied.
It only covers the six polled endpoints — use the script for the full probe.
