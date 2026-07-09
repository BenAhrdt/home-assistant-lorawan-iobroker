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

ALLOWED_SERVICES: dict[str, set[str]] = {
    "button": {"press"},
    "cover": {"open_cover", "close_cover", "stop_cover", "set_cover_position"},
    "humidifier": {"turn_on", "turn_off", "set_humidity", "set_mode"},
    "input_boolean": {"turn_on", "turn_off"},
    "light": {"turn_on", "turn_off", "toggle"},
    "lock": {"lock", "unlock", "open"},
    "number": {"set_value"},
    "select": {"select_option"},
    "switch": {"turn_on", "turn_off", "toggle"},
}


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
        hass: HomeAssistant = request.app["hass"]
        return self.json(integration_payload(hass))


class LoRaWANControlView(HomeAssistantView):
    url = "/api/lorawan_iobroker/control"
    name = "api:lorawan_iobroker:control"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        data: dict[str, Any] = await request.json()
        entity_id = data.get("entity_id")
        service = data.get("service")
        service_data = data.get("service_data") or {}

        if not isinstance(entity_id, str) or "." not in entity_id:
            raise web.HTTPBadRequest(reason="entity_id is required")
        domain = entity_id.split(".", 1)[0]

        if service not in ALLOWED_SERVICES.get(domain, set()):
            raise web.HTTPBadRequest(reason="service is not allowed for this domain")

        await hass.services.async_call(
            domain,
            service,
            {"entity_id": entity_id, **service_data},
            blocking=False,
        )
        return self.json({"ok": True})


class LoRaWANOptionsView(HomeAssistantView):
    url = "/api/lorawan_iobroker/options"
    name = "api:lorawan_iobroker:options"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
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
