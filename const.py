from __future__ import annotations

DOMAIN = "unifi_drive"

# Config keys
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_VERIFY_SSL = "verify_ssl"
CONF_SCAN_INTERVAL = "scan_interval"

# Defaults
DEFAULT_SCAN_INTERVAL = 30  # seconds
MIN_SCAN_INTERVAL = 10  # seconds

# Actions
SERVICE_DUMP_API = "dump_api"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_OUTPUT_DIR = "output_dir"
ATTR_EXTRA_PATHS = "extra_paths"
DEFAULT_DUMP_DIR = "unifi_drive_api_samples"  # relative to the config directory
