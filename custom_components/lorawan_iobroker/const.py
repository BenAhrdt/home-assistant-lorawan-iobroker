DOMAIN = "lorawan_iobroker"
NAME = "ioBroker LoRaWAN Bridge"

CONF_SOURCE = "source"
CONF_SOURCE_DEVICE_ID = "source_device_id"
CONF_LABEL = "label"
CONF_PERIODIC_INTERVAL_MINUTES = "periodic_interval_minutes"

DEFAULT_SOURCE = "LoRaWAN.1"
DEFAULT_LABEL = "ToIob"
DEFAULT_PERIODIC_INTERVAL_MINUTES = 10

PANEL_URL = DOMAIN
PANEL_JS_URL = f"/{DOMAIN}/panel.js"
