# ioBroker LoRaWAN Bridge for Home Assistant

Custom integration for visualising and controlling Home Assistant MQTT devices that are exchanged with ioBroker LoRaWAN automations.

This integration does not connect to MQTT itself. It reads Home Assistant's existing devices and entities, groups them by configured ioBroker LoRaWAN source, and exposes a sidebar panel for diagnostics and control.

## Current assumptions

- MQTT devices are already discovered in Home Assistant.
- ioBroker exchange is handled by existing automations.
- Entities/devices sent to ioBroker are marked with the Home Assistant label `ToIob`.
- Sources are named like `LoRaWAN.0`, `LoRaWAN.1`; the topic prefix is derived automatically, e.g. `LoRaWAN.1` -> `lorawan_1/lorawan_1`.

## Installation

Copy this repository into `custom_components/lorawan_iobroker` or install it via HACS as a custom repository once published.

Restart Home Assistant, then add the integration from **Settings -> Devices & services**.
