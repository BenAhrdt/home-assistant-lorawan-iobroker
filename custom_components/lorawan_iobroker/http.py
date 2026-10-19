from __future__ import annotations

from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .bridge import async_publish_periodic_message
from .const import (
    CONF_PERIODIC_INTERVAL_MINUTES,
    DOMAIN,
)
from .registry import integration_payload


class LoRaWANPanelJsView(HomeAssistantView):
    url = "/lorawan_iobroker/panel.js"
    name = "lorawan_iobroker:panel"
    requires_auth = False

    def __init__(self, js: str) -> None:
        self._js = js

    async def get(self, request: web.Request) -> web.Response:
        return web.Response(text=self._js, content_type="application/javascript")


class LoRaWANDataView(HomeAssistantView):
    url = "/api/lorawan_iobroker/data"
    name = "api:lorawan_iobroker:data"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        _require_admin(request)
        hass: HomeAssistant = request.app["hass"]
        return self.json(integration_payload(hass))


class LoRaWANOptionsView(HomeAssistantView):
    url = "/api/lorawan_iobroker/options"
    name = "api:lorawan_iobroker:options"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        _require_admin(request)
        data: dict[str, Any] = await request.json()
        entry = _entry_from_request(hass, data)
        interval = data.get(CONF_PERIODIC_INTERVAL_MINUTES)

        try:
            interval = int(interval)
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(reason="periodic_interval_minutes must be a number") from None
        if interval < 1 or interval > 1440:
            raise web.HTTPBadRequest(reason="periodic_interval_minutes must be between 1 and 1440")

        options = dict(entry.options)
        options[CONF_PERIODIC_INTERVAL_MINUTES] = interval
        hass.config_entries.async_update_entry(entry, options=options)
        return self.json(
            {
                "ok": True,
                CONF_PERIODIC_INTERVAL_MINUTES: interval,
            }
        )


class LoRaWANPublishView(HomeAssistantView):
    url = "/api/lorawan_iobroker/publish"
    name = "api:lorawan_iobroker:publish"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        _require_admin(request)
        data: dict[str, Any] = await request.json()
        entry = _entry_from_request(hass, data)
        await async_publish_periodic_message(hass, entry)
        return self.json({"ok": True})


def _entry_from_request(hass: HomeAssistant, data: dict[str, Any]):
    entry_id = data.get("entry_id")
    if not isinstance(entry_id, str):
        raise web.HTTPBadRequest(reason="entry_id is required")

    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise web.HTTPNotFound(reason="entry not found")
    return entry


def _require_admin(request: web.Request) -> None:
    user = request.get("hass_user")
    if user is None or not user.is_admin:
        raise web.HTTPForbidden(reason="Administrator access required")
