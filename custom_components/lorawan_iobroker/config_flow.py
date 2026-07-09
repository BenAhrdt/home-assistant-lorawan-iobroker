from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import label_registry as lr

from .const import (
    CONF_LABEL,
    CONF_PERIODIC_INTERVAL_MINUTES,
    CONF_SOURCE,
    CONF_SOURCE_DEVICE_ID,
    DEFAULT_LABEL,
    DEFAULT_PERIODIC_INTERVAL_MINUTES,
    DEFAULT_SOURCE,
    DOMAIN,
)
from .registry import normalize


class LoRaWANIobrokerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ioBroker LoRaWAN Bridge."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            device_id = user_input[CONF_SOURCE_DEVICE_ID]
            source_devices = _source_device_options(self.hass)
            if device_id not in source_devices:
                errors[CONF_SOURCE_DEVICE_ID] = "no_source_device"
            else:
                source = source_devices[device_id]["source"]
                label = self._label_from_input(user_input.get(CONF_LABEL, DEFAULT_LABEL))
                self._ensure_label(label)

                await self.async_set_unique_id(source.lower())
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_SOURCE: source,
                        CONF_SOURCE_DEVICE_ID: device_id,
                        CONF_LABEL: label,
                    },
                )

        source_devices = _source_device_options(self.hass)
        default_device_id = next(iter(source_devices), "")
        default_name = _default_name(source_devices, default_device_id)
        default_label = _default_label_value(self.hass)
        device_options = _source_device_select_options(source_devices)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=default_name): str,
                vol.Required(CONF_SOURCE_DEVICE_ID, default=default_device_id): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=device_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_LABEL, default=default_label): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_label_options(self.hass),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    def _ensure_label(self, name: str) -> None:
        _ensure_label(self.hass, name)

    def _label_from_input(self, value) -> str:
        return _label_from_input(value)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LoRaWANIobrokerOptionsFlow(config_entry)


class LoRaWANIobrokerOptionsFlow(config_entries.OptionsFlow):
    """Options flow for ioBroker LoRaWAN Bridge."""

    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors = {}
        source_devices = self._source_devices_with_current()

        if user_input is not None:
            device_id = user_input[CONF_SOURCE_DEVICE_ID]
            if device_id not in source_devices:
                errors[CONF_SOURCE_DEVICE_ID] = "no_source_device"
            else:
                source = source_devices[device_id]["source"]
                if self._source_configured_elsewhere(source):
                    errors[CONF_SOURCE_DEVICE_ID] = "source_already_configured"
                else:
                    label = _label_from_input(user_input.get(CONF_LABEL, DEFAULT_LABEL))
                    _ensure_label(self.hass, label)

                    data = dict(self._config_entry.data)
                    data.update(
                        {
                            CONF_NAME: user_input[CONF_NAME],
                            CONF_SOURCE: source,
                            CONF_SOURCE_DEVICE_ID: device_id,
                            CONF_LABEL: label,
                        }
                    )
                    options = dict(self._config_entry.options)
                    options[CONF_PERIODIC_INTERVAL_MINUTES] = user_input[
                        CONF_PERIODIC_INTERVAL_MINUTES
                    ]
                    self._update_config_entry(user_input[CONF_NAME], data, options, source)
                    return self.async_create_entry(title="", data=options)

        current_device_id = self._config_entry.data.get(CONF_SOURCE_DEVICE_ID)
        if current_device_id not in source_devices and source_devices:
            current_device_id = next(iter(source_devices))
        default_device_id = current_device_id or next(iter(source_devices), "")
        interval = self._config_entry.options.get(
            CONF_PERIODIC_INTERVAL_MINUTES,
            DEFAULT_PERIODIC_INTERVAL_MINUTES,
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME,
                    default=self._config_entry.data.get(CONF_NAME, self._config_entry.title),
                ): str,
                vol.Required(
                    CONF_SOURCE_DEVICE_ID,
                    default=default_device_id,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_source_device_select_options(source_devices),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_LABEL,
                    default=self._config_entry.data.get(CONF_LABEL, _default_label_value(self.hass)),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_label_options(self.hass),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
                vol.Required(
                    CONF_PERIODIC_INTERVAL_MINUTES,
                    default=interval,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=1440,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    def _source_configured_elsewhere(self, source: str) -> bool:
        source = source.lower()
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.entry_id == self._config_entry.entry_id:
                continue
            if entry.data.get(CONF_SOURCE, "").lower() == source:
                return True
        return False

    def _source_devices_with_current(self) -> dict[str, dict[str, str]]:
        source_devices = _source_device_options(self.hass)
        current_device_id = self._config_entry.data.get(CONF_SOURCE_DEVICE_ID)
        if current_device_id and current_device_id not in source_devices:
            current_source = self._config_entry.data.get(CONF_SOURCE, DEFAULT_SOURCE)
            source_devices[current_device_id] = {
                "source": current_source,
                "name": self._config_entry.title,
                "label": f"{self._config_entry.title} ({current_source}) - current device not found",
            }
        return source_devices

    def _update_config_entry(self, title: str, data: dict, options: dict, source: str) -> None:
        try:
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                title=title,
                data=data,
                options=options,
                unique_id=source.lower(),
            )
        except TypeError:
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                title=title,
                data=data,
                options=options,
            )


def _source_device_options(hass) -> dict[str, dict[str, str]]:
    device_registry = dr.async_get(hass)
    devices: dict[str, dict[str, str]] = {}

    for device in device_registry.devices.values():
        source = _source_from_device(device)
        if source is None:
            continue
        name = device.name_by_user or device.name or source
        details = " - ".join(
            value
            for value in (
                device.sw_version,
                device.model,
            )
            if value
        )
        display_name = device.name_by_user or device.name or source
        if normalize(display_name) == normalize(source):
            display_name = source.replace(".", " ")
        devices[device.id] = {
            "source": source,
            "name": display_name,
            "label": f"{name} ({source})" if not details else f"{name} ({source}) - {details}",
        }

    return dict(
        sorted(
            devices.items(),
            key=lambda item: (
                int(item[1]["source"].rsplit(".", 1)[1]),
                item[1]["label"].lower(),
            ),
        )
    )


def _source_device_select_options(
    source_devices: dict[str, dict[str, str]],
) -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value=device_id, label=option["label"])
        for device_id, option in source_devices.items()
    ] or [
        selector.SelectOptionDict(
            value="",
            label="No lorawan.x MQTT device found",
        )
    ]


def _source_from_device(device: dr.DeviceEntry) -> str | None:
    values = [
        device.name,
        device.name_by_user,
        *[str(identifier) for _, identifier in device.identifiers],
    ]
    for value in values:
        if not value:
            continue
        normalized = normalize(value)
        parts = normalized.split("_")
        if len(parts) == 2 and parts[0] == "lorawan" and parts[1].isdigit():
            return f"LoRaWAN.{parts[1]}"
    return None


def _default_name(source_devices: dict[str, dict[str, str]], device_id: str) -> str:
    if device_id in source_devices:
        return source_devices[device_id]["name"]
    return "LoRaWAN 1"


def _label_options(hass) -> list[str]:
    label_registry = lr.async_get(hass)
    labels = {label.name for label in label_registry.async_list_labels()}
    labels.add(DEFAULT_LABEL)
    return sorted(labels, key=lambda item: (item.lower() != DEFAULT_LABEL.lower(), item.lower()))


def _ensure_label(hass, name: str) -> None:
    if not name:
        return
    label_registry = lr.async_get(hass)
    if (
        label_registry.async_get_label(name) is None
        and label_registry.async_get_label_by_name(name) is None
    ):
        label_registry.async_create(
            name,
            icon="mdi:radio-tower",
            description="Entities exchanged with ioBroker LoRaWAN.",
        )


def _label_from_input(value) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else DEFAULT_LABEL
    return str(value or DEFAULT_LABEL).strip()


def _default_label_value(hass) -> str:
    label_registry = lr.async_get(hass)
    label = label_registry.async_get_label_by_name(DEFAULT_LABEL)
    if label is not None:
        return label.name
    return DEFAULT_LABEL
