#!/usr/bin/env python3
"""Test script to verify the bug fix for Issue #1."""
import sys
sys.path.insert(0, 'ipcom')

from ipcom_tcp_client import IPComClient
import time

def main():
    client = IPComClient('megane-david.dyndns.info', 5000, debug=False)

    print('Connecting...')
    if not client.connect():
        print('Connection failed')
        return 1

    print('Authenticating...')
    if not client.authenticate():
        print('Authentication failed')
        return 1

    print('Starting polling...')
    client.start_snapshot_polling()

    # Wait for initial snapshot
    print('Waiting for snapshot...', end='', flush=True)
    for i in range(40):
        client._receive_loop()
        time.sleep(0.1)
        if client.get_latest_snapshot():
            print(' Got it!')
            break
    else:
        print(' Timeout!')
        client.disconnect()
        return 1

    # Get current state
    snapshot = client.get_latest_snapshot()
    values_before = snapshot.get_module_values(3)

    print('\n=== Module 3 State BEFORE ===')
    for i, val in enumerate(values_before):
        state = 'ON ' if val > 0 else 'OFF'
        print(f'  Output {i+1}: {val:3d} [{state}]')

    # Turn on Output 2
    print('\n=== Turning ON Output 2 (BADKAMER) ===')
    client.turn_on(3, 2)

    # Wait for update
    print('Waiting for state update...')
    time.sleep(2)
    for _ in range(20):
        client._receive_loop()
        time.sleep(0.1)

    # Check final state
    snapshot_after = client.get_latest_snapshot()
    values_after = snapshot_after.get_module_values(3)

    print('\n=== Module 3 State AFTER ===')
    for i, val in enumerate(values_after):
        state = 'ON ' if val > 0 else 'OFF'
        changed = ' <- CHANGED' if val != values_before[i] else ''
        print(f'  Output {i+1}: {val:3d} [{state}]{changed}')

    # Analyze results
    print('\n=== Test Results ===')
    output_2_on = values_after[1] > 0
    output_4_on = values_after[3] > 0

    if output_2_on and output_4_on:
        print('✅ SUCCESS: Both Output 2 and Output 4 are ON!')
        print('   Issue #1 is FIXED - lights no longer turn off each other')
        result = 0
    elif output_2_on and not output_4_on:
        print('❌ BUG STILL EXISTS: Output 4 turned OFF when Output 2 turned ON')
        result = 1
    elif not output_2_on:
        print('❌ ERROR: Output 2 did not turn ON (command may have failed)')
        result = 1
    else:
        print('? Unexpected state')
        result = 1

    client.disconnect()
    return result

if __name__ == '__main__':
    sys.exit(main())
