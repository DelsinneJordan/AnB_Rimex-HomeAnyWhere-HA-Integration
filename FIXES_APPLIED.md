# Fixes Applied for Home Assistant Integration Issues

**Date:** 2025-12-29 18:30
**Issue:** Initial deployment failed with "No entities found" and socket errors

## Issues Identified

### 1. ❌ No Light/Cover Entities Found
**Error:**
```
No light entities found in coordinator data
No cover entities found in coordinator data
```

**Root Cause:**
- `coordinator.data` was `None` during entity setup
- The callback from the background thread wasn't updating the coordinator fast enough
- `async_config_entry_first_refresh()` timed out waiting for initial data

### 2. ❌ Socket Error on Shutdown
**Error:**
```
Socket error in receive loop: [Errno 9] Bad file descriptor
```

**Root Cause:**
- Race condition during shutdown: disconnect() closed socket while receive loop was still reading
- No delay between signaling threads to stop and closing the socket

### 3. ⚠️ Confusing Config Flow
**Issue:**
- Config flow asks for "scan_interval" with default 10s
- User doesn't know this is just a fallback (real updates are 350ms)

## Fixes Applied

### Fix 1: Thread-Safe Callback Execution

**File:** `custom_components/ipcom/coordinator.py:105-107`

**Before:**
```python
self.async_set_updated_data(self._latest_data)
```

**After:**
```python
# Schedule the update in the event loop (thread-safe)
self.hass.loop.call_soon_threadsafe(
    lambda: self.async_set_updated_data(self._latest_data)
)
```

**Why:** The callback runs in a background thread, but `async_set_updated_data()` must run in Home Assistant's async event loop. Using `call_soon_threadsafe()` ensures thread-safe execution.

### Fix 2: Extended Initial Data Wait

**File:** `custom_components/ipcom/coordinator.py:218-227`

**Before:**
```python
for _ in range(5):  # Wait up to 0.5 seconds
    if self._latest_data:
        return self._latest_data
    await asyncio.sleep(0.1)
```

**After:**
```python
for i in range(20):  # Wait up to 2 seconds (20 * 0.1s)
    if self._latest_data:
        _LOGGER.debug(f"Received first snapshot after {(i+1)*0.1:.1f}s")
        return self._latest_data
    await asyncio.sleep(0.1)
```

**Why:** First snapshot can take up to 350ms to arrive. On slow connections or heavy CPU load, 0.5s wasn't enough. Extended to 2 seconds with debug logging.

### Fix 3: Graceful Shutdown Sequence

**File:** `ipcom/ipcom_tcp_client.py:1315-1335`

**Before:**
```python
self._persistent_mode = False
self._shutdown_event.set()

# Immediately wait for threads
for thread in [...]:
    thread.join(timeout=2.0)

# Immediately disconnect
self.disconnect()
```

**After:**
```python
self._persistent_mode = False
self._shutdown_event.set()

# Give threads a moment to see the shutdown signal
time.sleep(0.1)

# Then wait for threads to finish
for thread in [...]:
    thread.join(timeout=2.0)

# Finally disconnect
self.disconnect()
```

**Why:** Added 100ms delay after signaling shutdown to let threads exit gracefully before closing the socket.

### Fix 4: Suppress Errors During Shutdown

**File:** `ipcom/ipcom_tcp_client.py:1507-1519`

**Before:**
```python
except socket.error as e:
    self.logger.error(f"Socket error in receive loop: {e}")
    self._cleanup_socket()
```

**After:**
```python
except socket.error as e:
    # Ignore errors if we're shutting down
    if self._persistent_mode and self._connected:
        self.logger.error(f"Socket error in receive loop: {e}")
    self._cleanup_socket()
    if not auto_reconnect or not self._persistent_mode:
        break
```

**Why:** Socket errors during shutdown are expected (socket closed while thread is reading). Only log errors if we're still in persistent mode.

### Fix 5: Improved Config Flow Help Text

**File:** `custom_components/ipcom/translations/en.json:11-15`

**Before:**
```json
"scan_interval": "Update interval (seconds)"
```

**After:**
```json
"scan_interval": "Fallback interval (seconds) - actual updates occur every 350ms via persistent connection",
"data_description": {
  "scan_interval": "This is only used as a fallback if the persistent connection fails. Real-time updates happen every 350ms automatically."
}
```

**Why:** Clarifies that the 10s interval is just a fallback. Real updates happen every 350ms automatically.

## Testing Instructions

### 1. Remove Integration
```
Settings → Devices & Services → IPCom → Delete
```

### 2. Restart Home Assistant
```
Settings → System → Restart
```

### 3. Re-add Integration
```
Settings → Devices & Services → Add Integration → IPCom Home Anywhere Blue
```

**Configuration:**
- CLI Path: `ipcom/ipcom_cli.py` (or full path)
- Host: `megane-david.dyndns.info`
- Port: `5000`
- Scan Interval: `10` (just leave default - it's now clearly labeled as fallback)

### 4. Wait for Startup

**Expected Log Sequence:**
```
INFO Setting up IPCom integration: megane-david.dyndns.info:5000
INFO Persistent connection started: megane-david.dyndns.info:5000 (updates every 350ms)
DEBUG Waiting for first snapshot from persistent connection...
DEBUG Received first snapshot after 0.4s
INFO IPCom integration loaded: XX devices found
INFO Adding XX light entities
INFO Adding XX cover entities
```

### 5. Verify Entities Loaded

- Go to Settings → Devices & Services → IPCom
- Should see all your lights and covers
- Check Developer Tools → States
- Find an IPCom entity (e.g., `light.keuken`)

### 6. Test Real-Time Updates

- Watch an entity state in Developer Tools → States
- Toggle the physical switch
- State should update within 350ms (almost instantly)

### 7. Test Commands

- Toggle a light ON/OFF in Home Assistant
- Should respond instantly (<100ms)
- State should update immediately

## Expected Results

✅ **Startup:**
- Integration loads without errors
- Persistent connection established
- All entities discovered and created
- First snapshot received within 2 seconds

✅ **Operation:**
- State updates every 350ms (visible in Developer Tools)
- Commands execute instantly
- No "Socket error" messages in logs (except during shutdown)

✅ **Shutdown:**
- Clean shutdown when restarting HA
- All background loops stop gracefully
- No errors about bad file descriptors

## Rollback (If Issues Persist)

If problems continue, check:

1. **CLI Path Correct?**
   ```bash
   ls -la ipcom/ipcom_cli.py
   ```

2. **devices.yaml Exists?**
   ```bash
   ls -la ipcom/devices.yaml
   ```

3. **Connection Working?**
   ```bash
   python ipcom/ipcom_cli.py status --host megane-david.dyndns.info --port 5000
   ```

4. **Check Full Logs:**
   ```
   Settings → System → Logs
   # Look for errors with "ipcom" in them
   ```

## Files Modified (This Round)

1. `custom_components/ipcom/coordinator.py` - Thread-safe callbacks, extended wait time
2. `ipcom/ipcom_tcp_client.py` - Graceful shutdown, error suppression
3. `custom_components/ipcom/translations/en.json` - Improved help text

## Summary

The issues were caused by:
1. Thread safety problem (callback in worker thread)
2. Not waiting long enough for first snapshot
3. Race condition during shutdown

All fixed with minimal changes. The persistent connection implementation itself was correct, just needed better integration with Home Assistant's async event loop.

**Status:** ✅ **READY FOR TESTING**

Please restart Home Assistant and re-add the integration to test the fixes!
