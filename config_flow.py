from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from .api import UniFiDriveClient


def _schema(defaults: dict[str, Any], include_password: bool = True) -> vol.Schema:
    """Build the config/options schema with sensible defaults."""
    data = {
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
        vol.Optional(CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, False)): bool,
        vol.Optional(CONF_SCAN_INTERVAL, default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): int,
    }
    if include_password:
        data[vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, ""))] = str
    else:
        data[vol.Optional(CONF_PASSWORD, default="")] = str
    return vol.Schema(data)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the UniFi Drive config flow."""
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Initial step: collect host/creds and validate."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=_schema({}))

        client = UniFiDriveClient(
            user_input[CONF_HOST],
            user_input[CONF_USERNAME],
            user_input[CONF_PASSWORD],
            verify_ssl=user_input.get(CONF_VERIFY_SSL, False),
        )
        try:
            await client.login()
        except Exception:
            return self.async_show_form(
                step_id="user",
                data_schema=_schema(user_input),
                errors={"base": "auth"},
            )
        finally:
            await client.close()

        data = {
            CONF_HOST: user_input[CONF_HOST],
            CONF_USERNAME: user_input[CONF_USERNAME],
            CONF_PASSWORD: user_input[CONF_PASSWORD],
            CONF_VERIFY_SSL: user_input.get(CONF_VERIFY_SSL, False),
            CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        }

        # Unique ID ensures a single config per (host, username)
        await self.async_set_unique_id(f"{user_input[CONF_HOST]}_{user_input[CONF_USERNAME]}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title="UniFi Drive", data=data)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Start reauth flow (triggered by 401 during updates)."""
        self._reauth_entry = next(
            (e for e in self._async_current_entries() if e.data.get(CONF_HOST) == entry_data.get(CONF_HOST)),
            None,
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Prompt for password and validate, then update the entry."""
        entry = getattr(self, "_reauth_entry", None)
        if entry is None:
            return self.async_abort(reason="unknown")

        if user_input is None:
            defaults = {
                CONF_HOST: entry.data.get(CONF_HOST, ""),
                CONF_USERNAME: entry.data.get(CONF_USERNAME, ""),
                CONF_VERIFY_SSL: entry.data.get(CONF_VERIFY_SSL, False),
                CONF_SCAN_INTERVAL: entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                CONF_PASSWORD: "",
            }
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=_schema(defaults, include_password=True),
            )

        # Validate new password
        client = UniFiDriveClient(
            entry.data[CONF_HOST],
            entry.data[CONF_USERNAME],
            user_input[CONF_PASSWORD],
            verify_ssl=entry.data.get(CONF_VERIFY_SSL, False),
        )
        try:
            await client.login()
        except Exception:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=_schema(entry.data, include_password=True),
                errors={"base": "auth"},
            )
        finally:
            await client.close()

        # Update entry with the new password and reload
        self.hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]})
        await self.hass.config_entries.async_reload(entry.entry_id)
        return self.async_abort(reason="reauth_successful")

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        # Return an instance; do NOT rely on super().__init__
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow without deprecated self.config_entry assignment and no super().__init__."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        # Do NOT call super().__init__(config_entry); base has no __init__
        # Do NOT assign self.config_entry (deprecated).
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Edit options (host/username/password/verify_ssl/scan_interval)."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        entry = self._entry
        data = entry.data
        opts = entry.options

        defaults = {
            CONF_HOST: opts.get(CONF_HOST, data.get(CONF_HOST, "")),
            CONF_USERNAME: opts.get(CONF_USERNAME, data.get(CONF_USERNAME, "")),
            CONF_PASSWORD: opts.get(CONF_PASSWORD, data.get(CONF_PASSWORD, "")),
            CONF_VERIFY_SSL: opts.get(CONF_VERIFY_SSL, data.get(CONF_VERIFY_SSL, False)),
            CONF_SCAN_INTERVAL: opts.get(CONF_SCAN_INTERVAL, data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        }
        return self.async_show_form(step_id="init", data_schema=_schema(defaults, include_password=True))
