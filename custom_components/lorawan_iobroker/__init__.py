from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, NAME, PANEL_JS_URL, PANEL_URL
from .bridge import async_setup_bridge
from .http import (
    LoRaWANControlView,
    LoRaWANDataView,
    LoRaWANOptionsView,
    LoRaWANPanelJsView,
    LoRaWANPublishView,
)

PLATFORMS: list[str] = []
_REGISTERED = "registered"
LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    await _async_register_once(hass)
    unloaders = await async_setup_bridge(hass, entry)
    unloaders.append(entry.add_update_listener(_async_options_updated))
    hass.data[DOMAIN][entry.entry_id] = unloaders
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaders = hass.data.get(DOMAIN, {}).pop(entry.entry_id, [])
    for unload in unloaders:
        unload()
    if not hass.config_entries.async_entries(DOMAIN):
        if hasattr(frontend, "async_remove_panel"):
            frontend.async_remove_panel(hass, PANEL_URL)
        hass.data.get(DOMAIN, {}).pop(_REGISTERED, None)
    return True


async def _async_register_once(hass: HomeAssistant) -> None:
    if hass.data[DOMAIN].get(_REGISTERED):
        return
    hass.data[DOMAIN][_REGISTERED] = True

    panel_path = Path(__file__).with_name("panel.js")
    panel_js = await hass.async_add_executor_job(panel_path.read_text)

    hass.http.register_view(LoRaWANPanelJsView(panel_js))
    hass.http.register_view(LoRaWANDataView())
    hass.http.register_view(LoRaWANControlView())
    hass.http.register_view(LoRaWANOptionsView())
    hass.http.register_view(LoRaWANPublishView())

    try:
        frontend.async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title=NAME,
            sidebar_icon="mdi:radio-tower",
            frontend_url_path=PANEL_URL,
            config={
                "_panel_custom": {
                    "name": "lorawan-iobroker-panel",
                    "js_url": PANEL_JS_URL,
                    "embed_iframe": False,
                    "trust_external": False,
                }
            },
            require_admin=False,
        )
    except ValueError as err:
        if "Overwriting panel" not in str(err):
            hass.data[DOMAIN].pop(_REGISTERED, None)
            raise
        LOGGER.warning("Sidebar panel %s already exists, reusing it", PANEL_URL)
