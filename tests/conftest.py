"""Les fixtures communes : un faux panel derrière aioclient_mock."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nlaunchpanel.const import CONF_PERSISTENT, CONF_TOKEN, CONF_URL, DOMAIN

URL = "http://panel.test"
API = f"{URL}/api/v1"
TOKEN = "nlp_" + "a" * 64
PROBE = f"{API}/instances/nlaunchpanel-probe-does-not-exist/restart"

JELLYFIN = {"id": "inst-jelly", "name": "jellyfin", "status": "running", "source_type": "docker", "docker_image": "jellyfin/jellyfin:latest"}
SITE = {"id": "inst-site", "name": "site", "status": "stopped", "source_type": "git"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Charger custom_components/ dans chaque test."""


def faux_panel(
    aioclient_mock: AiohttpClientMocker,
    instances: list[dict[str, Any]] | None = None,
    *,
    ecriture: bool = True,
    notifications: list[dict[str, Any]] | None = None,
    statut_instances: int = 200,
    effacer: bool = True,
) -> None:
    """Le panel tel que l'intégration l'interroge."""
    if effacer:
        aioclient_mock.clear_requests()
    instances = [JELLYFIN, SITE] if instances is None else instances
    aioclient_mock.get(f"{API}/instances?limit=200", json={"items": instances}, status=statut_instances)
    if ecriture:
        aioclient_mock.post(PROBE, json={"error": "not_found"}, status=404)
    else:
        aioclient_mock.post(PROBE, json={"error": "read_only_token"}, status=403)
    for i in instances:
        iid = i["id"]
        aioclient_mock.get(f"{API}/instances/{iid}/metrics", json={"cpu_percent": 3.25, "memory_bytes": 612 * 1024 * 1024})
        aioclient_mock.get(
            f"{API}/instances/{iid}/backup",
            json={"config": {"enabled": True}, "runs": [
                {"status": "failed", "finished_at": "2026-10-28T10:00:00Z"},
                {"status": "success", "finished_at": "2026-10-28T04:00:00Z"},
            ]},
        )
        aioclient_mock.get(
            f"{API}/instances/{iid}/image-update",
            json={"docker": True, "can_manage": True, "state": {
                "image": "jellyfin/jellyfin:latest", "current_digest": "sha256:" + "1" * 64,
                "registry_digest": "sha256:" + "2" * 64, "same_major": "", "apply": {"status": ""},
            }},
        )
        for action in ("start", "stop", "restart", "deploy", "backup/run", "image-update/apply"):
            aioclient_mock.post(f"{API}/instances/{iid}/{action}", json={"status": "accepted"})
    aioclient_mock.get(f"{API}/inapp-notifications?limit=20", json={"items": notifications or []})


@pytest.fixture
def entree() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN, unique_id=URL, title="panel.test",
        data={CONF_URL: URL, CONF_TOKEN: TOKEN}, options={CONF_PERSISTENT: True},
    )
