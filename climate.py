"""Custom climate component for Fujitsu AC controlled via MQTT in Home Assistant."""
import logging
import voluptuous as vol
import json
from typing import List, Optional

from homeassistant.components.climate import (
    ClimateEntity,
    PLATFORM_SCHEMA,
    HVACMode,
    HVACAction,
    ClimateEntityFeature,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_NAME,
    CONF_TOPIC,
    PRECISION_WHOLE,
    TEMP_CELSIUS,
)
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

CONF_QOS = "qos"
CONF_RETAIN = "retain"

# Configuration validation
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_TOPIC): cv.string,
    vol.Optional(CONF_QOS, default=2): vol.All(vol.Coerce(int), vol.In([0, 1, 2])),
    vol.Optional(CONF_RETAIN, default=False): cv.boolean,
})

# Map HA modes to Fujitsu modes
MODE_MAPPING = {
    HVACMode.OFF: "Off",
    HVACMode.COOL: "Cool",
    HVACMode.HEAT: "Heat",
    HVACMode.FAN: "Fan",
}

REVERSE_MODE_MAPPING = {v: k for k, v in MODE_MAPPING.items()}

FAN_MAPPING = {
    "auto": "Auto",
    "low": "1",
    "medium": "2",
    "high": "3",
}

SWING_MODES = ["Auto", "Off", "Bottom", "Mid", "Top"]

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the MQTT Climate platform."""
    name = config[CONF_NAME]
    topic = config[CONF_TOPIC]
    qos = config[CONF_QOS]
    retain = config[CONF_RETAIN]
    
    async_add_entities([FujitsuClimate(hass, name, topic, qos, retain)], True)

class FujitsuClimate(ClimateEntity):
    """Representation of a Fujitsu AC Climate device."""

    def __init__(self, hass, name, topic, qos, retain):
        self._hass = hass
        self._name = name
        self._topic = topic
        self._qos = qos
        self._retain = retain
        
        # Initialize default values
        self._hvac_mode = HVACMode.OFF
        self._target_temperature = 22
        self._current_temperature = None
        self._fan_mode = "auto"
        self._swing_mode = "Off"
        self._quiet_mode = True
        
        # Set supported features
        self._supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE |
            ClimateEntityFeature.FAN_MODE |
            ClimateEntityFeature.SWING_MODE
        )

    @property
    def name(self) -> str:
        """Return the name of the climate device."""
        return self._name

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return self._supported_features

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def precision(self) -> float:
        """Return the precision of the system."""
        return PRECISION_WHOLE

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def hvac_mode(self) -> str:
        """Return hvac operation mode."""
        return self._hvac_mode

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes."""
        return [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.AUTO, HVACMode.DRY]

    @property
    def fan_mode(self) -> Optional[str]:
        """Return the fan setting."""
        return self._fan_mode

    @property
    def fan_modes(self) -> Optional[List[str]]:
        """Return the list of available fan modes."""
        return list(FAN_MAPPING.keys())

    @property
    def swing_mode(self) -> Optional[str]:
        """Return the swing mode setting."""
        return self._swing_mode

    @property
    def swing_modes(self) -> Optional[List[str]]:
        """Return the list of available swing modes."""
        return SWING_MODES

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE in kwargs:
            self._target_temperature = kwargs[ATTR_TEMPERATURE]
            await self._send_mqtt_command()
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: str):
        """Set new target hvac mode."""
        self._hvac_mode = hvac_mode
        await self._send_mqtt_command()
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str):
        """Set new target fan mode."""
        self._fan_mode = fan_mode
        await self._send_mqtt_command()
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str):
        """Set new target swing mode."""
        self._swing_mode = swing_mode
        await self._send_mqtt_command()
        self.async_write_ha_state()

    async def _send_mqtt_command(self):
        """Send MQTT command based on current state."""
        payload = {
            "Power": "On" if self._hvac_mode != HVACMode.OFF else "Off",
            "Vendor": "FUJITSU_AC",
            "Model": "ARRAH2E",
            "Command": "Control",
            "Mode": MODE_MAPPING.get(self._hvac_mode, "Auto"),
            "Celsius": "On",
            "Temp": int(self._target_temperature),
            "FanSpeed": FAN_MAPPING.get(self._fan_mode, "Auto"),
            "SwingV": self._swing_mode,
            "SwingH": "Off",
            "Quiet": "On" if self._quiet_mode else "Off"
        }

        await self._hass.services.async_call(
            'mqtt', 'publish',
            {
                'topic': self._topic,
                'payload': json.dumps(payload),
                'qos': self._qos,
                'retain': self._retain
            }
        )