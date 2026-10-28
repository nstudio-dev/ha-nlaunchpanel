"""La configuration : adresse, jeton, erreurs, nouveau jeton."""

from __future__ import annotations

import aiohttp

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nlaunchpanel.const import CONF_PERSISTENT, CONF_TOKEN, CONF_URL, DOMAIN

from .conftest import API, TOKEN, URL, faux_panel


async def _demarrer(hass: HomeAssistant) -> str:
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.FORM
    return r["flow_id"]


async def test_un_panel_et_un_jeton(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    faux_panel(aioclient_mock)
    flow = await _demarrer(hass)
    # Sans schéma : https par défaut ; la barre finale disparaît.
    aioclient_mock.get("https://panel.test/api/v1/instances?limit=200", json={"items": []})
    r = await hass.config_entries.flow.async_configure(flow, {CONF_URL: "panel.test/", CONF_TOKEN: f" {TOKEN} ", CONF_PERSISTENT: False})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"] == {CONF_URL: "https://panel.test", CONF_TOKEN: TOKEN}
    assert r["options"] == {CONF_PERSISTENT: False}
    assert r["title"] == "panel.test"
    # Le jeton n'est jamais dans l'adresse : il part en en-tête.
    appel = next(c for c in aioclient_mock.mock_calls if str(c[1]).startswith("https://panel.test"))
    assert TOKEN not in str(appel[1])


async def test_les_erreurs(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    flow = await _demarrer(hass)
    r = await hass.config_entries.flow.async_configure(flow, {CONF_URL: URL, CONF_TOKEN: "pas-un-jeton"})
    assert r["errors"] == {CONF_TOKEN: "invalid_token_format"}

    aioclient_mock.get(f"{API}/instances?limit=200", json={"error": "unauthorized"}, status=401)
    r = await hass.config_entries.flow.async_configure(flow, {CONF_URL: URL, CONF_TOKEN: TOKEN})
    assert r["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/instances?limit=200", exc=aiohttp.ClientConnectionError())
    r = await hass.config_entries.flow.async_configure(flow, {CONF_URL: URL, CONF_TOKEN: TOKEN})
    assert r["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/instances?limit=200", json={"error": "db_error"}, status=500)
    r = await hass.config_entries.flow.async_configure(flow, {CONF_URL: URL, CONF_TOKEN: TOKEN})
    assert r["errors"] == {"base": "unknown"}


async def test_un_panel_une_fois(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entree: MockConfigEntry) -> None:
    entree.add_to_hass(hass)
    faux_panel(aioclient_mock)
    flow = await _demarrer(hass)
    r = await hass.config_entries.flow.async_configure(flow, {CONF_URL: URL, CONF_TOKEN: TOKEN})
    assert r["type"] is FlowResultType.ABORT
    assert r["reason"] == "already_configured"


async def test_un_nouveau_jeton(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entree: MockConfigEntry) -> None:
    entree.add_to_hass(hass)
    faux_panel(aioclient_mock)
    r = await entree.start_reauth_flow(hass)
    assert r["step_id"] == "reauth_confirm"
    nouveau = "nlp_" + "b" * 64
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_TOKEN: nouveau})
    assert r["type"] is FlowResultType.ABORT
    assert r["reason"] == "reauth_successful"
    assert entree.data[CONF_TOKEN] == nouveau


async def test_les_options(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entree: MockConfigEntry) -> None:
    entree.add_to_hass(hass)
    faux_panel(aioclient_mock)
    await hass.config_entries.async_setup(entree.entry_id)
    await hass.async_block_till_done()
    r = await hass.config_entries.options.async_init(entree.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {CONF_PERSISTENT: False})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert entree.options == {CONF_PERSISTENT: False}
