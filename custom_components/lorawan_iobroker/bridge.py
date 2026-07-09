from __future__ import annotations

import json
import logging
from datetime import timedelta
from time import time_ns
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.mqtt import device_trigger as mqtt_device_trigger
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers import trigger as trigger_helper
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_LABEL,
    CONF_PERIODIC_INTERVAL_MINUTES,
    CONF_SOURCE,
    CONF_SOURCE_DEVICE_ID,
    DEFAULT_LABEL,
    DEFAULT_PERIODIC_INTERVAL_MINUTES,
)
from .registry import (
    SourceConfig,
    _entry_labels,
    _is_mqtt_device,
    _label_names,
    _matches_source,
    normalize,
    topic_prefix_from_source,
)

EXCLUDED_ATTRIBUTES = {
    "friendly_name",
    "icon",
    "supported_color_modes",
    "effect_list",
    "device_class",
    "state_class",
    "unit_of_measurement",
}

LOGGER = logging.getLogger(__name__)


def data_to_iob_topic(source: SourceConfig) -> str:
    return f"{source.topic_prefix}/{source.topic_prefix.split('/')[-1]}_bridge_datatoiob/set"


def data_from_iob_topic(source: SourceConfig) -> str:
    return f"{source.topic_prefix}/{source.topic_prefix.split('/')[-1]}_bridge_datafromiob/state"


def source_from_entry(entry: ConfigEntry) -> SourceConfig:
    source = entry.data.get(CONF_SOURCE, entry.title)
    return SourceConfig(
        entry_id=entry.entry_id,
        title=entry.title,
        source=source,
        topic_prefix=topic_prefix_from_source(source),
        label=entry.data.get(CONF_LABEL, DEFAULT_LABEL),
        source_device_id=entry.data.get(CONF_SOURCE_DEVICE_ID),
        periodic_interval_minutes=int(
            entry.options.get(
                CONF_PERIODIC_INTERVAL_MINUTES,
                DEFAULT_PERIODIC_INTERVAL_MINUTES,
            )
        ),
    )


async def async_setup_bridge(hass: HomeAssistant, entry: ConfigEntry) -> list[Any]:
    source = source_from_entry(entry)
    unloaders: list[Any] = []
    LOGGER.warning(
        "Starting ioBroker LoRaWAN bridge for %s: publish=%s subscribe=%s label=%s",
        source.source,
        data_to_iob_topic(source),
        data_from_iob_topic(source),
        source.label,
    )

    @callback
    def state_changed(event: Event) -> None:
        new_state: State | None = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            return
        if not _state_matches_label(hass, source, new_state.entity_id):
            return
        hass.add_job(_publish_entities, hass, source, [new_state.entity_id], False)

    unloaders.append(hass.bus.async_listen(EVENT_STATE_CHANGED, state_changed))
    unloaders.append(
        async_track_time_interval(
            hass,
            lambda _now: hass.add_job(_publish_all_labeled, hass, source),
            timedelta(minutes=source.periodic_interval_minutes),
        )
    )
    unsubscribe = mqtt.async_subscribe(
        hass,
        data_from_iob_topic(source),
        lambda msg: _handle_command(hass, source, msg.payload),
    )
    if hasattr(unsubscribe, "__await__"):
        unsubscribe = await unsubscribe
    unloaders.append(unsubscribe)

    notification_unsubscribe = await _attach_notification_device_trigger(hass, source)
    if notification_unsubscribe is not None:
        unloaders.append(notification_unsubscribe)

    await _publish_device_ids(hass, source)
    await _publish_all_labeled(hass, source)
    LOGGER.warning("ioBroker LoRaWAN bridge started for %s", source.source)
    return unloaders


async def _attach_notification_device_trigger(hass: HomeAssistant, source: SourceConfig):
    source_devices = _notification_candidate_devices(hass, source)

    if not source_devices:
        LOGGER.warning("No MQTT bridge notification candidate device found for %s", source.source)
        return None

    for device in source_devices:
        triggers = await mqtt_device_trigger.async_get_triggers(hass, device.id)
        LOGGER.warning(
            "MQTT notification candidate for %s: device=%s name=%s score=%s triggers=%s",
            source.source,
            device.id,
            device.name_by_user or device.name,
            _notification_device_score(source, device),
            triggers,
        )
        trigger = next(
            (
                item
                for item in triggers
                if item.get("type") == "notification"
                and item.get("subtype") == "general"
            ),
            None,
        )
        if trigger is None:
            continue

        return await _initialize_notification_trigger(hass, source, device.id)

    LOGGER.warning(
        "No advertised MQTT notification/general trigger found for %s; trying direct attach on %s candidate device(s)",
        source.source,
        len(source_devices),
    )
    for device in source_devices:
        try:
            return await _initialize_notification_trigger(hass, source, device.id)
        except Exception as err:  # noqa: BLE001 - keep setup alive and try remaining candidates.
            LOGGER.warning(
                "Direct notification trigger attach failed for %s on device %s: %s",
                source.source,
                device.id,
                err,
            )

    LOGGER.warning("No MQTT notification/general device trigger could be attached for %s", source.source)
    return None


def _notification_candidate_devices(
    hass: HomeAssistant,
    source: SourceConfig,
) -> list[dr.DeviceEntry]:
    """Find the MQTT bridge device that owns the notification trigger.

    The device overview intentionally follows via_device_id so child devices are
    shown under a source. The notification trigger must be attached to the
    actual MQTT bridge/source device, not to one of its children.
    """
    device_registry = dr.async_get(hass)
    scored_devices: list[tuple[int, str, dr.DeviceEntry]] = []

    if source.source_device_id:
        source_device = device_registry.async_get(source.source_device_id)
        if source_device is not None and _is_mqtt_device(hass, source_device):
            scored_devices.append(
                (
                    1000,
                    (source_device.name_by_user or source_device.name or "").lower(),
                    source_device,
                )
            )
        elif source_device is not None:
            LOGGER.warning(
                "Configured notification source device for %s is not an MQTT device: %s (%s)",
                source.source,
                source_device.id,
                source_device.name_by_user or source_device.name,
            )
        else:
            LOGGER.warning(
                "Configured notification source device for %s no longer exists: %s",
                source.source,
                source.source_device_id,
            )

    for device in device_registry.devices.values():
        if not _is_mqtt_device(hass, device):
            continue
        if source.source_device_id and device.id == source.source_device_id:
            continue
        score = _notification_device_score(source, device)
        if score <= 0:
            continue
        scored_devices.append((score, (device.name_by_user or device.name or "").lower(), device))

    scored_devices.sort(key=lambda item: (-item[0], item[1]))
    return [device for _, _, device in scored_devices]


def _notification_device_score(source: SourceConfig, device: dr.DeviceEntry) -> int:
    source_norm = normalize(source.source)
    bridge_slug = source.topic_prefix.split("/")[-1]
    candidates = _notification_device_tokens(device)
    score = 0

    for value in candidates:
        token = normalize(value)
        if not token:
            continue
        if token == source_norm or token == bridge_slug:
            score = max(score, 100)
        elif token in {
            f"{source_norm}_bridge",
            f"{bridge_slug}_bridge",
            f"{source_norm}_bridge_datatoiob",
            f"{source_norm}_bridge_datafromiob",
        }:
            score = max(score, 95)
        elif source_norm and token.startswith(f"{source_norm}_bridge"):
            score = max(score, 90)
        elif source_norm and token.startswith(f"{source_norm}_"):
            score = max(score, 45)
        elif source_norm and source_norm in token:
            score = max(score, 20)

    # Prefer adapter/bridge-like devices over normal endpoint devices if both
    # happen to contain the source token in their identifiers.
    bridge_hint = any(
        hint in normalize(value)
        for value in candidates
        for hint in ("bridge", "adapter", "datatoiob", "datafromiob")
    )
    if bridge_hint and score:
        score += 10

    return score


def _notification_device_tokens(device: dr.DeviceEntry) -> list[str]:
    tokens = [
        device.id,
        device.name,
        device.name_by_user,
        device.manufacturer,
        device.model,
        device.sw_version,
        device.hw_version,
    ]
    for domain, identifier in device.identifiers:
        tokens.extend((domain, str(identifier), f"{domain}:{identifier}"))
    for connection_type, value in device.connections:
        tokens.extend((connection_type, str(value), f"{connection_type}:{value}"))
    return [str(token) for token in tokens if token]


async def _initialize_notification_trigger(
    hass: HomeAssistant,
    source: SourceConfig,
    device_id: str,
):
    config = {
        "platform": "device",
        "domain": "mqtt",
        "device_id": device_id,
        "type": "notification",
        "subtype": "general",
    }
    LOGGER.warning(
        "Initializing HA automation-style MQTT device notification trigger for %s on device %s",
        source.source,
        device_id,
    )

    async def action(variables: dict[str, Any], context=None) -> None:
        _handle_notification_trigger(hass, source, variables)

    unsubscribe = trigger_helper.async_initialize_triggers(
        hass,
        [config],
        action,
        "lorawan_iobroker",
        f"{source.source} notification",
        LOGGER.warning,
    )
    if hasattr(unsubscribe, "__await__"):
        unsubscribe = await unsubscribe
    return unsubscribe


def _handle_notification_trigger(hass: HomeAssistant, source: SourceConfig, variables: dict[str, Any]) -> None:
    trigger = variables.get("trigger", {})
    payload = trigger.get("payload", "")

    LOGGER.warning("Received ioBroker LoRaWAN notification for %s: %s", source.source, payload)
    persistent_notification.async_create(
        hass,
        str(payload),
        title="LoRaWAN Adapter",
        notification_id=f"lorawan_iobroker_{source.entry_id}_{time_ns()}",
    )
    hass.add_job(_publish_device_ids, hass, source)


def _state_matches_label(hass: HomeAssistant, source: SourceConfig, entity_id: str) -> bool:
    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get(entity_id)
    if entity is None:
        return False

    labels = {label.lower() for label in _label_names(hass, _entry_labels(entity))}
    if source.label.lower() in labels:
        return True

    if entity.device_id is None:
        return False

    device_registry = dr.async_get(hass)
    device = device_registry.async_get(entity.device_id)
    return bool(
        device
        and source.label.lower()
        in {label.lower() for label in _label_names(hass, _entry_labels(device))}
    )


def _all_labeled_entities(hass: HomeAssistant, source: SourceConfig) -> list[str]:
    return [state.entity_id for state in hass.states.async_all() if _state_matches_label(hass, source, state.entity_id)]


async def _publish_device_ids(hass: HomeAssistant, source: SourceConfig) -> None:
    device_registry = dr.async_get(hass)
    devices: dict[str, dict[str, str]] = {}
    for device in device_registry.devices.values():
        for domain, identifier in device.identifiers:
            if domain == "mqtt":
                devices[str(identifier)] = {"deviceId": device.id}

    await mqtt.async_publish(
        hass,
        data_to_iob_topic(source),
        json.dumps({"version": "1.1.1", "deviceIds": True, "devices": devices}, default=str),
        qos=0,
        retain=False,
    )
    LOGGER.warning("Published %s MQTT device ids to %s", len(devices), data_to_iob_topic(source))


async def _publish_all_labeled(hass: HomeAssistant, source: SourceConfig) -> None:
    await _publish_entities(hass, source, _all_labeled_entities(hass, source), discovery=True)


async def async_publish_periodic_message(hass: HomeAssistant, entry: ConfigEntry) -> None:
    source = source_from_entry(entry)
    await _publish_all_labeled(hass, source)


async def _publish_entities(hass: HomeAssistant, source: SourceConfig, entity_ids: list[str], discovery: bool) -> None:
    entities = {}
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if state is None:
            continue
        entities[entity_id] = _entity_payload(hass, state)

    if not entities and not discovery:
        return

    payload: dict[str, Any] = {"version": "1.1.1", "entities": entities}
    if discovery:
        payload["discovery"] = True

    await mqtt.async_publish(
        hass,
        data_to_iob_topic(source),
        json.dumps(payload, default=str),
        qos=0,
        retain=False,
    )
    LOGGER.warning(
        "Published %s entities to %s discovery=%s",
        len(entities),
        data_to_iob_topic(source),
        discovery,
    )


def _entity_payload(hass: HomeAssistant, state: State) -> dict[str, Any]:
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    entity = entity_registry.async_get(state.entity_id)
    device = device_registry.async_get(entity.device_id) if entity and entity.device_id else None
    domain = state.entity_id.split(".", 1)[0]

    return {
        "entity_id": state.entity_id,
        "domain": domain,
        "state": state.state,
        "available": state.state not in ("unknown", "unavailable"),
        "unique_id": entity.unique_id if entity else state.entity_id,
        "friendly_name": state.attributes.get("friendly_name", state.entity_id),
        "device_class": state.attributes.get("device_class"),
        "state_class": state.attributes.get("state_class"),
        "unit_of_measurement": state.attributes.get("unit_of_measurement"),
        "last_changed": state.last_changed.isoformat(),
        "last_updated": state.last_updated.isoformat(),
        "attributes": {
            key: value
            for key, value in state.attributes.items()
            if key not in EXCLUDED_ATTRIBUTES
        },
        "capabilities": _capabilities(domain, state),
        "device": {
            "id": device.id if device else None,
            "name": (device.name_by_user or device.name) if device else "unknown",
            "manufacturer": device.manufacturer if device else "unknown",
            "model": device.model if device else "unknown",
        },
    }


def _capabilities(domain: str, state: State) -> dict[str, Any]:
    capabilities: dict[str, Any] = {}
    if "supported_color_modes" in state.attributes:
        capabilities["supported_color_modes"] = state.attributes["supported_color_modes"]
    if "effect_list" in state.attributes:
        capabilities["effects"] = {
            "states": {str(index): effect for index, effect in enumerate(state.attributes["effect_list"])}
        }
    if domain == "cover" and "supported_features" in state.attributes:
        features = int(state.attributes.get("supported_features") or 0)
        commands = {}
        if features & 1:
            commands["1"] = "open"
        if features & 2:
            commands["2"] = "close"
        if features & 8:
            commands["8"] = "stop"
        if commands:
            capabilities["commands"] = {"states": commands}
    return capabilities


def _handle_command(hass: HomeAssistant, source: SourceConfig, payload: str) -> None:
    LOGGER.warning("Received ioBroker LoRaWAN command on %s: %s", data_from_iob_topic(source), payload)
    try:
        data = json.loads(payload)
    except (TypeError, ValueError) as err:
        LOGGER.warning("Ignoring invalid ioBroker LoRaWAN JSON payload: %s", err)
        return
    hass.add_job(_async_handle_command, hass, source, data)


async def _async_handle_command(hass: HomeAssistant, source: SourceConfig, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        LOGGER.warning("Ignoring ioBroker LoRaWAN command because payload is not an object: %s", payload)
        return

    if "entity_id" in payload:
        await _handle_attribute_command(hass, source, payload)
        return

    if not payload:
        LOGGER.warning("Ignoring empty ioBroker LoRaWAN command")
        return
    entity_id = next(iter(payload))
    await _handle_simple_command(hass, source, entity_id, payload[entity_id])


async def _handle_attribute_command(hass: HomeAssistant, source: SourceConfig, payload: dict[str, Any]) -> None:
    entity_id = payload.get("entity_id")
    attribute = payload.get("attribute")
    value = payload.get("value", payload.get("state"))
    if not isinstance(entity_id, str) or "." not in entity_id:
        LOGGER.warning("Ignoring command without valid entity_id: %s", payload)
        return
    if not _command_allowed_for_entity(hass, source, entity_id):
        LOGGER.warning(
            "Ignoring command for %s because it is neither labeled %s nor matched to %s",
            entity_id,
            source.label,
            source.source,
        )
        return
    domain = entity_id.split(".", 1)[0]

    if attribute in (None, "state", "value"):
        await _handle_simple_command(hass, source, entity_id, value)
    elif domain == "lock" and attribute == "command":
        service = {"lock": "lock", "unlock": "unlock", "open": "open"}.get(str(value).lower().strip())
        if service:
            await _call_service(hass, domain, service, {ATTR_ENTITY_ID: entity_id})
    elif domain == "climate" and attribute == "temperature":
        await _call_service(hass, domain, "set_temperature", {ATTR_ENTITY_ID: entity_id, "temperature": float(value)})
    elif domain == "humidifier" and attribute == "humidity":
        await _call_service(hass, domain, "set_humidity", {ATTR_ENTITY_ID: entity_id, "humidity": int(value)})
    elif domain == "humidifier" and attribute == "mode":
        await _call_service(hass, domain, "set_mode", {ATTR_ENTITY_ID: entity_id, "mode": value})
    elif domain == "light" and attribute:
        cast_value = int(value) if attribute in ("brightness", "transition") else value
        await _call_service(hass, domain, "turn_on", {ATTR_ENTITY_ID: entity_id, attribute: cast_value})
    elif domain == "cover" and attribute == "command":
        service = {"open": "open_cover", "close": "close_cover", "stop": "stop_cover"}.get(str(value).lower().strip())
        if service:
            await _call_service(hass, domain, service, {ATTR_ENTITY_ID: entity_id})
    elif domain == "cover" and attribute == "position":
        await _call_service(hass, domain, "set_cover_position", {ATTR_ENTITY_ID: entity_id, "position": int(value)})
    elif domain in ("number", "input_number") and attribute in ("value", "state"):
        await _call_service(hass, domain, "set_value", {ATTR_ENTITY_ID: entity_id, "value": float(value)})
    elif domain in ("text", "input_text") and attribute in ("value", "state"):
        await _call_service(hass, domain, "set_value", {ATTR_ENTITY_ID: entity_id, "value": str(value)})
    elif domain == "select" and attribute in ("option", "value", "state"):
        await _call_service(hass, domain, "select_option", {ATTR_ENTITY_ID: entity_id, "option": str(value)})
    else:
        LOGGER.warning("No command handler matched payload: %s", payload)


async def _handle_simple_command(hass: HomeAssistant, source: SourceConfig, entity_id: str, value: Any) -> None:
    if "." not in entity_id:
        LOGGER.warning("Ignoring simple command with invalid entity_id: %s", entity_id)
        return
    if not _command_allowed_for_entity(hass, source, entity_id):
        LOGGER.warning(
            "Ignoring simple command for %s because it is neither labeled %s nor matched to %s",
            entity_id,
            source.label,
            source.source,
        )
        return
    domain = entity_id.split(".", 1)[0]
    truthy = _truthy(value)

    if domain == "button":
        await _call_service(hass, domain, "press", {ATTR_ENTITY_ID: entity_id})
    elif domain in ("switch", "light", "input_boolean", "humidifier"):
        await _call_service(hass, domain, "turn_on" if truthy else "turn_off", {ATTR_ENTITY_ID: entity_id})
    elif domain == "cover":
        if value in ("open", "on", True, "1", 1):
            service = "open_cover"
        elif value in ("stop", "8", 8):
            service = "stop_cover"
        else:
            service = "close_cover"
        await _call_service(hass, domain, service, {ATTR_ENTITY_ID: entity_id})
    elif domain == "lock":
        await _call_service(hass, domain, "lock" if value in ("lock", "on", True, "1", 1) else "unlock", {ATTR_ENTITY_ID: entity_id})
    elif domain in ("number", "input_number"):
        await _call_service(hass, domain, "set_value", {ATTR_ENTITY_ID: entity_id, "value": float(value)})
    elif domain in ("text", "input_text"):
        await _call_service(hass, domain, "set_value", {ATTR_ENTITY_ID: entity_id, "value": str(value)})
    elif domain == "select":
        await _call_service(hass, domain, "select_option", {ATTR_ENTITY_ID: entity_id, "option": str(value)})
    else:
        LOGGER.warning("No simple command handler for domain %s entity %s value %s", domain, entity_id, value)


async def _call_service(hass: HomeAssistant, domain: str, service: str, data: dict[str, Any]) -> None:
    LOGGER.warning("Calling HA service %s.%s with %s", domain, service, data)
    await hass.services.async_call(domain, service, data, blocking=False)


def _truthy(value: Any) -> bool:
    return value is True or str(value).lower().strip() in ("true", "on", "1", "open", "lock")


def _command_allowed_for_entity(hass: HomeAssistant, source: SourceConfig, entity_id: str) -> bool:
    entity_registry = er.async_get(hass)
    entity = entity_registry.async_get(entity_id)
    if entity is None:
        return False

    if _state_matches_label(hass, source, entity_id):
        return True

    if entity.device_id is None:
        return False

    device_registry = dr.async_get(hass)
    device = device_registry.async_get(entity.device_id)
    if device is None:
        return False

    from .registry import _matches_source

    return _matches_source(source, device, device_registry)
