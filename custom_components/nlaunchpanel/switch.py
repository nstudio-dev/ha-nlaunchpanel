"""L'interrupteur marche / arrêt d'une instance (jeton « écriture »)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import NLaunchPanelError
from .coordinator import NLaunchPanelConfigEntry, NLaunchPanelCoordinator
from .entity import NLaunchPanelEntity, ajouter_au_fil_des_instances


async def async_setup_entry(hass: HomeAssistant, entry: NLaunchPanelConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if not entry.runtime_data.can_write:
        return

    def fabrique(c: NLaunchPanelCoordinator, iid: str) -> list[SwitchEntity]:
        return [NLaunchPanelPower(c, iid)]

    ajouter_au_fil_des_instances(entry, async_add_entities, fabrique)


class NLaunchPanelPower(NLaunchPanelEntity, SwitchEntity):
    def __init__(self, coordinator: NLaunchPanelCoordinator, instance_id: str) -> None:
        super().__init__(coordinator, instance_id, "power")

    @property
    def is_on(self) -> bool | None:
        d = self.instance
        return d.running if d else None

    async def _agir(self, action: str) -> None:
        try:
            await self.coordinator.client.action(self.instance_id, action)
        except NLaunchPanelError as err:
            raise HomeAssistantError(f"NLaunchPanel : {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._agir("start")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._agir("stop")
