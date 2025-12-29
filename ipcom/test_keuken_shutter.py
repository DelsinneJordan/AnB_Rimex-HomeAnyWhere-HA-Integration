#!/usr/bin/env python3
"""
Test script for Keuken shutter - verify it stops properly after commands.

This tests the dual-relay shutter control to ensure relays don't stay ON indefinitely.
"""

import sys
import time
from ipcom_tcp_client import IPComClient

# Connection settings
HOST = "megane-david.dyndns.info"
PORT = 5000

# Keuken shutter relays (CORRECT mapping from devices.yaml)
# rolluik_keuken_m = Module 5, Output 8 (UP relay)
# rolluik_keuken_d = Module 5, Output 7 (DOWN relay)
KEUKEN_UP_MODULE = 5
KEUKEN_UP_OUTPUT = 8
KEUKEN_DOWN_MODULE = 5
KEUKEN_DOWN_OUTPUT = 7

def get_relay_states(client):
    """Get current state of both keuken relays."""
    snapshot = client.get_latest_snapshot()
    if not snapshot:
        return None, None

    up_value = snapshot.get_value(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
    down_value = snapshot.get_value(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)
    return up_value, down_value

def print_relay_state(label, up_value, down_value):
    """Print relay state in a readable format."""
    up_state = "ON" if up_value > 0 else "OFF"
    down_state = "ON" if down_value > 0 else "OFF"

    print(f"{label}")
    print(f"  UP relay (M{KEUKEN_UP_MODULE}O{KEUKEN_UP_OUTPUT}):   {up_state:3s} (value={up_value})")
    print(f"  DOWN relay (M{KEUKEN_DOWN_MODULE}O{KEUKEN_DOWN_OUTPUT}): {down_state:3s} (value={down_value})")

    # Check for invalid state
    if up_value > 0 and down_value > 0:
        print("  WARNING: BOTH RELAYS ON - INVALID STATE!")
    elif up_value == 0 and down_value == 0:
        print("  OK: Both relays OFF (stopped)")
    elif up_value > 0:
        print("  Status: Opening (UP relay active)")
    elif down_value > 0:
        print("  Status: Closing (DOWN relay active)")
    print()

def main():
    print("=" * 70)
    print("Keuken Shutter Test - Relay State Monitoring")
    print("=" * 70)
    print()

    # Connect
    print(f"Connecting to {HOST}:{PORT}...")
    client = IPComClient(HOST, PORT, debug=False)

    if not client.connect():
        print("ERROR: Connection failed")
        return 1

    print("OK: Connected")

    if not client.authenticate():
        print("ERROR: Authentication failed")
        return 1

    print("OK: Authenticated")

    # Start polling
    client.start_snapshot_polling()
    print("OK: Polling started")
    print()

    # Wait for initial snapshot
    print("Waiting for initial state...")
    start = time.time()
    while not client.get_latest_snapshot() and time.time() - start < 3:
        client._receive_loop()
        time.sleep(0.05)

    if not client.get_latest_snapshot():
        print("ERROR: No snapshot received")
        return 1

    print()

    # Get initial state
    up_value, down_value = get_relay_states(client)
    print_relay_state("Initial State:", up_value, down_value)

    # Test sequence
    print("=" * 70)
    print("TEST 1: OPEN command (should turn ON UP relay, ensure DOWN is OFF)")
    print("=" * 70)
    print()

    print("Sending OPEN command...")
    # OPEN: DOWN=0, then UP=1
    client.turn_off(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)
    time.sleep(0.2)
    client.turn_on(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)

    # Wait for state update
    time.sleep(1)
    client._receive_loop()

    up_value, down_value = get_relay_states(client)
    print_relay_state("After OPEN command:", up_value, down_value)

    # Wait 5 seconds and check if relay is still ON
    print("Waiting 5 seconds to verify relay stays ON...")
    for i in range(5):
        time.sleep(1)
        client._receive_loop()
        up_value, down_value = get_relay_states(client)
        print(f"  After {i+1}s: UP={up_value}, DOWN={down_value}")

    print()
    up_value, down_value = get_relay_states(client)
    print_relay_state("After 5 seconds:", up_value, down_value)

    # Now send STOP command
    print("=" * 70)
    print("TEST 2: STOP command (should turn OFF both relays)")
    print("=" * 70)
    print()

    print("Sending STOP command...")
    client.turn_off(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
    client.turn_off(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)

    # Wait for state update
    time.sleep(1)
    client._receive_loop()

    up_value, down_value = get_relay_states(client)
    print_relay_state("After STOP command:", up_value, down_value)

    # Verify both are OFF
    if up_value == 0 and down_value == 0:
        print("SUCCESS: Both relays are OFF")
    else:
        print("FAILURE: Relays are not both OFF!")
        print(f"   Expected: UP=0, DOWN=0")
        print(f"   Got:      UP={up_value}, DOWN={down_value}")

    print()
    print("=" * 70)
    print("TEST 3: CLOSE command (should turn ON DOWN relay, ensure UP is OFF)")
    print("=" * 70)
    print()

    print("Sending CLOSE command...")
    # CLOSE: UP=0, then DOWN=1
    client.turn_off(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
    time.sleep(0.2)
    client.turn_on(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)

    # Wait for state update
    time.sleep(1)
    client._receive_loop()

    up_value, down_value = get_relay_states(client)
    print_relay_state("After CLOSE command:", up_value, down_value)

    # Wait 5 seconds
    print("Waiting 5 seconds to verify relay stays ON...")
    for i in range(5):
        time.sleep(1)
        client._receive_loop()
        up_value, down_value = get_relay_states(client)
        print(f"  After {i+1}s: UP={up_value}, DOWN={down_value}")

    print()
    up_value, down_value = get_relay_states(client)
    print_relay_state("After 5 seconds:", up_value, down_value)

    # Final STOP
    print("=" * 70)
    print("FINAL: Sending STOP to ensure clean state")
    print("=" * 70)
    print()

    print("Sending STOP command...")
    client.turn_off(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
    client.turn_off(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)

    # Wait for state update
    time.sleep(1)
    client._receive_loop()

    up_value, down_value = get_relay_states(client)
    print_relay_state("Final State:", up_value, down_value)

    # Verify both are OFF
    if up_value == 0 and down_value == 0:
        print("TEST COMPLETE: Keuken shutter is in safe state (both relays OFF)")
    else:
        print("WARNING: Keuken shutter is NOT in safe state!")
        print(f"   Expected: UP=0, DOWN=0")
        print(f"   Got:      UP={up_value}, DOWN={down_value}")

    # Disconnect
    client.disconnect()
    print("\nOK: Disconnected")

    return 0

if __name__ == "__main__":
    sys.exit(main())
