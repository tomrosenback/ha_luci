import logging

from homeassistant.helpers.entity import ToggleEntity

from . import DATA_KEY, LuciVPNEntity

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up a Luci switch."""
    if discovery_info is None:
        return
    add_entities([LuciVPNSwitch(*discovery_info)])


class LuciVPNSwitch(LuciVPNEntity, ToggleEntity):
    """Representation of a Luci switch."""

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self.vpn.enabled

    def turn_on(self, **kwargs):
        """Turn the switch on."""
        #await self.instrument.turn_on()
        _LOGGER.debug("Luci: %s turned on", self.vpn.name)

        self.data.rpc_call("set", "openvpn", self.vpn.name, "enabled", "1")
        self.data.rpc_call("commit", "openvpn")

        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn the switch off."""
        #await self.instrument.turn_off()
        _LOGGER.debug("Luci: %s turned off", self.vpn.name)

        self.data.rpc_call("set", "openvpn", self.vpn.name, "enabled", "0")
        self.data.rpc_call("commit", "openvpn")

        self.schedule_update_ha_state()

    def update(self):
        """Update vesync device."""
        self.vpn.enabled = False
        try:
            cfg_value = self.data.rpc_call('get', "openvpn", self.vpn.name, "enabled")
        except:
            return
        if (cfg_value is not None):
            _LOGGER.debug("LuciOpenVPN get %s returned: %s", self.vpn.name, cfg_value) 
            self.vpn.enabled = (cfg_value == "1")
        