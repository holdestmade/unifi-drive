# UniFi Drive Home Assistant Integration

This repository contains a custom [Home Assistant](https://www.home-assistant.io/) integration that adds sensors and binary sensors for UniFi Drive / UNAS appliances.  It provides a simple polling client that authenticates against the UniFi OS local API and exposes information such as system status, storage metrics, drive health and network connectivity.

## Features

- Login handling with CSRF support and cookie based sessions.
- Data update coordinator that periodically polls the REST API.
- Rich set of sensors covering firmware versions, CPU, memory, storage totals and per-drive metrics.
- Binary sensors for link status and snapshot enablement.
- Config flow with reauthentication and options flow for updating credentials and polling interval.

## Installation

1. Copy the repository into your Home Assistant `custom_components` directory so it is available at `custom_components/unifi_drive`.
2. Restart Home Assistant to load the integration.
3. Navigate to **Settings → Devices & Services → Add Integration**, search for "UniFi Drive" and follow the prompts.

## Configuration Options

During setup you will be prompted for:

- **Host** – the IP or hostname of your UniFi OS console.
- **Username / Password** – credentials for a local UniFi OS account.
- **Verify SSL** – whether to validate the HTTPS certificate.  Disable this if you use the default self-signed certificate.
- **Update Interval** – polling frequency in seconds (defaults to 30 seconds).

These options can be adjusted later from the integration's options dialog.

## Development

- Install dependencies listed in `manifest.json` (notably `aiohttp`).
- Use Home Assistant's development container or virtual environment for testing flows.
- Run static type checking or linting tools as needed.  There are currently no automated tests in the repository.
- Implement Websocket instead of Polling

## Additional UniFi Drive API endpoints to explore

The REST surface exposed under `/proxy/drive/api/v2/` is broader than the handful of resources currently consumed by this integration.  When expanding sensor or binary sensor coverage it is worth inspecting the responses from these commonly observed endpoints:

- `GET /proxy/drive/api/v2/storage/pools` – detailed RAID/pool health and redundancy metadata.
- `GET /proxy/drive/api/v2/storage/tasks` – asynchronous storage tasks such as scrubs, rebuilds, and formatting jobs.
- `GET /proxy/drive/api/v2/alerts` – active alerts and warning notifications raised by UniFi Drive.
- `GET /proxy/drive/api/v2/settings` – global appliance settings, including update channels and power profiles.
- `GET /proxy/drive/api/v2/systems/led` – enclosure LED status and current behaviour.

Capturing these endpoints while logged into the UniFi OS web UI (for example via the browser's developer tools) will reveal the exact payload shape returned by your firmware version.

## License

This project is provided as-is without an explicit license.  Please open an issue or submit a PR if you would like to contribute improvements.
