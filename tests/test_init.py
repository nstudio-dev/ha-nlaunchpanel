"""Les entités, les actions, les appareils qui vont et viennent, la cloche."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nlaunchpanel.const import DOMAIN, EVENT_NOTIFICATION

from .conftest import API, JELLYFIN, SITE, TOKEN, faux_panel


async def _installer(hass: HomeAssistant, entree: MockConfigEntry) -> None:
    entree.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entree.entry_id)
    await hass.async_block_till_done()


async def _tour(hass: HomeAssistant) -> None:
    """Un tour du coordinateur. Home Assistant le lance en tâche de fond :
    il faut l'attendre explicitement."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done(wait_background_tasks=True)


def _entite(hass: HomeAssistant, instance: str, cle: str) -> str:
    eid = er.async_get(hass).async_get_entity_id(_domaine(cle), DOMAIN, f"{instance}_{cle}")
    assert eid, f"{instance}_{cle}"
    return eid


def _domaine(cle: str) -> str:
    return {"restart": "button", "backup": "button", "deploy": "button", "power": "switch", "image": "update"}.get(cle, "sensor")


def _appels(aioclient_mock: AiohttpClientMocker, methode: str, morceau: str) -> list[Any]:
    return [c for c in aioclient_mock.mock_calls if c[0] == methode and morceau in str(c[1])]


async def test_les_capteurs(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entree: MockConfigEntry) -> None:
    faux_panel(aioclient_mock)
    await _installer(hass, entree)
    assert entree.state is ConfigEntryState.LOADED

    assert hass.states.get(_entite(hass, "inst-jelly", "status")).state == "running"
    assert float(hass.states.get(_entite(hass, "inst-jelly", "cpu")).state) == pytest.approx(3.25)
    assert float(hass.states.get(_entite(hass, "inst-jelly", "memory")).state) == pytest.approx(612, abs=1)
    # La dernière sauvegarde RÉUSSIE, pas la dernière tout court.
    assert hass.states.get(_entite(hass, "inst-jelly", "last_backup")).state == "2026-10-28T04:00:00+00:00"
    # Une instance arrêtée : pas de mesures demandées, capteurs inconnus.
    assert hass.states.get(_entite(hass, "inst-site", "status")).state == "stopped"
    assert hass.states.get(_entite(hass, "inst-site", "cpu")).state == "unknown"
    assert not _appels(aioclient_mock, "GET", "inst-site/metrics")

    # L'image : une nouvelle construction du même tag.
    img = hass.states.get(_entite(hass, "inst-jelly", "image"))
    assert img.state == "on"
    assert img.attributes["installed_version"] == "latest (111111111111)"
    assert img.attributes["latest_version"] == "latest (222222222222)"
    # Une instance Git n'a pas d'image.
    assert er.async_get(hass).async_get_entity_id("update", DOMAIN, "inst-site_image") is None

    # Un appareil par instance, avec son lien vers la fiche du panel.
    appareil = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "inst-jelly")})
    assert appareil.name == "jellyfin"
    assert appareil.configuration_url == "http://panel.test/instances/inst-jelly"
    # Le jeton part en en-tête, jamais dans une adresse.
    assert all(TOKEN not in str(c[1]) for c in aioclient_mock.mock_calls)


async def test_les_actions(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entree: MockConfigEntry) -> None:
    faux_panel(aioclient_mock)
    await _installer(hass, entree)
    await hass.services.async_call("button", "press", {"entity_id": _entite(hass, "inst-jelly", "restart")}, blocking=True)
    assert _appels(aioclient_mock, "POST", "inst-jelly/restart")
    await hass.services.async_call("button", "press", {"entity_id": _entite(hass, "inst-jelly", "backup")}, blocking=True)
    assert _appels(aioclient_mock, "POST", "inst-jelly/backup/run")
    await hass.services.async_call("button", "press", {"entity_id": _entite(hass, "inst-jelly", "deploy")}, blocking=True)
    assert _appels(aioclient_mock, "POST", "inst-jelly/deploy")
    await hass.services.async_call("switch", "turn_off", {"entity_id": _entite(hass, "inst-jelly", "power")}, blocking=True)
    assert _appels(aioclient_mock, "POST", "inst-jelly/stop")
    await hass.services.async_call("switch", "turn_on", {"entity_id": _entite(hass, "inst-site", "power")}, blocking=True)
    assert _appels(aioclient_mock, "POST", "inst-site/start")
    await hass.services.async_call("update", "install", {"entity_id": _entite(hass, "inst-jelly", "image")}, blocking=True)
    apply = _appels(aioclient_mock, "POST", "inst-jelly/image-update/apply")
    assert apply and apply[0][2] == {"kind": "build"}
    assert hass.states.get(_entite(hass, "inst-jelly", "power")).state == "on"


async def test_un_refus_du_panel(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entree: MockConfigEntry) -> None:
    faux_panel(aioclient_mock)
    await _installer(hass, entree)
    # Le premier enregistré l'emporte : le refus, puis le reste du panel.
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{API}/instances/inst-jelly/restart", json={"error": "forbidden", "message": "access denied"}, status=403)
    faux_panel(aioclient_mock, effacer=False)
    with pytest.raises(HomeAssistantError, match="access denied"):
        await hass.services.async_call("button", "press", {"entity_id": _entite(hass, "inst-jelly", "restart")}, blocking=True)


async def test_jeton_en_lecture(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entree: MockConfigEntry) -> None:
    faux_panel(aioclient_mock, ecriture=False)
    await _installer(hass, entree)
    registre = er.async_get(hass)
    # Les capteurs, pas les boutons ni l'interrupteur ; la mise à jour sans « installer ».
    assert hass.states.get(_entite(hass, "inst-jelly", "status")).state == "running"
    assert registre.async_get_entity_id("button", DOMAIN, "inst-jelly_restart") is None
    assert registre.async_get_entity_id("switch", DOMAIN, "inst-jelly_power") is None
    assert hass.states.get(_entite(hass, "inst-jelly", "image")).attributes["supported_features"] == 0


async def test_les_instances_vont_et_viennent(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entree: MockConfigEntry) -> None:
    faux_panel(aioclient_mock)
    await _installer(hass, entree)
    nouvelle = {"id": "inst-mqtt", "name": "mosquitto", "status": "running", "source_type": "docker", "docker_image": "eclipse-mosquitto:2"}
    faux_panel(aioclient_mock, [JELLYFIN, nouvelle])
    await _tour(hass)
    coord = entree.runtime_data.coordinator
    assert "inst-mqtt" in (coord.data or {}), f"données {list(coord.data or {})} ; appels {[str(c[1]) for c in aioclient_mock.mock_calls][:6]}"
    appareils = dr.async_get(hass)
    # La nouvelle arrive, la supprimée part.
    assert hass.states.get(_entite(hass, "inst-mqtt", "status")).state == "running"
    assert appareils.async_get_device(identifiers={(DOMAIN, "inst-site")}) is None
    assert appareils.async_get_device(identifiers={(DOMAIN, "inst-jelly")}) is not None


async def test_panel_injoignable_puis_jeton_refuse(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entree: MockConfigEntry) -> None:
    faux_panel(aioclient_mock)
    await _installer(hass, entree)
    faux_panel(aioclient_mock, statut_instances=502)
    await _tour(hass)
    assert hass.states.get(_entite(hass, "inst-jelly", "status")).state == "unavailable"
    faux_panel(aioclient_mock, statut_instances=401)
    await _tour(hass)
    # Le jeton refusé : Home Assistant en demande un nouveau.
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_la_cloche(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entree: MockConfigEntry) -> None:
    ancienne = {"id": "n1", "kind": "backup", "severity": "info", "title": "Ancienne", "body": "déjà là", "created_at": "2026-10-28T01:00:00Z"}
    faux_panel(aioclient_mock, notifications=[ancienne])
    evenements = async_capture_events(hass, EVENT_NOTIFICATION)
    persistantes = patch("custom_components.nlaunchpanel.coordinator.persistent_notification.async_create")
    creer = persistantes.start()
    await _installer(hass, entree)
    # Le premier tour ne rejoue pas l'historique.
    assert evenements == []

    nouvelle = {"id": "n2", "kind": "instance.crashed", "severity": "critical", "title": "jellyfin est tombé", "body": "Redémarrage en boucle", "link": "/instances/inst-jelly", "created_at": "2026-10-28T20:00:00Z"}
    faux_panel(aioclient_mock, notifications=[nouvelle, ancienne])
    await _tour(hass)
    assert len(evenements) == 1, f"vues {entree.runtime_data.coordinator._vues} ; appels {[str(c[1]) for c in aioclient_mock.mock_calls]}"
    assert evenements[0].data["title"] == "jellyfin est tombé"
    assert evenements[0].data["severity"] == "critical"
    # La notification persistante (option cochée), une seule.
    assert creer.call_count == 1
    assert creer.call_args.kwargs["title"] == "NLaunchPanel — jellyfin est tombé"
    assert creer.call_args.kwargs["notification_id"] == "nlaunchpanel_n2"

    # Le tour suivant : rien de nouveau, rien d'émis.
    await _tour(hass)
    assert len(evenements) == 1
    assert creer.call_count == 1
    persistantes.stop()


async def test_sans_notification_persistante(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    entree = MockConfigEntry(domain=DOMAIN, unique_id="http://panel.test", data={"url": "http://panel.test", "token": TOKEN},
                             options={"persistent_notifications": False})
    faux_panel(aioclient_mock)
    evenements = async_capture_events(hass, EVENT_NOTIFICATION)
    with patch("custom_components.nlaunchpanel.coordinator.persistent_notification.async_create") as creer:
        await _installer(hass, entree)
        faux_panel(aioclient_mock, notifications=[{"id": "n9", "title": "x", "body": "y"}])
        await _tour(hass)
    # L'événement part toujours ; la notification persistante, non.
    assert len(evenements) == 1
    assert creer.call_count == 0


async def test_dechargement(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entree: MockConfigEntry) -> None:
    faux_panel(aioclient_mock)
    await _installer(hass, entree)
    assert await hass.config_entries.async_unload(entree.entry_id)
    assert entree.state is ConfigEntryState.NOT_LOADED
