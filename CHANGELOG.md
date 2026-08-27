# Changelog

All notable changes to this project are documented in this file.

## [0.2.0] - 2026-08-27

### Added

- Added a data-flow view to the sidebar panel that visualizes imports from ioBroker through MQTT into Home Assistant and label-based exports back to ioBroker.
- Grouped exported devices by their originating Home Assistant integration, including integration brand icons and direct links to device pages.
- Added source and label match metadata to distinguish imported devices, exported devices, and devices participating in both directions.
- Added warnings and direct device links for potential feedback loops where an imported device also carries the configured export label.

### Changed

- Improved source matching by considering the configured source device and its direct downstream devices.
- Added a Devices/Data Flow view switch while retaining source, search, and integration filters.

## [0.1.4] - 2026-08-21

### Fixed

- Added a stable synthetic Home Assistant device for helpers and other entities without a device association, allowing ioBroker to consume their complete entity payloads.

## [0.1.3] - 2026-08-19

### Changed

- Reduced routine bridge logging: startup messages now use the `info` level, while MQTT publishes, received commands, notifications, service calls, and other high-frequency diagnostics use `debug`.

### Fixed

- Prevented successful bridge activity from appearing as warnings in the Home Assistant system log.
- Synchronized the version reported by the diagnostics panel with the integration version.

## [0.1.2] - 2026-08-09

### Changed

- Expanded the README with HACS installation, configuration, troubleshooting, updating, removal, and security guidance.
- Added complete English and German translations for the configuration and options flows.
- Optimized the integration icon for distribution.

## [0.1.1] - 2026-07-09

### Fixed

- Corrected MQTT device identifier handling.

## [0.1.0] - 2026-07-09

### Added

- Initial release of the ioBroker LoRaWAN Bridge integration for Home Assistant.

[0.2.0]: https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/compare/v0.1.4...v0.2.0
[0.1.4]: https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/releases/tag/v0.1.0
