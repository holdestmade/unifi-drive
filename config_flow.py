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
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
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
            return self.async_show_form(step_id="user", data_schema=_schema(user_input), errors={"base": "auth"})
        finally:
            await client.close()

        data = {
            CONF_HOST: user_input[CONF_HOST],
            CONF_USERNAME: user_input[CONF_USERNAME],
            CONF_PASSWORD: user_input[CONF_PASSWORD],
            CONF_VERIFY_SSL: user_input.get(CONF_VERIFY_SSL, False),
            CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        }
        await self.async_set_unique_id(f"{user_input[CONF_HOST]}_{user_input[CONF_USERNAME]}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="UniFi Drive", data=data)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle a re-authentication request for an existing entry.

        Home Assistant provides the entry id in the flow context when a
        reauthentication is triggered.  The previous implementation ignored that
        information and simply grabbed the first configured entry which meant the
        wrong config entry could be updated in multi-device installations.  This
        method now looks up the specific entry that requested reauth (falling
        back to matching by host/username when the context is unavailable).
        """

        entry: config_entries.ConfigEntry | None = None

        if entry_id := self.context.get("entry_id"):
            entry = self.hass.config_entries.async_get_entry(entry_id)

        if entry is None:
            host = entry_data.get(CONF_HOST)
            username = entry_data.get(CONF_USERNAME)
            entry = next(
                (
                    e
                    for e in self._async_current_entries()
                    if e.data.get(CONF_HOST) == host
                    and e.data.get(CONF_USERNAME) == username
                ),
                None,
            )

        self._reauth_entry = entry
        if self._reauth_entry is None:
            return self.async_abort(reason="unknown")

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        entry = self._reauth_entry
        if entry is None:
            return self.async_abort(reason="unknown")

        if user_input is None:
            defaults = {
                CONF_HOST: entry.data.get(CONF_HOST),
                CONF_USERNAME: entry.data.get(CONF_USERNAME),
                CONF_VERIFY_SSL: entry.data.get(CONF_VERIFY_SSL, False),
                CONF_SCAN_INTERVAL: entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            }
            return self.async_show_form(step_id="reauth_confirm", data_schema=_schema(defaults, include_password=True))

        client = UniFiDriveClient(
            entry.data[CONF_HOST],
            entry.data[CONF_USERNAME],
            user_input[CONF_PASSWORD],
            verify_ssl=entry.data.get(CONF_VERIFY_SSL, False),
        )
        try:
            await client.login()
        except Exception:
            return self.async_show_form(step_id="reauth_confirm", data_schema=_schema(entry.data, include_password=True), errors={"base": "auth"})
        finally:
            await client.close()

        data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
        self.hass.config_entries.async_update_entry(entry, data=data)
        await self.hass.config_entries.async_reload(entry.entry_id)
        return self.async_abort(reason="reauth_successful")

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data = self.config_entry.data
        opts = self.config_entry.options
        defaults = {
            CONF_HOST: opts.get(CONF_HOST, data.get(CONF_HOST)),
            CONF_USERNAME: opts.get(CONF_USERNAME, data.get(CONF_USERNAME)),
            CONF_PASSWORD: opts.get(CONF_PASSWORD, data.get(CONF_PASSWORD)),
            CONF_VERIFY_SSL: opts.get(CONF_VERIFY_SSL, data.get(CONF_VERIFY_SSL, False)),
            CONF_SCAN_INTERVAL: opts.get(CONF_SCAN_INTERVAL, data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        }
        schema = _schema(defaults, include_password=True)
        return self.async_show_form(step_id="init", data_schema=schema)
