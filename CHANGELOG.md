# Changelog

All notable changes to this project are documented in this file.

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

[0.1.3]: https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/BenAhrdt/home-assistant-lorawan-iobroker/releases/tag/v0.1.0
