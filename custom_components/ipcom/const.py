"""Constants for the IPCom integration."""
import shutil
import sys

DOMAIN = "ipcom"

# Configuration keys
CONF_CLI_PATH = "cli_path"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Defaults
DEFAULT_HOST = ""  # No default - user must provide their host
DEFAULT_PORT = 5000

# Entity platforms
PLATFORMS = ["light", "cover"]


def get_python_executable() -> str:
    """Get the correct Python executable for the current platform.

    Home Assistant containers typically use 'python3', while Windows
    often uses 'python'. This function finds the correct executable.

    Returns:
        Path to Python executable (e.g., 'python3', 'python', or full path)
    """
    # First, try to use the same Python that's running Home Assistant
    # This is the most reliable approach
    current_python = sys.executable
    if current_python:
        return current_python

    # Fallback: Check for python3 first (Linux/macOS), then python
    python3_path = shutil.which("python3")
    if python3_path:
        return python3_path

    python_path = shutil.which("python")
    if python_path:
        return python_path

    # Last resort fallback
    return "python3"
