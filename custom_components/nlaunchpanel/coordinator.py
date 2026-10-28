"""Le coordinateur : un tour toutes les 60 s pour tout le panel."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import NLaunchPanelAuthError, NLaunchPanelClient, NLaunchPanelConnectionError, NLaunchPanelError
from .const import CONF_PERSISTENT, DOMAIN, EVENT_NOTIFICATION, MAX_PARALLEL, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass
class InstanceData:
    """Ce que le panel dit d'une instance, à ce tour."""

    info: dict[str, Any]
    cpu_percent: float | None = None
    memory_bytes: int | None = None
    last_backup: datetime | None = None
    backup_configured: bool = False
    image: dict[str, Any] | None = field(default=None)

    @property
    def status(self) -> str:
        return str(self.info.get("status") or "")

    @property
    def running(self) -> bool:
        return self.status == "running"


type NLaunchPanelConfigEntry = ConfigEntry["NLaunchPanelRuntime"]


@dataclass
class NLaunchPanelRuntime:
    """Ce que l'entrée garde en mémoire (entry.runtime_data)."""

    client: NLaunchPanelClient
    coordinator: "NLaunchPanelCoordinator"
    can_write: bool


class NLaunchPanelCoordinator(DataUpdateCoordinator[dict[str, InstanceData]]):
    """Les instances de l'organisation du jeton, et la cloche de son propriétaire."""

    config_entry: NLaunchPanelConfigEntry

    def __init__(self, hass: HomeAssistant, entry: NLaunchPanelConfigEntry, client: NLaunchPanelClient) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.client = client
        # Les notifications déjà vues ; None : le premier tour, qui ne signale
        # rien (on ne rejoue pas tout l'historique de la cloche à l'installation).
        self._vues: set[str] | None = None

    async def _async_update_data(self) -> dict[str, InstanceData]:
        try:
            instances = await self.client.instances()
        except NLaunchPanelAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NLaunchPanelError as err:
            raise UpdateFailed(str(err)) from err

        limite = asyncio.Semaphore(MAX_PARALLEL)

        async def detail(info: dict[str, Any]) -> InstanceData:
            async with limite:
                return await self._detail(info)

        details = await asyncio.gather(*(detail(i) for i in instances))
        await self._notifications()
        return {d.info["id"]: d for d in details}

    async def _detail(self, info: dict[str, Any]) -> InstanceData:
        """Un appel en échec laisse son champ vide, pas toute l'instance."""
        d = InstanceData(info=info)
        iid = info["id"]
        if d.running:
            try:
                m = await self.client.metrics(iid)
                d.cpu_percent = _nombre(m.get("cpu_percent"))
                mem = _nombre(m.get("memory_bytes"))
                d.memory_bytes = int(mem) if mem is not None else None
            except NLaunchPanelError as err:
                _LOGGER.debug("mesures de %s : %s", iid, err)
        try:
            b = await self.client.backup(iid)
            d.backup_configured = bool(b.get("config"))
            for run in b.get("runs") or []:
                if isinstance(run, dict) and run.get("status") == "success" and run.get("finished_at"):
                    d.last_backup = dt_util.parse_datetime(str(run["finished_at"]))
                    break
        except NLaunchPanelError as err:
            _LOGGER.debug("sauvegardes de %s : %s", iid, err)
        if info.get("source_type") == "docker":
            try:
                img = await self.client.image_update(iid)
                if isinstance(img.get("state"), dict):
                    d.image = img["state"]
            except NLaunchPanelError as err:
                _LOGGER.debug("image de %s : %s", iid, err)
        return d

    async def _notifications(self) -> None:
        """Les nouvelles notifications de la cloche : un événement chacune."""
        try:
            items = await self.client.notifications()
        except NLaunchPanelConnectionError:
            return
        except NLaunchPanelError as err:
            # Un panel trop ancien n'ouvre pas la cloche aux jetons : les
            # capteurs marchent, les alertes attendent sa mise à jour.
            _LOGGER.debug("cloche : %s", err)
            return
        ids = {str(n["id"]) for n in items}
        if self._vues is None:
            self._vues = ids
            return
        persistantes = bool(self.config_entry.options.get(CONF_PERSISTENT, True))
        for n in reversed(items):  # les plus anciennes d'abord
            nid = str(n["id"])
            if nid in self._vues:
                continue
            self._vues.add(nid)
            donnees = {
                "id": nid,
                "kind": n.get("kind"),
                "severity": n.get("severity"),
                "title": n.get("title"),
                "body": n.get("body"),
                "link": n.get("link"),
                "created_at": n.get("created_at"),
            }
            self.hass.bus.async_fire(EVENT_NOTIFICATION, donnees)
            if persistantes:
                persistent_notification.async_create(
                    self.hass,
                    str(n.get("body") or ""),
                    title=f"NLaunchPanel — {n.get('title') or ''}",
                    notification_id=f"{DOMAIN}_{nid}",
                )
        # La mémoire reste bornée à ce que la cloche rend encore.
        self._vues = ids


def _nombre(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)
