# UniFi Drive Home Assistant Integration

[![Validate](https://github.com/holdestmade/unifi-drive/actions/workflows/validate.yml/badge.svg)](https://github.com/holdestmade/unifi-drive/actions/workflows/validate.yml)
[![GitHub release](https://img.shields.io/github/v/release/holdestmade/unifi-drive)](https://github.com/holdestmade/unifi-drive/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A custom [Home Assistant](https://www.home-assistant.io/) integration for **UniFi Drive / UNAS appliances** (e.g. UNAS Pro). It polls the UniFi OS local API and exposes system status, storage metrics, drive usage and disk health as sensors — no cloud connection required.

## Features

- Local polling of the UniFi OS API with cookie-based sessions, CSRF handling and automatic token refresh.
- Automatic fallback between the `v2` and `v1` Drive API versions, so both newer and older firmware work.
- Rich set of sensors: firmware/app versions, CPU load and temperature, memory, storage totals, per-drive usage and per-disk SMART health.
- Binary sensors for network link status and per-drive snapshot protection.
- Entities are added automatically when new drives or disks appear — no reload needed.
- Config flow with reauthentication, a reconfigure flow for connection settings and an options flow for the polling interval.
- Graceful degradation: if one API endpoint fails, the remaining sensors keep updating.

## Installation

### HACS (recommended)

This integration is not (yet) in the HACS default store, so add it as a **custom repository**:

[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=holdestmade&repository=unifi-drive&category=integration)

Or manually:

1. In Home Assistant open **HACS**, click the three-dot menu (⋮) in the top right and choose **Custom repositories**.
2. Paste the repository URL:

   ```text
   https://github.com/holdestmade/unifi-drive
   ```

3. Select type **Integration** and click **Add**.
4. Search for **UniFi Drive** in HACS, install it, and restart Home Assistant.

Home Assistant **2024.11 or newer** is required.

### Manual

1. Copy the repository content into `custom_components/unifi_drive` inside your Home Assistant configuration directory.
2. Restart Home Assistant.

## Setup

Go to **Settings → Devices & Services → Add Integration**, search for **UniFi Drive** and follow the prompts:

| Field | Description |
| --- | --- |
| **Host** | IP address or hostname of your UniFi OS console (e.g. `192.168.1.211`). |
| **Username / Password** | Credentials for a **local** UniFi OS account. Accounts with 2FA will not work — create a dedicated local admin/viewer account instead. |
| **Verify SSL** | Whether to validate the HTTPS certificate. Leave disabled if the console uses the default self-signed certificate. |
| **Scan interval** | Polling frequency in seconds (default 30, minimum 10). |

After setup:

- **Options** (on the integration entry) — change the polling interval.
- **Reconfigure** (three-dot menu on the entry) — change host, username, password or SSL verification. Leave the password blank to keep the current one.
- If the stored credentials stop working, Home Assistant prompts for **reauthentication** automatically.

## Entities

All entities are attached to a single device representing the appliance.

### System sensors

| Entity | Description |
| --- | --- |
| Firmware Version / Drive App Version | UniFi OS firmware and Drive application versions |
| System Status | Overall system status reported by the appliance |
| CPU Load / CPU Temperature | Current CPU utilisation (%) and temperature |
| Memory Total / Available / Free / Used / Usage | Memory figures in bytes plus usage percentage |
| Active NIC Link Speed | Link speed of the connected network interface (Mbit/s) |
| Fan Profile | Current fan profile (options discovered from the appliance) |

### Storage sensors

| Entity | Description |
| --- | --- |
| Storage Total / Used / Free | Pool capacity figures in bytes |
| Storage Used Percent | Pool usage percentage |
| Shares Count | Number of configured shares |
| Disks Count | Number of populated disk slots |
| Hottest Disk Temperature | Highest temperature across all disks |

### Per-drive sensors (one set per UniFi Drive share)

| Entity | Description |
| --- | --- |
| Usage | Space used by the drive in bytes |
| Status | Drive status reported by the API |
| Member Count | Number of members with access |
| Snapshot Enabled (binary) | Whether snapshot protection is enabled |

### Per-disk sensors (one set per populated slot)

| Entity | Description |
| --- | --- |
| Temperature | Disk temperature |
| Capacity | Disk size in bytes |
| RPM | Spindle speed |
| State | Disk state (e.g. `normal`) |
| Power On | Accumulated power-on hours |
| SMART Bad Sectors / SMART Uncorrectable / Read Error Rate | SMART health counters |

### Binary sensors

| Entity | Description |
| --- | --- |
| Active NIC Connected | Connectivity of the active network interface, with interface details as attributes |

## Troubleshooting

- **"Login failed" during setup** — check the credentials and make sure the account is a *local* UniFi OS account without 2FA.
- **"Login was rate-limited"** — UniFi OS temporarily blocks repeated failed logins. Wait a few minutes and try again.
- **"Cannot connect to the host"** — verify the host/IP, that the console is reachable from Home Assistant, and the SSL setting (disable *Verify SSL* for self-signed certificates).
- **Debug logging** — add the following to `configuration.yaml` and restart:

  ```yaml
  logger:
    logs:
      custom_components.unifi_drive: debug
  ```

- **Diagnostics** — on the integration entry choose **Download diagnostics** for a
  JSON file containing the raw response of every polled endpoint (under `raw`),
  the normalised data the entities use (under `processed`), and the entry
  configuration. Serials, MACs, IPs, hostnames and credentials are redacted.

## Actions

### `unifi_drive.dump_api`

**UniFi Drive: Dump API responses** queries every known controller endpoint and
writes one JSON file per endpoint, showing all the data the appliance exposes.
It is the reference for adding new sensors — if a value isn't in the dump, the
integration can't read it.

```yaml
action: unifi_drive.dump_api
data:
  output_dir: unifi_drive_api_samples
```

| Field | Purpose |
| --- | --- |
| `config_entry_id` | Which appliance to query. Only needed when more than one is configured. |
| `output_dir` | Where to write, relative to the configuration directory. Defaults to `unifi_drive_api_samples`, created if missing. |
| `extra_paths` | Additional absolute API paths to probe, e.g. `/api/system`. |

Alongside the six polled endpoints it probes a set of speculative ones and
records which paths a given firmware actually supports in `_index.json` — the
404s are as informative as the hits. The same index comes back as response
data, so **Developer tools → Actions** shows the result without opening a file.

**The output is not redacted**: serials, MAC addresses, IP addresses and
hostnames are all present. Review the files before sharing them; use
*Download diagnostics* when you need something safe to attach to an issue.

See [`api_samples/README.md`](api_samples/README.md) for the file layout and
the full endpoint list.

## Development

- The integration only uses libraries shipped with Home Assistant core (notably `aiohttp`), so there are no extra requirements to install.
- Every push and pull request is checked by [HACS validation and hassfest](.github/workflows/validate.yml).
- Use Home Assistant's development container or a virtual environment for testing flows. There are currently no automated tests in the repository.

## License

This project is licensed under the [MIT License](LICENSE). Please open an issue or submit a PR if you would like to contribute improvements.
