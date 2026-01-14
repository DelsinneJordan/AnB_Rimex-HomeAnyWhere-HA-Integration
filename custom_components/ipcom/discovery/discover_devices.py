#!/usr/bin/env python3
"""
HomeAnywhere Device Discovery Tool

This interactive CLI tool connects to the HomeAnywhere cloud service,
retrieves your site configuration, and generates a devices.yaml file
for the IPCom Home Assistant integration.

Usage:
    python discover_devices.py

Or as a module:
    python -m custom_components.ipcom.discovery discover
"""

import sys
import getpass
from pathlib import Path

# Handle imports for both direct execution and module execution
try:
    # Try relative imports first (when running directly from discovery folder)
    from homeanywhere_api import HomeAnywhereAPI, FlashSite
    from devices_generator import generate_devices_yaml
except ImportError:
    # Fall back to package imports (when running as module)
    from .homeanywhere_api import HomeAnywhereAPI, FlashSite
    from .devices_generator import generate_devices_yaml


def print_banner():
    """Print welcome banner."""
    print()
    print("=" * 60)
    print("  HomeAnywhere Device Discovery Tool")
    print("  IPCom Home Assistant Integration")
    print("=" * 60)
    print()
    print("This tool will:")
    print("  1. Connect to HomeAnywhere cloud")
    print("  2. Retrieve your site configuration")
    print("  3. Generate a devices.yaml file")
    print()


def get_credentials() -> tuple[str, str]:
    """Prompt user for HomeAnywhere credentials."""
    print("-" * 40)
    print("Enter your HomeAnywhere credentials")
    print("-" * 40)
    print()

    username = input("Username: ").strip()
    if not username:
        print("Error: Username cannot be empty")
        sys.exit(1)

    password = getpass.getpass("Password: ")
    if not password:
        print("Error: Password cannot be empty")
        sys.exit(1)

    return username, password


def select_site(sites: list[FlashSite]) -> FlashSite:
    """Let user select a site from the list."""
    print()
    print("-" * 40)
    print(f"Found {len(sites)} site(s) on your account")
    print("-" * 40)
    print()

    for i, site in enumerate(sites, 1):
        print(f"  [{i}] {site.name} (ID: {site.id})")

    print()

    if len(sites) == 1:
        print(f"Auto-selecting: {sites[0].name}")
        return sites[0]

    while True:
        try:
            choice = input(f"Select site (1-{len(sites)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(sites):
                return sites[idx]
            print(f"Please enter a number between 1 and {len(sites)}")
        except ValueError:
            print("Please enter a valid number")


def select_ipcom(site: FlashSite) -> int:
    """Let user select an IPCom if multiple are present."""
    if not site.ipcoms:
        print("Error: No IPCom devices found on this site")
        sys.exit(1)

    if len(site.ipcoms) == 1:
        ipcom = site.ipcoms[0]
        print(f"\nFound IPCom: {ipcom.name} ({ipcom.local_address})")
        return 0

    print()
    print("-" * 40)
    print(f"Found {len(site.ipcoms)} IPCom device(s)")
    print("-" * 40)
    print()

    for i, ipcom in enumerate(site.ipcoms, 1):
        print(f"  [{i}] {ipcom.name}")
        print(f"      Local:  {ipcom.local_address}:{ipcom.local_port}")
        print(f"      Remote: {ipcom.remote_address}:{ipcom.remote_port}")
        print()

    while True:
        try:
            choice = input(f"Select IPCom (1-{len(site.ipcoms)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(site.ipcoms):
                return idx
            print(f"Please enter a number between 1 and {len(site.ipcoms)}")
        except ValueError:
            print("Please enter a valid number")


def get_output_path() -> Path:
    """Get output path for devices.yaml."""
    # Default to current directory
    default_path = Path.cwd() / "devices.yaml"

    # If running from the discovery directory, use that
    script_dir = Path(__file__).parent
    if script_dir.name == "discovery":
        default_path = script_dir / "devices.yaml"

    print()
    print("-" * 40)
    print("Output file")
    print("-" * 40)
    print()
    print(f"Default: {default_path}")
    print()

    custom = input("Press Enter for default, or enter custom path: ").strip()

    if custom:
        return Path(custom)
    return default_path


def print_summary(site: FlashSite, ipcom_idx: int):
    """Print summary of discovered devices."""
    ipcom = site.ipcoms[ipcom_idx]

    print()
    print("-" * 40)
    print("Discovery Summary")
    print("-" * 40)
    print()
    print(f"Site: {site.name}")
    print(f"IPCom: {ipcom.name}")
    print()

    # Count devices by type
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

    # Shutters are in pairs
    shutters = shutters // 2

    print("Discovered devices:")
    print(f"  - Lights:   {lights}")
    print(f"  - Dimmers:  {dimmers}")
    print(f"  - Shutters: {shutters} (paired)")
    print()

    # List modules
    print("Modules found:")
    for module in ipcom.modules:
        active_outputs = sum(1 for o in module.outputs if o)
        print(f"  - Module {module.number}: {module.type} ({active_outputs} outputs)")


def main():
    """Main entry point."""
    print_banner()

    # Get credentials
    username, password = get_credentials()

    # Connect and login
    print()
    print("Connecting to HomeAnywhere...")

    api = HomeAnywhereAPI()

    try:
        sites = api.login(username, password)
    except ConnectionError as e:
        print(f"\nError: Could not connect to HomeAnywhere")
        print(f"Details: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"\nError: {e}")
        sys.exit(1)

    if not sites:
        print("\nError: No sites found on your account")
        sys.exit(1)

    print(f"Login successful!")

    # Select site
    selected_site = select_site(sites)

    # Get full site configuration
    print()
    print(f"Fetching configuration for '{selected_site.name}'...")

    try:
        full_site = api.get_site_config(selected_site.id, selected_site.version)
        full_site.name = selected_site.name  # Preserve name from login
    except Exception as e:
        print(f"\nError fetching site configuration: {e}")
        sys.exit(1)

    if not full_site.ipcoms:
        print("\nError: No IPCom devices found on this site")
        sys.exit(1)

    # Select IPCom (if multiple)
    ipcom_idx = select_ipcom(full_site)

    # Show summary
    print_summary(full_site, ipcom_idx)

    # Get output path
    output_path = get_output_path()

    # Check if file exists
    if output_path.exists():
        print()
        overwrite = input(f"File exists. Overwrite? (y/N): ").strip().lower()
        if overwrite != 'y':
            print("Aborted.")
            sys.exit(0)

    # Generate devices.yaml
    print()
    print("Generating devices.yaml...")

    ipcom = full_site.ipcoms[ipcom_idx]
    yaml_content = generate_devices_yaml(full_site, ipcom)

    # Write file
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_content, encoding="utf-8")
    except Exception as e:
        print(f"\nError writing file: {e}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  SUCCESS!")
    print("=" * 60)
    print()
    print(f"Generated: {output_path}")
    print()
    print("Next steps:")
    print("  1. Review the generated devices.yaml")
    print("  2. Adjust display names if needed")
    print("  3. Copy to your Home Assistant config directory")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        sys.exit(1)
