# API samples

Captured JSON responses from the UniFi Drive controller — one file per
endpoint, showing every field the appliance exposes. They are reference
material for adding sensors: if a value isn't in here, the integration can't
read it.

The files are generated, not hand-written. Regenerate them from a running Home
Assistant with the **UniFi Drive: Dump API responses** action
(`unifi_drive.dump_api`) — in **Developer tools → Actions**, or:

```yaml
action: unifi_drive.dump_api
data:
  output_dir: unifi_drive_api_samples
```

The files land in that directory under your Home Assistant configuration
directory. Copy the ones worth keeping into this folder.

| Field | Purpose |
| --- | --- |
| `config_entry_id` | Which appliance to query. Only needed when more than one is configured. |
| `output_dir` | Where to write, relative to the configuration directory. Defaults to `unifi_drive_api_samples`, created if missing. Paths outside the configuration directory are rejected. |
| `extra_paths` | Additional absolute API paths to probe, e.g. `/api/system`. |

The action also returns the index as response data, so **Developer tools →
Actions** shows the result without opening a single file.

## Not redacted

The output is verbatim: **serial numbers, MAC addresses, IP addresses,
hostnames and account names are all present.** That is the point — it is a
faithful record of what the controller returns. Review the files before
committing them or attaching them to an issue.

For something safe to share, use **Download diagnostics** on the integration
entry instead. It carries the last polled response for each endpoint under
`raw` and the normalised entity data under `processed`, with serials, MACs,
IPs, hostnames and credentials replaced by `**REDACTED**`. It covers only the
six polled endpoints — the action covers the full probe.

## File layout

Each file wraps the response with the path that answered it:

```json
{
  "endpoint": "/proxy/drive/api/v2/storage",
  "status": 200,
  "used_by_integration": true,
  "redacted": false,
  "data": { "...": "the controller response, verbatim" }
}
```

File names come from the logical endpoint (`drive_storage.json`), not the
resolved path, so a firmware that answers on `v1` instead of `v2` still
updates the same file. `_index.json` lists every endpoint that was probed, its
status and its top-level keys — including the ones that 404, which is how you
tell what a given firmware does *not* support.

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
then `v1`. The catalogue lives in [`dump.py`](../dump.py).
