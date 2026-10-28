"""NLaunchPanel : les instances d'un panel comme appareils de Home Assistant."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NLaunchPanelAuthError, NLaunchPanelClient, NLaunchPanelError
from .const import CONF_TOKEN, CONF_URL, DOMAIN
from .coordinator import NLaunchPanelConfigEntry, NLaunchPanelCoordinator, NLaunchPanelRuntime

PLATFORMS = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH, Platform.UPDATE]


async def async_setup_entry(hass: HomeAssistant, entry: NLaunchPanelConfigEntry) -> bool:
    client = NLaunchPanelClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN])
    try:
        ecriture = await client.can_write()
    except NLaunchPanelAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except NLaunchPanelError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = NLaunchPanelCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = NLaunchPanelRuntime(client=client, coordinator=coordinator, can_write=ecriture)

    # Une instance supprimée du panel : son appareil quitte Home Assistant.
    def retirer_disparues() -> None:
        registre = dr.async_get(hass)
        for appareil in dr.async_entries_for_config_entry(registre, entry.entry_id):
            ids = {i for (d, i) in appareil.identifiers if d == DOMAIN}
            if ids and not ids & set(coordinator.data or {}):
                registre.async_update_device(appareil.id, remove_config_entry_id=entry.entry_id)

    entry.async_on_unload(coordinator.async_add_listener(retirer_disparues))
    entry.async_on_unload(entry.add_update_listener(_recharger))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _recharger(hass: HomeAssistant, entry: NLaunchPanelConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NLaunchPanelConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
