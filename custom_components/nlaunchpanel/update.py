"""La mise à jour de l'image Docker d'une instance (celle du panel)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import NLaunchPanelError
from .coordinator import NLaunchPanelConfigEntry, NLaunchPanelCoordinator
from .entity import NLaunchPanelEntity, ajouter_au_fil_des_instances


def _court(digest: str) -> str:
    """« sha256:1a2b3c4d5e6f… » → « 1a2b3c4d5e6f »."""
    return digest.removeprefix("sha256:")[:12]


async def async_setup_entry(hass: HomeAssistant, entry: NLaunchPanelConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    ecriture = entry.runtime_data.can_write

    def fabrique(c: NLaunchPanelCoordinator, iid: str) -> list[UpdateEntity]:
        # Seules les instances Docker ont une image à mettre à jour.
        if c.data[iid].info.get("source_type") != "docker":
            return []
        return [NLaunchPanelImageUpdate(c, iid, ecriture)]

    ajouter_au_fil_des_instances(entry, async_add_entities, fabrique)


class NLaunchPanelImageUpdate(NLaunchPanelEntity, UpdateEntity):
    """La nouvelle construction du même tag, ou la version suivante de la même majeure."""

    def __init__(self, coordinator: NLaunchPanelCoordinator, instance_id: str, ecriture: bool) -> None:
        super().__init__(coordinator, instance_id, "image")
        if ecriture:
            self._attr_supported_features = UpdateEntityFeature.INSTALL

    @property
    def _etat(self) -> dict[str, Any]:
        d = self.instance
        return (d.image if d else None) or {}

    @property
    def installed_version(self) -> str | None:
        e = self._etat
        image = str(e.get("image") or "")
        tag = image.rsplit(":", 1)[1] if ":" in image.rsplit("/", 1)[-1] else "latest"
        courant = _court(str(e.get("current_digest") or ""))
        return f"{tag} ({courant})" if courant else (tag if e else None)

    @property
    def latest_version(self) -> str | None:
        e = self._etat
        if not e:
            return None
        if e.get("same_major"):
            return str(e["same_major"])
        registre = _court(str(e.get("registry_digest") or ""))
        if registre:
            image = str(e.get("image") or "")
            tag = image.rsplit(":", 1)[1] if ":" in image.rsplit("/", 1)[-1] else "latest"
            return f"{tag} ({registre})"
        return self.installed_version

    @property
    def in_progress(self) -> bool:
        # La sauvegarde d'avant, puis le déploiement (ui/lib/imagesMaj.ts : majEnCours).
        apply = self._etat.get("apply")
        return isinstance(apply, dict) and apply.get("status") in ("backup", "deploying")

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        # Le panel sauvegarde avant d'appliquer, et revient en arrière si la
        # nouvelle image ne démarre pas saine.
        genre = "version" if self._etat.get("same_major") else "build"
        try:
            await self.coordinator.client.apply_image_update(self.instance_id, genre)
        except NLaunchPanelError as err:
            raise HomeAssistantError(f"NLaunchPanel : {err}") from err
        await self.coordinator.async_request_refresh()
