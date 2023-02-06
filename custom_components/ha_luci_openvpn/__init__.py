"""Support for OpenWRT (luci) routers."""
import logging
from datetime import timedelta

from openwrt_luci_rpc.openwrt_luci_rpc import OpenWrtLuciRPC # pylint: disable=import-error
from openwrt_luci_rpc.utilities import normalise_keys
from openwrt_luci_rpc.constants import Constants
from openwrt_luci_rpc.exceptions import LuciConfigError, InvalidLuciTokenError

import voluptuous as vol

from homeassistant.components.switch import (
    DOMAIN,
    SwitchEntity,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    CONF_SCAN_INTERVAL,
)
import homeassistant.helpers.config_validation as cv

from homeassistant.helpers import discovery
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util.dt import utcnow

_LOGGER = logging.getLogger(__name__)

MIN_UPDATE_INTERVAL = timedelta(minutes=1)
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=10)

SIGNAL_STATE_UPDATED = "{}.updated".format(DOMAIN)

DOMAIN = "luci_openvpn"
DATA_KEY = DOMAIN

DEFAULT_SSL = False
DEFAULT_VERIFY_SSL = True

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_SSL, default=DEFAULT_SSL): cv.boolean,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
        vol.Optional(
            CONF_SCAN_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
        ): vol.All(cv.time_period, vol.Clamp(min=MIN_UPDATE_INTERVAL)),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema(vol.All(cv.ensure_list, [CONFIG_SCHEMA]))},
    extra=vol.ALLOW_EXTRA,
)

def setup(hass, config):
    _LOGGER.info("Initializing Luci OpenVPN platform")

    if not config[DOMAIN]:
        return False

    for p_config in config[DOMAIN]:
        interval = p_config.get(CONF_SCAN_INTERVAL)
        data = hass.data[DATA_KEY + "_" + p_config.get(CONF_HOST)] = LuciRPC(p_config)

        """Update status from the online service."""
        openvpn_result = data.rpc_call('get_all', 'openvpn')
        _LOGGER.debug("Luci get_all openvpn returned: %s", openvpn_result)    

        for entry in openvpn_result:
            _LOGGER.debug("Luci: vpn %s",entry)
            if openvpn_result[entry][".name"] in data.vpn:
                vpn = data.vpn[openvpn_result[entry][".name"]]
            else:
                _LOGGER.info("Luci: vpn %s found", entry)
                vpn = data.vpn[openvpn_result[entry][".name"]] = LuciVPN()
                hass.async_create_task(
                    discovery.async_load_platform(
                        hass,
                        "switch",
                        DOMAIN,
                        (p_config.get(CONF_HOST), openvpn_result[entry][".name"], DATA_KEY + "_" + p_config.get(CONF_HOST),),
                        config,
                    )
                )

            vpn.name = openvpn_result[entry][".name"]
            if "enabled" not in openvpn_result[entry]:
                vpn.enabled = False
            else:
                vpn.enabled = openvpn_result[entry]["enabled"] == "1"

        async_dispatcher_send(hass, SIGNAL_STATE_UPDATED)

        if not data.success_init:
            return False
    
    return True

class LuciVPN():

    def __init__(self):
        self.name = ""
        self.enabled = False

    def __repr__(self):
        return self.name

    def __eq__(self, other):
        if isinstance(other, LuciVPN):
            return (self.name == other.name)
        else:
            return False

    def __ne__(self, other):
        return (not self.__eq__(other))

    def __hash__(self):
        return hash(self.__repr__())

class LuciRPC():
    """This class scans Openvpn client configured."""

    def __init__(self, config):
        """Initialize the router."""
        self._rpc = OpenWrtLuciRPC(
            config.get(CONF_HOST),
            config.get(CONF_USERNAME),
            config.get(CONF_PASSWORD),
            config.get(CONF_SSL),
            config.get(CONF_VERIFY_SSL),
        )
        self.success_init = self._rpc.token is not None
        if not self.success_init:
            _LOGGER.error("Cannot connect to luci")    
            return

        self.vpn = {}

    def rpc_call(self, method, *args, **kwargs):
        rpc_uci_call = Constants.LUCI_RPC_UCI_PATH.format(
            self._rpc.host_api_url), method, *args
        try:
            rpc_result = self._rpc._call_json_rpc(*rpc_uci_call)
        except InvalidLuciTokenError:
            _LOGGER.info("Refreshing login token")
            self._rpc._refresh_token()
            return self.rpc_call(method, args, kwargs)

        return rpc_result


class LuciVPNEntity(Entity):
    """Base class for all entities."""

    def __init__(self, host, name, datastr):
        """Initialize the entity."""
        self.host = host
        self.vpnname = name
        self.datastr = datastr

        self.data = None
        self.vpn = None

    async def async_added_to_hass(self):
        """Register update dispatcher."""
        self.data = self.hass.data[self.datastr]
        self.vpn = self.data.vpn[self.vpnname]

        async_dispatcher_connect(
            self.hass, SIGNAL_STATE_UPDATED, self.async_schedule_update_ha_state
        )

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:vpn"

    @property
    def name(self):
        return f"lucivpn_{self.host}_{self.vpnname}"

    @property
    def should_poll(self):
        """Return the polling state."""
        return True

    @property
    def assumed_state(self):
        """Return true if unable to access real state of entity."""
        return False

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        return dict(
        )