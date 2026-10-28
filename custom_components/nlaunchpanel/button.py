"""Les boutons : redémarrer, sauvegarder, redéployer (jeton « écriture »)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import NLaunchPanelClient, NLaunchPanelError
from .coordinator import NLaunchPanelConfigEntry, NLaunchPanelCoordinator
from .entity import NLaunchPanelEntity, ajouter_au_fil_des_instances


@dataclass(frozen=True, kw_only=True)
class NLaunchPanelButtonDescription(ButtonEntityDescription):
    agir: Callable[[NLaunchPanelClient, str], Awaitable[None]]


DESCRIPTIONS: tuple[NLaunchPanelButtonDescription, ...] = (
    NLaunchPanelButtonDescription(
        key="restart", translation_key="restart", device_class=ButtonDeviceClass.RESTART,
        agir=lambda c, iid: c.action(iid, "restart"),
    ),
    NLaunchPanelButtonDescription(key="backup", translation_key="backup", agir=lambda c, iid: c.run_backup(iid)),
    NLaunchPanelButtonDescription(key="deploy", translation_key="deploy", agir=lambda c, iid: c.deploy(iid)),
)


async def async_setup_entry(hass: HomeAssistant, entry: NLaunchPanelConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    # Un jeton en lecture seule : aucun bouton (le panel refuserait).
    if not entry.runtime_data.can_write:
        return

    def fabrique(c: NLaunchPanelCoordinator, iid: str) -> list[ButtonEntity]:
        return [NLaunchPanelButton(c, iid, d) for d in DESCRIPTIONS]

    ajouter_au_fil_des_instances(entry, async_add_entities, fabrique)


class NLaunchPanelButton(NLaunchPanelEntity, ButtonEntity):
    entity_description: NLaunchPanelButtonDescription

    def __init__(self, coordinator: NLaunchPanelCoordinator, instance_id: str, description: NLaunchPanelButtonDescription) -> None:
        super().__init__(coordinator, instance_id, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        try:
            await self.entity_description.agir(self.coordinator.client, self.instance_id)
        except NLaunchPanelError as err:
            raise HomeAssistantError(f"NLaunchPanel : {err}") from err
        await self.coordinator.async_request_refresh()
