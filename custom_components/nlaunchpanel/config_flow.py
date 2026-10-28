"""La configuration : l'adresse du panel et un jeton d'API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NLaunchPanelAuthError, NLaunchPanelClient, NLaunchPanelConnectionError, NLaunchPanelError
from .const import CONF_PERSISTENT, CONF_TOKEN, CONF_URL, DOMAIN


def _normaliser(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


class NLaunchPanelConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _verifier(self, url: str, token: str) -> str | None:
        """Rend la clé d'erreur, ou None si le panel accepte le jeton."""
        client = NLaunchPanelClient(async_get_clientsession(self.hass), url, token)
        try:
            await client.instances()
        except NLaunchPanelAuthError:
            return "invalid_auth"
        except NLaunchPanelConnectionError:
            return "cannot_connect"
        except NLaunchPanelError:
            return "unknown"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        erreurs: dict[str, str] = {}
        if user_input is not None:
            url = _normaliser(user_input[CONF_URL])
            token = user_input[CONF_TOKEN].strip()
            if not token.startswith("nlp_"):
                erreurs[CONF_TOKEN] = "invalid_token_format"
            elif (e := await self._verifier(url, token)) is not None:
                erreurs["base"] = e
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=url.split("://", 1)[1],
                    data={CONF_URL: url, CONF_TOKEN: token},
                    options={CONF_PERSISTENT: user_input.get(CONF_PERSISTENT, True)},
                )
        schema = vol.Schema({
            vol.Required(CONF_URL, default=(user_input or {}).get(CONF_URL, "")): str,
            vol.Required(CONF_TOKEN): str,
            vol.Optional(CONF_PERSISTENT, default=True): bool,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=erreurs)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Le jeton a été refusé (expiré, révoqué) : en coller un nouveau."""
        erreurs: dict[str, str] = {}
        entree = self._get_reauth_entry()
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            if not token.startswith("nlp_"):
                erreurs[CONF_TOKEN] = "invalid_token_format"
            elif (e := await self._verifier(entree.data[CONF_URL], token)) is not None:
                erreurs["base"] = e
            else:
                return self.async_update_reload_and_abort(entree, data_updates={CONF_TOKEN: token})
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}), errors=erreurs,
            description_placeholders={"url": entree.data[CONF_URL]},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        return NLaunchPanelOptionsFlow()


class NLaunchPanelOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        actuel = self.config_entry.options.get(CONF_PERSISTENT, True)
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema({vol.Optional(CONF_PERSISTENT, default=actuel): bool}),
        )
