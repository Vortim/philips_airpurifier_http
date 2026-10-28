"""philips_airpurifier_http platform setup"""

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv

from .client import CannotConnect, connect
from .const import DATA_PHILIPS_FANS, DOMAIN, SERVICE_ATTR_ENTITY_ID
from .services import AIRPURIFIER_SERVICE_SCHEMA, SERVICE_TO_METHOD

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.FAN]

CONFIG_SCHEMA = cv.platform_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config) -> bool:
    """Register the integration's services once, for all purifiers."""
    hass.data.setdefault(DATA_PHILIPS_FANS, [])

    async def async_service_handler(service: ServiceCall):
        entity_ids = service.data.get(SERVICE_ATTR_ENTITY_ID)
        service_method = SERVICE_TO_METHOD[service.service]["method"]

        # Params to set to method handler. Drop entity_id.
        params = {
            key: value
            for key, value in service.data.items()
            if key != SERVICE_ATTR_ENTITY_ID
        }

        devices = hass.data[DATA_PHILIPS_FANS]
        if entity_ids:
            devices = [device for device in devices if device.entity_id in entity_ids]

        update_tasks = []
        for device in devices:
            if not hasattr(device, service_method):
                continue
            await getattr(device, service_method)(**params)
            update_tasks.append(asyncio.create_task(device.async_update_ha_state(True)))

        if update_tasks:
            await asyncio.gather(*update_tasks)

    for air_purifier_service, spec in SERVICE_TO_METHOD.items():
        hass.services.async_register(
            DOMAIN,
            air_purifier_service,
            async_service_handler,
            schema=spec.get("schema", AIRPURIFIER_SERVICE_SCHEMA),
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Connect to the purifier; if it's offline, HA retries setup with backoff."""
    host = entry.data[CONF_HOST]
    try:
        entry.runtime_data = await hass.async_add_executor_job(connect, host)
    except CannotConnect as exc:
        raise ConfigEntryNotReady(f"Can't reach the purifier at {host}") from exc

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
