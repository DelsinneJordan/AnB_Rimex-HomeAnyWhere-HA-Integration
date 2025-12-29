#!/usr/bin/env python3
"""Test script to demonstrate 60-second safety timeout."""

import sys
import time
sys.path.insert(0, '.')

from ipcom_client import IPComClient

# Import CLI functions
from ipcom_cli import DeviceMapper, control_cover

def test_60s_timeout():
    """Test that shutter stops after 60 seconds."""
    print("=" * 70)
    print("SAFETY TIMEOUT TEST - 60 Second Auto-Stop")
    print("=" * 70)
    print()
    
    # Connect to device
    client = IPComClient(host="megane-david.dyndns.info", port=5000)
    
    print("Connecting...")
    if not client.connect():
        print("❌ Connection failed")
        return
    
    print("✔ Connected")
    
    # Authenticate
    if not client.authenticate():
        print("❌ Authentication failed")
        return
    
    print("✔ Authenticated")
    
    # Start polling
    client.start_snapshot_polling()
    print("✔ Polling started")
    
    # Wait for initial snapshot
    print("Waiting for initial state...")
    start = time.time()
    while not client.get_latest_snapshot() and time.time() - start < 3:
        client._receive_loop()
        time.sleep(0.05)
    print("✔ Initial state loaded\n")
    
    # Load device mapper
    mapper = DeviceMapper()
    
    # Open shutter (starts 60s timer)
    print("Step 1: Opening shutter...")
    print("-" * 70)
    control_cover(client, mapper, "rolluik_sal_links_m", "open")
    print()
    
    # Wait and show countdown
    print("Step 2: Waiting for 60-second safety timeout...")
    print("-" * 70)
    for remaining in range(60, 0, -5):
        print(f"   {remaining}s remaining... (keeping connection alive)")
        for _ in range(5):
            client._receive_loop()
            time.sleep(1)
    
    print()
    print("Step 3: Verifying automatic STOP occurred...")
    print("-" * 70)
    
    # Give timer a moment to execute
    time.sleep(2)
    client._receive_loop()
    
    # Check relay state
    snapshot = client.get_latest_snapshot()
    up_value = snapshot.get_value(5, 2)  # Module 5, Output 2 (UP relay)
    down_value = snapshot.get_value(5, 1)  # Module 5, Output 1 (DOWN relay)
    
    print(f"   UP relay (Module 5, Output 2):   {up_value}")
    print(f"   DOWN relay (Module 5, Output 1): {down_value}")
    print()
    
    if up_value == 0 and down_value == 0:
        print("✔ SUCCESS: Both relays are OFF (safety timeout worked!)")
    else:
        print(f"❌ FAIL: Relays still ON (UP={up_value}, DOWN={down_value})")
    
    print()
    client.disconnect()
    print("✔ Disconnected")
    print()
    print("=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    test_60s_timeout()
