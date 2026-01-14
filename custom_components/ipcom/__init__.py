"""The IPCom Home Anywhere Blue integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICES,
    CONF_CONNECTION_TYPE,
    CONF_LOCAL_HOST,
    CONF_LOCAL_PORT,
    CONF_REMOTE_HOST,
    CONF_REMOTE_PORT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import IPComCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IPCom from a config entry."""
    # Extract config
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    username = entry.data.get(CONF_USERNAME, "")
    password = entry.data.get(CONF_PASSWORD, "")
    devices_config = entry.data.get(CONF_DEVICES)  # May be None for manual config

    # Extract connection type configuration
    connection_type = entry.data.get(CONF_CONNECTION_TYPE)
    local_host = entry.data.get(CONF_LOCAL_HOST)
    local_port = entry.data.get(CONF_LOCAL_PORT)
    remote_host = entry.data.get(CONF_REMOTE_HOST)
    remote_port = entry.data.get(CONF_REMOTE_PORT)

    _LOGGER.info(
        "Setting up IPCom integration | host: %s:%s | connection_type: %s | "
        "local: %s:%s | remote: %s:%s",
        host, port, connection_type or "not set",
        local_host or "N/A", local_port or "N/A",
        remote_host or "N/A", remote_port or "N/A"
    )

    # Create coordinator (CLI path is auto-detected from bundled CLI)
    coordinator = IPComCoordinator(
        hass=hass,
        host=host,
        port=port,
        username=username,
        password=password,
        devices_config=devices_config,
        connection_type=connection_type,
        local_host=local_host,
        local_port=local_port,
        remote_host=remote_host,
        remote_port=remote_port,
    )

    # Start persistent CLI subprocess
    try:
        await coordinator.async_start()
    except Exception as err:
        _LOGGER.error("Failed to start IPCom coordinator: %s", err)
        return False

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward entry setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register shutdown handler
    async def _async_shutdown(_):
        """Shutdown handler for HA stop event."""
        await coordinator.async_shutdown()

    entry.async_on_unload(
        hass.bus.async_listen_once("homeassistant_stop", _async_shutdown)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Shutdown coordinator first
    coordinator: IPComCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_shutdown()

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Remove coordinator
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
