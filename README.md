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

## License

This project is provided as-is without an explicit license.  Please open an issue or submit a PR if you would like to contribute improvements.
