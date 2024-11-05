"""Custom climate component for Fujitsu AC controlled via MQTT in Home Assistant."""
import logging
import voluptuous as vol
import json
from typing import Any, Dict, List, Optional

from homeassistant.components.climate import (
    ClimateEntity,
    PLATFORM_SCHEMA,
    HVACMode,
    HVACAction,
    ClimateEntityFeature,
)
from homeassistant.components.mqtt.const import CONF_TOPIC
from homeassistant.components import mqtt
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_NAME,
    PRECISION_WHOLE,
    Platform,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ir_climate"
CONF_QOS = "qos"
CONF_RETAIN = "retain"

# Configuration validation
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_TOPIC): cv.string,
        vol.Optional(CONF_QOS, default=2): vol.All(vol.Coerce(int), vol.In([0, 1, 2])),
        vol.Optional(CONF_RETAIN, default=False): cv.boolean,
    }
)

# Map HA modes to Fujitsu modes
MODE_MAPPING = {
    HVACMode.OFF: "Off",
    HVACMode.COOL: "Cool",
    HVACMode.HEAT: "Heat",
    HVACMode.FAN_ONLY: "Fan",
    HVACMode.AUTO: "Auto",
    HVACMode.DRY: "Dry",
}

REVERSE_MODE_MAPPING = {v: k for k, v in MODE_MAPPING.items()}

FAN_MAPPING = {
    "auto": "Auto",
    "low": "1",
    "medium": "2",
    "high": "3",
}

SWING_MODES = ["Auto", "Off", "Bottom", "Mid", "Top"]

def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the MQTT Climate platform."""
    name = config[CONF_NAME]
    topic = config[CONF_TOPIC]
    qos = config[CONF_QOS]
    retain = config[CONF_RETAIN]

    add_entities([FujitsuClimate(hass, name, topic, qos, retain)], True)

class FujitsuClimate(ClimateEntity):
    """Representation of a Fujitsu AC Climate device."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_WHOLE
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
    )
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.AUTO,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]
    _attr_fan_modes = list(FAN_MAPPING.keys())
    _attr_swing_modes = SWING_MODES
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_target_temperature_step = 1

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        topic: str,
        qos: int,
        retain: bool,
    ) -> None:
        """Initialize the climate device."""
        self.hass = hass
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{name}"
        self._topic = topic
        self._qos = qos
        self._retain = retain

        # Initialize state
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature = 22
        self._attr_current_temperature = None
        self._attr_fan_mode = "auto"
        self._attr_swing_mode = "Off"
        self._quiet_mode = True
        self._attr_available = True

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self._attr_target_temperature = temp
            await self._send_mqtt_command()
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        self._attr_hvac_mode = hvac_mode
        await self._send_mqtt_command()
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        self._attr_fan_mode = fan_mode
        await self._send_mqtt_command()
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing mode."""
        self._attr_swing_mode = swing_mode
        await self._send_mqtt_command()
        self.async_write_ha_state()

    async def _send_mqtt_command(self) -> None:
        """Send MQTT command based on current state."""
        try:
            payload = {
                "Power": "On" if self._attr_hvac_mode != HVACMode.OFF else "Off",
                "Vendor": "FUJITSU_AC",
                "Model": "ARRAH2E",
                "Command": "Control",
                "Mode": MODE_MAPPING.get(self._attr_hvac_mode, "Auto"),
                "Celsius": "On",
                "Temp": int(self._attr_target_temperature),
                "FanSpeed": FAN_MAPPING.get(self._attr_fan_mode, "Auto"),
                "SwingV": self._attr_swing_mode,
                "SwingH": "Off",
                "Quiet": "On" if self._quiet_mode else "Off",
            }

            await mqtt.async_publish(
                self.hass,
                self._topic,
                json.dumps(payload),
                self._qos,
                self._retain,
            )
        except Exception as ex:
            _LOGGER.error("Failed to send MQTT command: %s", ex)
            self._attr_available = False
            self.async_write_ha_state()
