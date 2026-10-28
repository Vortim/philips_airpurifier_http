"""Config flow for Philips AirPurifier (HTTP)."""

import logging
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_HOST, CONF_NAME

try:
    from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo
except ImportError:  # HA < 2025.1
    from homeassistant.components.ssdp import SsdpServiceInfo

from .client import CannotConnect, probe
from .const import CONF_MAC, DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
    }
)
RECONFIGURE_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


class PhilipsAirPurifierConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a purifier by IP, change its IP later, or pick it up via SSDP."""

    VERSION = 1

    def __init__(self):
        self._host = None
        self._mac = None
        self._name = DEFAULT_NAME

    async def _async_probe(self, host):
        return await self.hass.async_add_executor_job(probe, host)

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                info = await self._async_probe(host)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info["mac"] or host)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={CONF_HOST: host, CONF_MAC: info["mac"]},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Point an existing purifier at a new IP address."""
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                info = await self._async_probe(host)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                known_mac = entry.data.get(CONF_MAC)
                if known_mac and info["mac"] and info["mac"] != known_mac:
                    errors["base"] = "wrong_device"
                else:
                    mac = info["mac"] or known_mac
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=mac or entry.unique_id,
                        data_updates={CONF_HOST: host, CONF_MAC: mac},
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                RECONFIGURE_SCHEMA, user_input or {CONF_HOST: entry.data[CONF_HOST]}
            ),
            errors=errors,
        )

    async def async_step_import(self, import_data):
        """Import a purifier from YAML. The device may be offline at boot, so
        don't require it to answer — setup of the entry retries on its own."""
        host = import_data[CONF_HOST]
        name = import_data[CONF_NAME]
        for entry in self._async_current_entries(include_ignore=False):
            if entry.data.get(CONF_HOST) == host or entry.title == name:
                return self.async_abort(reason="already_configured")

        try:
            info = await self._async_probe(host)
        except CannotConnect:
            info = {"mac": None}
        await self.async_set_unique_id(info["mac"] or host)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        return self.async_create_entry(
            title=name, data={CONF_HOST: host, CONF_MAC: info["mac"]}
        )

    async def async_step_ssdp(self, discovery_info: SsdpServiceInfo):
        """A purifier announced itself; if it's a known one at a new IP, update it."""
        host = urlparse(discovery_info.ssdp_location).hostname
        try:
            info = await self._async_probe(host)
        except CannotConnect:
            return self.async_abort(reason="cannot_connect")
        if not info["mac"]:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(info["mac"])
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._host = host
        self._mac = info["mac"]
        self._name = (
            discovery_info.upnp.get("friendlyName") or info["model"] or DEFAULT_NAME
        )
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title=self._name, data={CONF_HOST: self._host, CONF_MAC: self._mac}
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"name": self._name, "host": self._host},
        )
