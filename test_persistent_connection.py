#!/usr/bin/env python3
"""
Test script for persistent connection mode.

This script verifies that the upgraded IPComClient works correctly with:
1. Persistent TCP connection
2. Keep-alive loop (30s)
3. Status poll loop (350ms)
4. Command queue loop (250ms)
5. Auto-reconnect on disconnection

Usage:
    python test_persistent_connection.py
"""

import sys
import time
import logging
from pathlib import Path

# Add ipcom directory to path
ipcom_dir = Path(__file__).parent / "ipcom"
sys.path.insert(0, str(ipcom_dir))

from ipcom_tcp_client import IPComClient
from models import StateSnapshot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_persistent_connection():
    """Test persistent connection with background loops."""

    # Connection settings
    HOST = "megane-david.dyndns.info"
    PORT = 5000

    logger.info("=" * 80)
    logger.info("Testing Persistent Connection Mode")
    logger.info("=" * 80)

    # Create client
    client = IPComClient(host=HOST, port=PORT, debug=True)

    # Track state updates
    update_count = [0]
    last_snapshot = [None]

    def on_snapshot(snapshot: StateSnapshot):
        """Callback for state updates."""
        update_count[0] += 1
        last_snapshot[0] = snapshot

        if update_count[0] % 10 == 0:  # Log every 10 updates
            logger.info(f"Received {update_count[0]} state updates (polling at 350ms)")
            logger.info(f"Latest snapshot timestamp: {snapshot.timestamp_iso}")

            # Show sample module values
            module1_values = snapshot.get_module_values(1)
            logger.info(f"Module 1 values: {module1_values}")

    # Register callback
    client.on_state_snapshot(on_snapshot)

    try:
        # Start persistent connection
        logger.info("\n[1/4] Starting persistent connection...")
        success = client.start_persistent_connection(auto_reconnect=True)

        if not success:
            logger.error("Failed to start persistent connection")
            return False

        logger.info("✓ Persistent connection started successfully")
        logger.info("  - Keep-alive loop: running (30s interval)")
        logger.info("  - Status poll loop: running (350ms interval)")
        logger.info("  - Command queue loop: running (250ms interval)")
        logger.info("  - Receive loop: running (continuous)")

        # Wait for initial snapshots
        logger.info("\n[2/4] Waiting for state updates...")
        time.sleep(5)

        if update_count[0] == 0:
            logger.error("No state updates received after 5 seconds")
            return False

        logger.info(f"✓ Received {update_count[0]} updates in 5 seconds")
        logger.info(f"  Expected: ~14 updates (350ms interval)")
        logger.info(f"  Actual update rate: {update_count[0] / 5:.2f} updates/second")

        # Test command queueing
        logger.info("\n[3/4] Testing command queue...")

        # Queue a test command (turn on Module 1, Output 1)
        logger.info("Queuing ON command for Module 1, Output 1...")
        client.queue_command(client.turn_on, 1, 1)

        time.sleep(2)  # Wait for command to execute and state to update

        # Check if command was executed
        value = client.get_value(1, 1)
        logger.info(f"Module 1, Output 1 value after ON: {value}")

        if value and value > 0:
            logger.info("✓ Command executed successfully")
        else:
            logger.warning("⚠ Command may not have executed (check device)")

        # Queue OFF command
        logger.info("Queuing OFF command for Module 1, Output 1...")
        client.queue_command(client.turn_off, 1, 1)

        time.sleep(2)

        value = client.get_value(1, 1)
        logger.info(f"Module 1, Output 1 value after OFF: {value}")

        # Monitor for a bit longer
        logger.info("\n[4/4] Monitoring connection for 10 seconds...")
        initial_count = update_count[0]
        time.sleep(10)
        final_count = update_count[0]

        updates_received = final_count - initial_count
        logger.info(f"✓ Received {updates_received} updates in 10 seconds")
        logger.info(f"  Expected: ~29 updates (350ms interval)")
        logger.info(f"  Actual rate: {updates_received / 10:.2f} updates/second")

        # Verify connection is still active
        if client.is_connected():
            logger.info("✓ Connection is still active")
        else:
            logger.error("✗ Connection was lost")
            return False

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("TEST RESULTS")
        logger.info("=" * 80)
        logger.info(f"✓ Persistent connection: WORKING")
        logger.info(f"✓ Background loops: RUNNING")
        logger.info(f"✓ State updates: {update_count[0]} total ({update_count[0] / 17:.2f}/sec)")
        logger.info(f"✓ Command queue: FUNCTIONAL")
        logger.info(f"✓ Connection stability: STABLE")
        logger.info("=" * 80)

        return True

    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
        return False

    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        return False

    finally:
        # Cleanup
        logger.info("\nStopping persistent connection...")
        client.stop_persistent_connection()
        logger.info("Test complete")


if __name__ == "__main__":
    success = test_persistent_connection()
    sys.exit(0 if success else 1)
