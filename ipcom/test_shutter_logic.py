#!/usr/bin/env python3
"""
Test keuken shutter dual-relay safety logic.

Verifies that the shutter follows the correct relay truth table:
  UP  DOWN  Result
  0   0     STOP / IDLE
  1   0     MOVING UP (opening)
  0   1     MOVING DOWN (closing)
  1   1     INVALID - MUST NEVER OCCUR
"""

import sys
import time
from ipcom_tcp_client import IPComClient

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
    """Get current state of both relays."""
    snapshot = client.get_latest_snapshot()
    if not snapshot:
        return None, None

    up = snapshot.get_value(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
    down = snapshot.get_value(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)
    return up, down

def verify_state(client, expected_up, expected_down, label):
    """Verify relay state matches expectations."""
    # Allow time for state to stabilize (need longer for hardware response)
    time.sleep(1.5)
    # Poll multiple times to ensure we get fresh data
    for _ in range(5):
        client._receive_loop()
        time.sleep(0.1)

    up, down = get_relay_states(client)

    up_ok = (up > 0) if expected_up else (up == 0)
    down_ok = (down > 0) if expected_down else (down == 0)

    status = "PASS" if (up_ok and down_ok) else "FAIL"

    print(f"{label}")
    print(f"  Expected: UP={1 if expected_up else 0}, DOWN={1 if expected_down else 0}")
    print(f"  Actual:   UP={up}, DOWN={down}")
    print(f"  Status:   {status}")

    if up > 0 and down > 0:
        print("  ERROR: BOTH RELAYS ON - INVALID STATE!")
        return False

    return up_ok and down_ok

def main():
    print("=" * 70)
    print("Keuken Shutter Dual-Relay Safety Logic Test")
    print("=" * 70)
    print()

    client = IPComClient(HOST, PORT, debug=False)

    print(f"Connecting to {HOST}:{PORT}...")
    if not client.connect():
        print("ERROR: Connection failed")
        return 1
    print("OK: Connected")

    if not client.authenticate():
        print("ERROR: Authentication failed")
        return 1
    print("OK: Authenticated")

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
    up, down = get_relay_states(client)
    print(f"Initial state: UP={up}, DOWN={down}")
    print()

    # Force clean state first
    print("=" * 70)
    print("SETUP: Ensuring clean state (both relays OFF)")
    print("=" * 70)
    client.turn_off(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
    client.turn_off(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)
    time.sleep(1)
    client._receive_loop()

    if not verify_state(client, False, False, "Initial STOP state"):
        print("WARNING: Could not establish clean initial state")
    print()

    # Test 1: UP (OPEN)
    print("=" * 70)
    print("TEST 1: OPEN command (should result in UP=1, DOWN=0)")
    print("=" * 70)
    print("Sending: turn_off(DOWN), then turn_on(UP)")
    client.turn_off(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)
    time.sleep(0.2)
    client.turn_on(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)

    test1_pass = verify_state(client, True, False, "After OPEN command")
    print()

    # Test 2: STOP from UP
    print("=" * 70)
    print("TEST 2: STOP from OPEN (should result in UP=0, DOWN=0)")
    print("=" * 70)
    print("Sending: turn_off(UP), turn_off(DOWN)")
    client.turn_off(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
    client.turn_off(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)

    test2_pass = verify_state(client, False, False, "After STOP command")
    print()

    # Test 3: DOWN (CLOSE)
    print("=" * 70)
    print("TEST 3: CLOSE command (should result in UP=0, DOWN=1)")
    print("=" * 70)
    print("Sending: turn_off(UP), then turn_on(DOWN)")
    client.turn_off(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
    time.sleep(0.2)
    client.turn_on(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)

    test3_pass = verify_state(client, False, True, "After CLOSE command")
    print()

    # Test 4: STOP from DOWN
    print("=" * 70)
    print("TEST 4: STOP from CLOSE (should result in UP=0, DOWN=0)")
    print("=" * 70)
    print("Sending: turn_off(UP), turn_off(DOWN)")
    client.turn_off(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
    client.turn_off(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)

    test4_pass = verify_state(client, False, False, "After STOP command")
    print()

    # Test 5: Direction change (DOWN to UP without STOP)
    print("=" * 70)
    print("TEST 5: Direction change CLOSE->OPEN (safety check)")
    print("=" * 70)
    print("Starting with CLOSE (DOWN=1)...")
    client.turn_off(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
    time.sleep(0.2)
    client.turn_on(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)
    time.sleep(0.5)
    client._receive_loop()

    print("Now sending OPEN command (should turn OFF DOWN first)...")
    client.turn_off(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)
    time.sleep(0.2)
    client.turn_on(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)

    test5_pass = verify_state(client, True, False, "After direction change")
    print()

    # Test 6: Direction change (UP to DOWN without STOP)
    print("=" * 70)
    print("TEST 6: Direction change OPEN->CLOSE (safety check)")
    print("=" * 70)
    print("Starting with OPEN (UP=1)...")
    # Already in OPEN from test 5

    print("Now sending CLOSE command (should turn OFF UP first)...")
    client.turn_off(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
    time.sleep(0.2)
    client.turn_on(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)

    test6_pass = verify_state(client, False, True, "After direction change")
    print()

    # Final cleanup: STOP
    print("=" * 70)
    print("CLEANUP: Final STOP")
    print("=" * 70)
    client.turn_off(KEUKEN_UP_MODULE, KEUKEN_UP_OUTPUT)
    client.turn_off(KEUKEN_DOWN_MODULE, KEUKEN_DOWN_OUTPUT)

    cleanup_pass = verify_state(client, False, False, "Final state")
    print()

    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Test 1 (OPEN):              {'PASS' if test1_pass else 'FAIL'}")
    print(f"Test 2 (STOP from OPEN):    {'PASS' if test2_pass else 'FAIL'}")
    print(f"Test 3 (CLOSE):             {'PASS' if test3_pass else 'FAIL'}")
    print(f"Test 4 (STOP from CLOSE):   {'PASS' if test4_pass else 'FAIL'}")
    print(f"Test 5 (CLOSE->OPEN):       {'PASS' if test5_pass else 'FAIL'}")
    print(f"Test 6 (OPEN->CLOSE):       {'PASS' if test6_pass else 'FAIL'}")
    print(f"Cleanup (Final STOP):       {'PASS' if cleanup_pass else 'FAIL'}")
    print()

    all_pass = all([test1_pass, test2_pass, test3_pass, test4_pass,
                    test5_pass, test6_pass, cleanup_pass])

    if all_pass:
        print("RESULT: ALL TESTS PASSED")
        print("The keuken shutter follows correct dual-relay safety logic.")
    else:
        print("RESULT: SOME TESTS FAILED")
        print("The shutter may have safety issues.")

    client.disconnect()
    print()
    print("OK: Disconnected")

    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())
