"""Config flow for IPCom Home Anywhere Blue integration.

This config flow supports two setup methods:
1. Auto-discovery: Connect to HomeAnywhere cloud to automatically discover devices
2. Manual: Enter IPCom connection details manually (requires devices.yaml)

The auto-discovery flow:
    1. User chooses setup method (auto or manual)
    2. If auto: Enter HomeAnywhere cloud credentials
    3. Select site from available sites
    4. Confirm discovered devices
    5. Select connection type (local/remote/both)
    6. Create config entry with all device data stored

Device configuration is stored in the config entry, NOT in devices.yaml.
This ensures HACS updates don't affect user configuration.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICES,
    CONF_CLOUD_USERNAME,
    CONF_CLOUD_PASSWORD,
    CONF_SITE_ID,
    CONF_SITE_NAME,
    CONF_CONNECTION_TYPE,
    CONF_LOCAL_HOST,
    CONF_LOCAL_PORT,
    CONF_REMOTE_HOST,
    CONF_REMOTE_PORT,
    CONNECTION_TYPE_LOCAL,
    CONNECTION_TYPE_REMOTE,
    CONNECTION_TYPE_BOTH,
    DEFAULT_PORT,
    DOMAIN,
)
from .discovery.homeanywhere_api import HomeAnywhereAPI, FlashSite
from .discovery.devices_generator import generate_devices_config

_LOGGER = logging.getLogger(__name__)

# Step IDs
STEP_USER = "user"
STEP_CLOUD_LOGIN = "cloud_login"
STEP_SELECT_SITE = "select_site"
STEP_CONFIRM_DEVICES = "confirm_devices"
STEP_CONNECTION_TYPE = "connection_type"
STEP_MANUAL = "manual"


async def async_discover_from_cloud(
    hass: HomeAssistant,
    username: str,
    password: str,
) -> tuple[list[FlashSite], HomeAnywhereAPI]:
    """Connect to HomeAnywhere cloud and get available sites.

    Args:
        hass: Home Assistant instance
        username: HomeAnywhere username
        password: HomeAnywhere password

    Returns:
        Tuple of (list of sites, API instance for further calls)

    Raises:
        ValueError: If login fails
        ConnectionError: If connection fails
    """
    _LOGGER.debug("Attempting to connect to HomeAnywhere cloud for user: %s", username)
    api = HomeAnywhereAPI()

    def _login():
        return api.login(username, password)

    try:
        sites = await hass.async_add_executor_job(_login)
        _LOGGER.info(
            "Successfully connected to HomeAnywhere cloud. Found %d site(s) for user: %s",
            len(sites), username
        )
        for site in sites:
            _LOGGER.debug("  - Site: %s (ID: %d)", site.name, site.id)
        return sites, api
    except Exception as err:
        _LOGGER.error("Failed to connect to HomeAnywhere cloud: %s", err)
        raise


async def async_get_site_config(
    hass: HomeAssistant,
    api: HomeAnywhereAPI,
    site: FlashSite,
) -> FlashSite:
    """Get full site configuration from HomeAnywhere.

    Args:
        hass: Home Assistant instance
        api: Authenticated API instance
        site: Site to get config for

    Returns:
        FlashSite with full configuration (IPComs, modules, etc.)
    """
    _LOGGER.debug("Fetching configuration for site: %s (ID: %d)", site.name, site.id)

    def _get_config():
        full_site = api.get_site_config(site.id, site.version)
        full_site.name = site.name  # Preserve name
        return full_site

    try:
        full_site = await hass.async_add_executor_job(_get_config)
        _LOGGER.info(
            "Successfully fetched site configuration for '%s': %d IPCom(s) found",
            site.name, len(full_site.ipcoms)
        )
        for ipcom in full_site.ipcoms:
            _LOGGER.debug(
                "  - IPCom: %s | Local: %s:%d | Remote: %s:%d | Modules: %d",
                ipcom.name,
                ipcom.local_address, ipcom.local_port,
                ipcom.remote_address, ipcom.remote_port,
                len(ipcom.modules)
            )
        return full_site
    except Exception as err:
        _LOGGER.error("Failed to fetch site configuration for '%s': %s", site.name, err)
        raise


class IPComConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IPCom integration.

    Supports both auto-discovery from HomeAnywhere cloud and manual configuration.
    """

    VERSION = 2  # Bumped version for new config structure

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._cloud_api: HomeAnywhereAPI | None = None
        self._sites: list[FlashSite] = []
        self._selected_site: FlashSite | None = None
        self._full_site: FlashSite | None = None
        self._cloud_username: str = ""
        self._cloud_password: str = ""
        self._devices_config: dict | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - choose setup method."""
        _LOGGER.debug("Config flow step: user (setup method selection)")

        if user_input is not None:
            setup_method = user_input.get("setup_method", "auto")
            _LOGGER.info("User selected setup method: %s", setup_method)

            if setup_method == "auto":
                return await self.async_step_cloud_login()
            else:
                return await self.async_step_manual()

        # Show setup method selection
        return self.async_show_form(
            step_id=STEP_USER,
            data_schema=vol.Schema({
                vol.Required("setup_method", default="auto"): vol.In({
                    "auto": "Auto-discover from HomeAnywhere (Recommended)",
                    "manual": "Manual configuration",
                }),
            }),
        )

    async def async_step_cloud_login(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle HomeAnywhere cloud login step."""
        _LOGGER.debug("Config flow step: cloud_login")
        errors: dict[str, str] = {}

        if user_input is not None:
            self._cloud_username = user_input[CONF_CLOUD_USERNAME]
            self._cloud_password = user_input[CONF_CLOUD_PASSWORD]

            try:
                self._sites, self._cloud_api = await async_discover_from_cloud(
                    self.hass,
                    self._cloud_username,
                    self._cloud_password,
                )

                if not self._sites:
                    _LOGGER.warning("No sites found for user: %s", self._cloud_username)
                    errors["base"] = "no_sites"
                else:
                    # Proceed to site selection
                    return await self.async_step_select_site()

            except ValueError as err:
                _LOGGER.error("Cloud login failed (ValueError): %s", err)
                errors["base"] = "cloud_auth_failed"
            except ConnectionError as err:
                _LOGGER.error("Cloud connection failed (ConnectionError): %s", err)
                errors["base"] = "cloud_connection_failed"
            except Exception as err:
                _LOGGER.exception("Unexpected error during cloud login: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id=STEP_CLOUD_LOGIN,
            data_schema=vol.Schema({
                vol.Required(CONF_CLOUD_USERNAME): cv.string,
                vol.Required(CONF_CLOUD_PASSWORD): cv.string,
            }),
            errors=errors,
        )

    async def async_step_select_site(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle site selection step."""
        _LOGGER.debug("Config flow step: select_site")
        errors: dict[str, str] = {}

        if user_input is not None:
            site_id = int(user_input["site"])
            _LOGGER.info("User selected site ID: %d", site_id)

            # Find selected site
            for site in self._sites:
                if site.id == site_id:
                    self._selected_site = site
                    break

            if self._selected_site:
                try:
                    # Fetch full site configuration
                    self._full_site = await async_get_site_config(
                        self.hass,
                        self._cloud_api,
                        self._selected_site,
                    )

                    if not self._full_site.ipcoms:
                        _LOGGER.warning("No IPCom devices found for site: %s", self._selected_site.name)
                        errors["base"] = "no_ipcoms"
                    else:
                        # Proceed to device confirmation
                        return await self.async_step_confirm_devices()

                except Exception as err:
                    _LOGGER.exception("Error fetching site config: %s", err)
                    errors["base"] = "fetch_config_failed"

        # Build site selection options
        site_options = {
            str(site.id): site.name for site in self._sites
        }

        return self.async_show_form(
            step_id=STEP_SELECT_SITE,
            data_schema=vol.Schema({
                vol.Required("site"): vol.In(site_options),
            }),
            errors=errors,
        )

    async def async_step_confirm_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle device confirmation step."""
        _LOGGER.debug("Config flow step: confirm_devices")

        if user_input is not None:
            # User confirmed devices - proceed to connection type selection
            ipcom = self._full_site.ipcoms[0]  # Use first IPCom

            # Generate and store device configuration for later
            self._devices_config = generate_devices_config(self._full_site, ipcom)

            _LOGGER.info(
                "User confirmed devices for site '%s': %d lights, %d shutters",
                self._selected_site.name,
                len(self._devices_config.get("lights", {})),
                len(self._devices_config.get("shutters", {})) // 2  # Pairs
            )

            # Proceed to connection type selection
            return await self.async_step_connection_type()

        # Calculate device summary
        ipcom = self._full_site.ipcoms[0]
        lights = 0
        dimmers = 0
        shutters = 0

        for module in ipcom.modules:
            for output in module.outputs:
                if not output:
                    continue
                if module.type == "ExoDim":
                    dimmers += 1
                elif module.type == "ExoStore":
                    shutters += 1
                else:
                    lights += 1

        shutters = shutters // 2  # Pairs

        return self.async_show_form(
            step_id=STEP_CONFIRM_DEVICES,
            data_schema=vol.Schema({}),  # Just a confirm button
            description_placeholders={
                "site_name": self._selected_site.name,
                "ipcom_name": ipcom.name,
                "ipcom_address": f"{ipcom.local_address}:{ipcom.local_port}",
                "lights": str(lights),
                "dimmers": str(dimmers),
                "shutters": str(shutters),
            },
        )

    async def async_step_connection_type(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle connection type selection step."""
        _LOGGER.debug("Config flow step: connection_type")
        errors: dict[str, str] = {}

        ipcom = self._full_site.ipcoms[0]

        if user_input is not None:
            connection_type = user_input["connection_type"]
            _LOGGER.info(
                "User selected connection type: %s for site '%s'",
                connection_type, self._selected_site.name
            )

            # Determine host/port based on connection type
            if connection_type == CONNECTION_TYPE_LOCAL:
                host = ipcom.local_address
                port = ipcom.local_port
                _LOGGER.info("Using LOCAL connection: %s:%d", host, port)
            elif connection_type == CONNECTION_TYPE_REMOTE:
                host = ipcom.remote_address
                port = ipcom.remote_port
                _LOGGER.info("Using REMOTE connection: %s:%d", host, port)
            else:  # CONNECTION_TYPE_BOTH
                # Primary is local, will fallback to remote
                host = ipcom.local_address
                port = ipcom.local_port
                _LOGGER.info(
                    "Using BOTH connection mode: Primary LOCAL %s:%d, Fallback REMOTE %s:%d",
                    host, port, ipcom.remote_address, ipcom.remote_port
                )

            # Check for existing entries with same host
            unique_id = f"{host}:{port}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            title = f"IPCom - {self._selected_site.name}"

            config_data = {
                CONF_HOST: host,
                CONF_PORT: port,
                CONF_USERNAME: ipcom.username,
                CONF_PASSWORD: ipcom.password,
                CONF_SITE_ID: self._selected_site.id,
                CONF_SITE_NAME: self._selected_site.name,
                CONF_DEVICES: self._devices_config,
                CONF_CONNECTION_TYPE: connection_type,
                # Store both addresses for fallback support
                CONF_LOCAL_HOST: ipcom.local_address,
                CONF_LOCAL_PORT: ipcom.local_port,
                CONF_REMOTE_HOST: ipcom.remote_address,
                CONF_REMOTE_PORT: ipcom.remote_port,
            }

            _LOGGER.info(
                "Creating config entry for '%s' | Connection: %s | Host: %s:%d",
                title, connection_type, host, port
            )

            return self.async_create_entry(
                title=title,
                data=config_data,
            )

        # Show connection type form
        return self.async_show_form(
            step_id=STEP_CONNECTION_TYPE,
            data_schema=vol.Schema({
                vol.Required("connection_type", default=CONNECTION_TYPE_LOCAL): vol.In({
                    CONNECTION_TYPE_LOCAL: "Local (LAN connection)",
                    CONNECTION_TYPE_REMOTE: "Remote (Internet connection)",
                    CONNECTION_TYPE_BOTH: "Both (Local preferred, Remote fallback)",
                }),
            }),
            description_placeholders={
                "local_address": f"{ipcom.local_address}:{ipcom.local_port}",
                "remote_address": f"{ipcom.remote_address}:{ipcom.remote_port}",
            },
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual configuration step."""
        _LOGGER.debug("Config flow step: manual")
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.info(
                "Manual configuration: host=%s, port=%d",
                user_input[CONF_HOST], user_input[CONF_PORT]
            )

            # Check for existing entries with same host
            unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            title = f"IPCom ({user_input[CONF_HOST]}:{user_input[CONF_PORT]})"

            # For manual config, devices will be loaded from devices.yaml
            return self.async_create_entry(
                title=title,
                data={
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_PORT: user_input[CONF_PORT],
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_DEVICES: None,  # Will load from devices.yaml
                    CONF_CONNECTION_TYPE: CONNECTION_TYPE_LOCAL,  # Manual is always direct
                },
            )

        return self.async_show_form(
            step_id=STEP_MANUAL,
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return IPComOptionsFlow(config_entry)


class IPComOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for IPCom integration.

    Allows users to re-run discovery to update devices or modify settings.
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._cloud_api: HomeAnywhereAPI | None = None
        self._sites: list[FlashSite] = []
        self._selected_site: FlashSite | None = None
        self._full_site: FlashSite | None = None
        self._devices_config: dict | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow init."""
        _LOGGER.debug("Options flow step: init")

        if user_input is not None:
            action = user_input.get("action")
            _LOGGER.info("User selected options action: %s", action)

            if action == "rediscover":
                return await self.async_step_rediscover()
            elif action == "change_connection":
                return await self.async_step_change_connection()

        # Get current connection type for display
        current_type = self._config_entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_LOCAL)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action", default="rediscover"): vol.In({
                    "rediscover": "Re-discover devices from HomeAnywhere",
                    "change_connection": "Change connection type",
                }),
            }),
            description_placeholders={
                "current_connection": current_type,
            },
        )

    async def async_step_change_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle connection type change."""
        _LOGGER.debug("Options flow step: change_connection")
        errors: dict[str, str] = {}

        # Get stored addresses
        local_host = self._config_entry.data.get(CONF_LOCAL_HOST, "")
        local_port = self._config_entry.data.get(CONF_LOCAL_PORT, DEFAULT_PORT)
        remote_host = self._config_entry.data.get(CONF_REMOTE_HOST, "")
        remote_port = self._config_entry.data.get(CONF_REMOTE_PORT, DEFAULT_PORT)

        if not local_host and not remote_host:
            _LOGGER.warning("No stored connection addresses found. Cannot change connection type.")
            errors["base"] = "no_addresses"
            return self.async_show_form(
                step_id="change_connection",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        if user_input is not None:
            connection_type = user_input["connection_type"]
            _LOGGER.info("Changing connection type to: %s", connection_type)

            # Determine new host/port
            if connection_type == CONNECTION_TYPE_LOCAL:
                new_host = local_host
                new_port = local_port
            elif connection_type == CONNECTION_TYPE_REMOTE:
                new_host = remote_host
                new_port = remote_port
            else:  # CONNECTION_TYPE_BOTH
                new_host = local_host
                new_port = local_port

            # Update config entry
            new_data = {
                **self._config_entry.data,
                CONF_HOST: new_host,
                CONF_PORT: new_port,
                CONF_CONNECTION_TYPE: connection_type,
            }

            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data=new_data,
            )

            _LOGGER.info(
                "Connection type changed to %s. New host: %s:%d. Reloading integration...",
                connection_type, new_host, new_port
            )

            # Reload the integration to apply new connection settings
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)

            return self.async_create_entry(title="", data={})

        current_type = self._config_entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_LOCAL)

        return self.async_show_form(
            step_id="change_connection",
            data_schema=vol.Schema({
                vol.Required("connection_type", default=current_type): vol.In({
                    CONNECTION_TYPE_LOCAL: "Local (LAN connection)",
                    CONNECTION_TYPE_REMOTE: "Remote (Internet connection)",
                    CONNECTION_TYPE_BOTH: "Both (Local preferred, Remote fallback)",
                }),
            }),
            description_placeholders={
                "current_connection": current_type,
                "local_address": f"{local_host}:{local_port}" if local_host else "Not available",
                "remote_address": f"{remote_host}:{remote_port}" if remote_host else "Not available",
            },
            errors=errors,
        )

    async def async_step_rediscover(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-discovery step."""
        _LOGGER.debug("Options flow step: rediscover")
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                self._sites, self._cloud_api = await async_discover_from_cloud(
                    self.hass,
                    user_input[CONF_CLOUD_USERNAME],
                    user_input[CONF_CLOUD_PASSWORD],
                )

                if not self._sites:
                    errors["base"] = "no_sites"
                else:
                    return await self.async_step_select_site()

            except ValueError:
                _LOGGER.error("Re-discovery: Cloud authentication failed")
                errors["base"] = "cloud_auth_failed"
            except ConnectionError:
                _LOGGER.error("Re-discovery: Cloud connection failed")
                errors["base"] = "cloud_connection_failed"
            except Exception as err:
                _LOGGER.exception("Re-discovery: Unexpected error: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="rediscover",
            data_schema=vol.Schema({
                vol.Required(CONF_CLOUD_USERNAME): cv.string,
                vol.Required(CONF_CLOUD_PASSWORD): cv.string,
            }),
            errors=errors,
        )

    async def async_step_select_site(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle site selection in options flow."""
        _LOGGER.debug("Options flow step: select_site")
        errors: dict[str, str] = {}

        if user_input is not None:
            site_id = int(user_input["site"])

            for site in self._sites:
                if site.id == site_id:
                    self._selected_site = site
                    break

            if self._selected_site:
                try:
                    self._full_site = await async_get_site_config(
                        self.hass,
                        self._cloud_api,
                        self._selected_site,
                    )

                    if self._full_site.ipcoms:
                        # Store devices config and proceed to connection type
                        ipcom = self._full_site.ipcoms[0]
                        self._devices_config = generate_devices_config(
                            self._full_site, ipcom
                        )
                        return await self.async_step_select_connection()
                    else:
                        errors["base"] = "no_ipcoms"

                except Exception as err:
                    _LOGGER.exception("Options flow: Error fetching site config: %s", err)
                    errors["base"] = "fetch_config_failed"

        site_options = {str(site.id): site.name for site in self._sites}

        return self.async_show_form(
            step_id="select_site",
            data_schema=vol.Schema({
                vol.Required("site"): vol.In(site_options),
            }),
            errors=errors,
        )

    async def async_step_select_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle connection type selection in options flow after rediscovery."""
        _LOGGER.debug("Options flow step: select_connection")
        errors: dict[str, str] = {}

        ipcom = self._full_site.ipcoms[0]

        if user_input is not None:
            connection_type = user_input["connection_type"]

            # Determine host/port based on connection type
            if connection_type == CONNECTION_TYPE_LOCAL:
                host = ipcom.local_address
                port = ipcom.local_port
            elif connection_type == CONNECTION_TYPE_REMOTE:
                host = ipcom.remote_address
                port = ipcom.remote_port
            else:  # CONNECTION_TYPE_BOTH
                host = ipcom.local_address
                port = ipcom.local_port

            # Update the config entry data
            new_data = {
                **self._config_entry.data,
                CONF_HOST: host,
                CONF_PORT: port,
                CONF_USERNAME: ipcom.username,
                CONF_PASSWORD: ipcom.password,
                CONF_SITE_ID: self._selected_site.id,
                CONF_SITE_NAME: self._selected_site.name,
                CONF_DEVICES: self._devices_config,
                CONF_CONNECTION_TYPE: connection_type,
                CONF_LOCAL_HOST: ipcom.local_address,
                CONF_LOCAL_PORT: ipcom.local_port,
                CONF_REMOTE_HOST: ipcom.remote_address,
                CONF_REMOTE_PORT: ipcom.remote_port,
            }

            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data=new_data,
            )

            _LOGGER.info(
                "Re-discovery complete. Updated config for '%s' | Connection: %s | Host: %s:%d. Reloading integration...",
                self._selected_site.name, connection_type, host, port
            )

            # Reload the integration to apply new settings
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)

            return self.async_create_entry(title="", data={})

        # Get current connection type as default
        current_type = self._config_entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_LOCAL)

        return self.async_show_form(
            step_id="select_connection",
            data_schema=vol.Schema({
                vol.Required("connection_type", default=current_type): vol.In({
                    CONNECTION_TYPE_LOCAL: "Local (LAN connection)",
                    CONNECTION_TYPE_REMOTE: "Remote (Internet connection)",
                    CONNECTION_TYPE_BOTH: "Both (Local preferred, Remote fallback)",
                }),
            }),
            description_placeholders={
                "local_address": f"{ipcom.local_address}:{ipcom.local_port}",
                "remote_address": f"{ipcom.remote_address}:{ipcom.remote_port}",
            },
            errors=errors,
        )
