"""Le client de l'API publique de NLaunchPanel (/api/v1, jeton « nlp_… »)."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=20)

# Une instance qui n'existe pas : y demander un redémarrage dit seulement si
# le jeton peut écrire (refusé avant même de chercher l'instance s'il est en
# lecture seule), sans rien toucher.
PROBE_INSTANCE = "nlaunchpanel-probe-does-not-exist"


class NLaunchPanelError(Exception):
    """Le panel n'a pas répondu comme attendu."""


class NLaunchPanelConnectionError(NLaunchPanelError):
    """Le panel est injoignable."""


class NLaunchPanelAuthError(NLaunchPanelError):
    """Le jeton est refusé (inconnu, expiré, propriétaire retiré)."""


class NLaunchPanelReadOnlyError(NLaunchPanelError):
    """Le jeton est en lecture seule."""


class NLaunchPanelClient:
    """Un panel, un jeton."""

    def __init__(self, session: aiohttp.ClientSession, url: str, token: str) -> None:
        self._session = session
        self.url = url.rstrip("/")
        self._token = token

    async def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self.url}/api/v1{path}",
                json=body,
                headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
                timeout=TIMEOUT,
            ) as resp:
                # Le corps est lu en JSON quel que soit l'en-tête : un mandataire
                # devant le panel peut le changer, le contenu reste le même.
                data: Any = None
                try:
                    data = await resp.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError):
                    data = None
                if resp.status == 401:
                    raise NLaunchPanelAuthError(_message(data, resp.status))
                if resp.status == 403 and isinstance(data, dict) and data.get("error") == "read_only_token":
                    raise NLaunchPanelReadOnlyError(_message(data, resp.status))
                if resp.status >= 400:
                    raise NLaunchPanelError(_message(data, resp.status))
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise NLaunchPanelConnectionError(str(err) or type(err).__name__) from err

    async def instances(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/instances?limit=200")
        items = data.get("items") if isinstance(data, dict) else None
        return [i for i in items or [] if isinstance(i, dict) and i.get("id")]

    async def metrics(self, instance_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/instances/{instance_id}/metrics") or {}

    async def backup(self, instance_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/instances/{instance_id}/backup") or {}

    async def image_update(self, instance_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/instances/{instance_id}/image-update") or {}

    async def action(self, instance_id: str, action: str) -> None:
        """start, stop ou restart."""
        if action not in ("start", "stop", "restart"):
            raise ValueError(action)
        await self._request("POST", f"/instances/{instance_id}/{action}", {})

    async def deploy(self, instance_id: str) -> None:
        await self._request("POST", f"/instances/{instance_id}/deploy", {})

    async def run_backup(self, instance_id: str) -> None:
        await self._request("POST", f"/instances/{instance_id}/backup/run", {})

    async def apply_image_update(self, instance_id: str, kind: str) -> None:
        """kind : « build » (nouvelle construction du même tag) ou « version »."""
        if kind not in ("build", "version"):
            raise ValueError(kind)
        await self._request("POST", f"/instances/{instance_id}/image-update/apply", {"kind": kind})

    async def notifications(self, limit: int = 20) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/inapp-notifications?limit={limit}")
        items = data.get("items") if isinstance(data, dict) else None
        return [n for n in items or [] if isinstance(n, dict) and n.get("id")]

    async def can_write(self) -> bool:
        """Le jeton peut-il agir ? Sonde sans effet (voir PROBE_INSTANCE)."""
        try:
            await self._request("POST", f"/instances/{PROBE_INSTANCE}/restart", {})
        except NLaunchPanelReadOnlyError:
            return False
        except NLaunchPanelAuthError:
            raise
        except NLaunchPanelConnectionError:
            raise
        except NLaunchPanelError:
            # 404 (instance inconnue) ou 403 d'un rôle : le jeton, lui, écrit.
            return True
        return True


def _message(data: Any, status: int) -> str:
    if isinstance(data, dict):
        return str(data.get("message") or data.get("error") or f"HTTP {status}")
    return f"HTTP {status}"
