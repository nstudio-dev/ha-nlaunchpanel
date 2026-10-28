"""Les capteurs : état, processeur, mémoire, dernière sauvegarde."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import STATUSES
from .coordinator import InstanceData, NLaunchPanelConfigEntry, NLaunchPanelCoordinator
from .entity import NLaunchPanelEntity, ajouter_au_fil_des_instances


@dataclass(frozen=True, kw_only=True)
class NLaunchPanelSensorDescription(SensorEntityDescription):
    valeur: Callable[[InstanceData], Any]


def _statut(d: InstanceData) -> str | None:
    return d.status if d.status in STATUSES else None


DESCRIPTIONS: tuple[NLaunchPanelSensorDescription, ...] = (
    NLaunchPanelSensorDescription(
        key="status", translation_key="status", device_class=SensorDeviceClass.ENUM, options=STATUSES, valeur=_statut,
    ),
    NLaunchPanelSensorDescription(
        key="cpu", translation_key="cpu", native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1, valeur=lambda d: d.cpu_percent,
    ),
    NLaunchPanelSensorDescription(
        key="memory", translation_key="memory", device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES, suggested_unit_of_measurement=UnitOfInformation.MEBIBYTES,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0, valeur=lambda d: d.memory_bytes,
    ),
    NLaunchPanelSensorDescription(
        key="last_backup", translation_key="last_backup", device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC, valeur=lambda d: d.last_backup,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: NLaunchPanelConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    def fabrique(c: NLaunchPanelCoordinator, iid: str) -> list[SensorEntity]:
        return [NLaunchPanelSensor(c, iid, d) for d in DESCRIPTIONS]

    ajouter_au_fil_des_instances(entry, async_add_entities, fabrique)


class NLaunchPanelSensor(NLaunchPanelEntity, SensorEntity):
    entity_description: NLaunchPanelSensorDescription

    def __init__(self, coordinator: NLaunchPanelCoordinator, instance_id: str, description: NLaunchPanelSensorDescription) -> None:
        super().__init__(coordinator, instance_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | float | int | datetime | None:
        d = self.instance
        return self.entity_description.valeur(d) if d else None
