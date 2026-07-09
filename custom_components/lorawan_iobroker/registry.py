from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_LABEL,
    CONF_PERIODIC_INTERVAL_MINUTES,
    CONF_SOURCE,
    CONF_SOURCE_DEVICE_ID,
    DEFAULT_LABEL,
    DEFAULT_PERIODIC_INTERVAL_MINUTES,
    DOMAIN,
)


def normalize(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def token_matches(haystack: str | None, needle: str) -> bool:
    if not haystack:
        return False
    normalized = normalize(haystack)
    needle_norm = normalize(needle)
    return needle_norm in normalized or needle_norm.replace("_", "") in normalized.replace("_", "")


@dataclass(slots=True)
class SourceConfig:
    entry_id: str
    title: str
    source: str
    topic_prefix: str
    label: str
    source_device_id: str | None = None
    periodic_interval_minutes: int = DEFAULT_PERIODIC_INTERVAL_MINUTES


def source_configs(hass: HomeAssistant) -> list[SourceConfig]:
    configs: list[SourceConfig] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        configs.append(
            SourceConfig(
                entry_id=entry.entry_id,
                title=entry.title,
                source=entry.data.get(CONF_SOURCE, entry.title),
                topic_prefix=topic_prefix_from_source(entry.data.get(CONF_SOURCE, entry.title)),
                label=entry.data.get(CONF_LABEL, DEFAULT_LABEL),
                source_device_id=entry.data.get(CONF_SOURCE_DEVICE_ID),
                periodic_interval_minutes=int(
                    entry.options.get(
                        CONF_PERIODIC_INTERVAL_MINUTES,
                        DEFAULT_PERIODIC_INTERVAL_MINUTES,
                    )
                ),
            )
        )
    return configs


def topic_prefix_from_source(source: str) -> str:
    normalized = normalize(source)
    return f"{normalized}/{normalized}" if normalized else ""


def _entry_domain(hass: HomeAssistant, entry_id: str) -> str | None:
    entry = hass.config_entries.async_get_entry(entry_id)
    return entry.domain if entry else None


def _label_names(hass: HomeAssistant, label_ids: set[str]) -> set[str]:
    try:
        from homeassistant.helpers import label_registry as lr
    except ImportError:
        return label_ids

    label_registry = lr.async_get(hass)
    names = set(label_ids)
    for label_id in label_ids:
        label = label_registry.async_get_label(label_id)
        if label is not None:
            names.add(label.name)
    return names


def _entry_labels(entry: Any) -> set[str]:
    labels = getattr(entry, "labels", None) or []
    return {str(label) for label in labels}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]
    return str(value)


def _registry_item_values(item: tuple[Any, ...]) -> list[str]:
    parts = [str(part) for part in item if part is not None]
    if not parts:
        return []
    if len(parts) == 1:
        return parts

    domain = parts[0]
    identifier = ":".join(parts[1:])
    values = [f"{domain}:{identifier}", identifier]
    if len(parts) > 2:
        values.append(parts[-1])
    return values


def _device_identifiers(device: dr.DeviceEntry) -> list[str]:
    values: list[str] = []
    for identifier in device.identifiers:
        values.extend(_registry_item_values(identifier))
    return values


def _device_connections(device: dr.DeviceEntry) -> list[str]:
    values: list[str] = []
    for connection in device.connections:
        values.extend(_registry_item_values(connection))
    return values


def _is_mqtt_device(hass: HomeAssistant, device: dr.DeviceEntry) -> bool:
    return any(_entry_domain(hass, entry_id) == "mqtt" for entry_id in device.config_entries)


def _device_integrations(hass: HomeAssistant, device: dr.DeviceEntry) -> list[str]:
    return sorted(
        {
            domain
            for entry_id in device.config_entries
            if (domain := _entry_domain(hass, entry_id)) is not None
        }
    )


def _device_matches_source_name(source_name: str, device: dr.DeviceEntry) -> bool:
    searchable = [
        device.name,
        device.name_by_user,
        device.manufacturer,
        device.model,
        *_device_identifiers(device),
        *_device_connections(device),
    ]
    return any(token_matches(value, source_name) for value in searchable)


def _via_device_matches_source(
    source: SourceConfig,
    device: dr.DeviceEntry,
    device_registry: dr.DeviceRegistry,
) -> bool:
    if not device.via_device_id:
        return False

    via_device = device_registry.async_get(device.via_device_id)
    if via_device is None:
        return token_matches(device.via_device_id, source.source)

    return _device_matches_source_name(source.source, via_device)


def _matches_source(
    source: SourceConfig,
    device: dr.DeviceEntry,
    device_registry: dr.DeviceRegistry,
) -> bool:
    if _device_matches_source_name(source.source, device):
        return True
    return _via_device_matches_source(source, device, device_registry)


def _matches_label(hass: HomeAssistant, source: SourceConfig, device: dr.DeviceEntry, entities: list[er.RegistryEntry]) -> bool:
    target = source.label.lower()
    device_labels = {label.lower() for label in _label_names(hass, _entry_labels(device))}
    entity_labels = {
        label.lower()
        for entity in entities
        for label in _label_names(hass, _entry_labels(entity))
    }
    return target in device_labels or target in entity_labels


def _entity_payload(hass: HomeAssistant, entity: er.RegistryEntry) -> dict[str, Any]:
    state = hass.states.get(entity.entity_id)
    attributes = dict(state.attributes) if state else {}
    domain = entity.entity_id.split(".", 1)[0]
    return {
        "entity_id": entity.entity_id,
        "unique_id": entity.unique_id,
        "name": entity.name or entity.original_name or attributes.get("friendly_name") or entity.entity_id,
        "icon": attributes.get("icon"),
        "domain": domain,
        "platform": entity.platform,
        "disabled": entity.disabled,
        "hidden": entity.hidden,
        "labels": sorted(_label_names(hass, _entry_labels(entity))),
        "state": state.state if state else None,
        "available": bool(state and state.state not in ("unknown", "unavailable")),
        "last_changed": state.last_changed.isoformat() if state else None,
        "last_updated": state.last_updated.isoformat() if state else None,
        "attributes": {
            key: _json_safe(value)
            for key, value in attributes.items()
            if key
            not in {
                "attribution",
                "entity_picture",
                "supported_features",
            }
        },
        "supported_features": _json_safe(attributes.get("supported_features")),
    }


def _device_payload(
    hass: HomeAssistant,
    source: SourceConfig,
    device: dr.DeviceEntry,
    entities: list[er.RegistryEntry],
) -> dict[str, Any]:
    entity_payloads = [_entity_payload(hass, entity) for entity in entities]
    domains = sorted({entity["domain"] for entity in entity_payloads})
    return {
        "id": device.id,
        "name": device.name_by_user or device.name or "Unnamed device",
        "manufacturer": device.manufacturer,
        "model": device.model,
        "sw_version": device.sw_version,
        "hw_version": device.hw_version,
        "area_id": device.area_id,
        "labels": sorted(_label_names(hass, _entry_labels(device))),
        "identifiers": sorted(_device_identifiers(device)),
        "connections": sorted(_device_connections(device)),
        "integrations": _device_integrations(hass, device),
        "source": source.source,
        "mqtt": _is_mqtt_device(hass, device),
        "entity_count": len(entity_payloads),
        "domains": domains,
        "entities": sorted(entity_payloads, key=lambda item: item["entity_id"]),
    }


def integration_payload(hass: HomeAssistant) -> dict[str, Any]:
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    configs = source_configs(hass)
    sources_payload = []

    for source in configs:
        devices = []
        for device in device_registry.devices.values():
            entities = list(er.async_entries_for_device(entity_registry, device.id))
            if not entities:
                continue
            if not (
                _matches_source(source, device, device_registry)
                or _matches_label(hass, source, device, entities)
            ):
                continue
            devices.append(_device_payload(hass, source, device, entities))

        devices.sort(key=lambda item: item["name"].lower())
        entity_count = sum(device["entity_count"] for device in devices)
        sources_payload.append(
            {
                "entry_id": source.entry_id,
                "title": source.title,
                "source": source.source,
                "topic_prefix": source.topic_prefix,
                "label": source.label,
                "periodic_interval_minutes": source.periodic_interval_minutes,
                "device_count": len(devices),
                "entity_count": entity_count,
                "devices": devices,
            }
        )

    return {
        "version": "0.1.0",
        "sources": sources_payload,
    }
