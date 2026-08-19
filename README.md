# ioBroker LoRaWAN Bridge for Home Assistant

[![Validate](https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/actions/workflows/validate.yml/badge.svg)](https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/actions/workflows/validate.yml)
[![GitHub release](https://img.shields.io/github/v/release/BenAhrdt/home-assistant-lorawan-iobroker)](https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/releases)

Custom integration for visualising and controlling Home Assistant MQTT devices exchanged with the ioBroker LoRaWAN adapter.

The integration reads devices and entities already discovered by Home Assistant's MQTT integration, groups them by their configured ioBroker LoRaWAN source, and provides a sidebar panel for diagnostics and control. It does not establish a separate MQTT connection.

## Requirements

- Home Assistant 2024.6.0 or newer
- HACS for the recommended installation method
- Home Assistant's MQTT integration, connected to the same broker as ioBroker
- MQTT devices created by the ioBroker LoRaWAN adapter
- ioBroker/Home Assistant automations that exchange bridge messages

LoRaWAN sources must follow the `LoRaWAN.<number>` naming convention, for example `LoRaWAN.0` or `LoRaWAN.1`. The corresponding MQTT topic prefix is derived automatically; `LoRaWAN.1`, for example, maps to `lorawan_1/lorawan_1`.

## Installation with HACS

Until the integration is included in the default HACS catalogue, add it as a custom repository:

1. Open HACS in Home Assistant.
2. Open the menu and select **Custom repositories**.
3. Enter `https://github.com/BenAhrdt/home-assistant-lorawan-iobroker`.
4. Select **Integration** as the category and add the repository.
5. Download **ioBroker LoRaWAN Bridge** and restart Home Assistant.

You can also use this shortcut after HACS has been installed:

[![Open your Home Assistant instance and add this repository to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BenAhrdt&repository=home-assistant-lorawan-iobroker&category=integration)

For a manual installation, copy `custom_components/lorawan_iobroker` to the `custom_components` directory in your Home Assistant configuration and restart Home Assistant.

## Configuration

1. Make sure the ioBroker LoRaWAN MQTT device is already visible in Home Assistant.
2. Go to **Settings → Devices & services → Add integration**.
3. Search for **ioBroker LoRaWAN Bridge**.
4. Select the `lorawan.x` source device and choose a name and label.

The default label is `ToIob`. Apply this label to every Home Assistant entity or device that should be sent to ioBroker. Existing labels can be selected in the integration options; entering a new name creates that label automatically.

Add one configuration entry for each LoRaWAN source. The same source cannot be configured more than once.

The integration options allow you to change:

- the display name
- the associated LoRaWAN source device
- the Home Assistant label used for discovery
- the periodic discovery interval

## Sidebar panel

After setup, **ioBroker LoRaWAN Bridge** appears in the Home Assistant sidebar. The panel shows the configured sources and their discovered devices and entities and provides the controls supported by the bridge.

Only administrators should use bridge controls that can change devices. Access still follows the permissions and services available in the Home Assistant instance.

## Updating and removing

HACS notifies you when a new release is available. Install the update in HACS and restart Home Assistant when requested.

To remove the integration, first delete all ioBroker LoRaWAN Bridge entries under **Settings → Devices & services**. Then remove the repository through HACS and restart Home Assistant. Removing the integration does not delete MQTT devices, labels, or ioBroker automations.

## Troubleshooting

- **No LoRaWAN source is offered:** Verify that MQTT is configured and that a device named or identified as `lorawan.<number>` exists.
- **No entities appear:** Apply the configured label, `ToIob` by default, to the relevant entity or device.
- **Commands do not reach ioBroker:** Check the MQTT broker connection, bridge automations, source number, and generated topic prefix.
- **The panel is missing after installation:** Restart Home Assistant and clear the browser cache.

Enable debug logging when reporting a problem:

```yaml
logger:
  logs:
    custom_components.lorawan_iobroker: debug
```

Please report reproducible problems in the [GitHub issue tracker](https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/issues) and include the Home Assistant version, integration version, relevant logs, and the configured source name. Remove credentials and private MQTT payload data first.

## Known limitations

- The integration depends on existing MQTT discovery and does not manage the broker connection.
- Message exchange with ioBroker depends on separately configured automations.
- Source discovery expects the `LoRaWAN.<number>` naming scheme.

## Changelog

Release notes and the complete change history are available in the [changelog](CHANGELOG.md).

## License

This project is licensed under the [MIT License](LICENSE).
