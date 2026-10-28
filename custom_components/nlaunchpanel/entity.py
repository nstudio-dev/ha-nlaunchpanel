"""La base des entités : un appareil par instance du panel."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import InstanceData, NLaunchPanelConfigEntry, NLaunchPanelCoordinator


class NLaunchPanelEntity(CoordinatorEntity[NLaunchPanelCoordinator]):
    """Une entité d'une instance."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NLaunchPanelCoordinator, instance_id: str, cle: str) -> None:
        super().__init__(coordinator)
        self.instance_id = instance_id
        self._attr_translation_key = cle
        self._attr_unique_id = f"{instance_id}_{cle}"
        info = coordinator.data[instance_id].info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, instance_id)},
            name=str(info.get("name") or instance_id),
            manufacturer="NLaunchPanel",
            model=str(info.get("docker_image") or info.get("source_type") or "instance"),
            configuration_url=f"{coordinator.client.url}/instances/{instance_id}",
        )

    @property
    def instance(self) -> InstanceData | None:
        return (self.coordinator.data or {}).get(self.instance_id)

    @property
    def available(self) -> bool:
        return super().available and self.instance is not None


def ajouter_au_fil_des_instances(
    entry: NLaunchPanelConfigEntry,
    async_add_entities: AddEntitiesCallback,
    fabrique: Callable[[NLaunchPanelCoordinator, str], Iterable[Entity]],
) -> None:
    """Les entités des instances présentes, puis de celles qui apparaissent."""
    coordinator = entry.runtime_data.coordinator
    connues: set[str] = set()

    @callback
    def nouvelles() -> None:
        ajout: list[Entity] = []
        for iid in coordinator.data or {}:
            if iid not in connues:
                connues.add(iid)
                ajout.extend(fabrique(coordinator, iid))
        if ajout:
            async_add_entities(ajout)

    nouvelles()
    entry.async_on_unload(coordinator.async_add_listener(nouvelles))
