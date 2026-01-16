# ✅ Dual Tracking: Memory + Disk PID Files

## Overview

The S3VaultFuseManager now tracks processes in **TWO places**, just like your existing GitHub repository:

1. **In Memory** - Fast runtime tracking with full process information
2. **On Disk** - PID files at `/run/dms/s3/<backup_target_id>.pid` for persistence

## 📁 PID File Structure

### Directory Layout
```
/run/dms/s3/
├── target-123.pid          → Contains: 12345
├── target-456.pid          → Contains: 12346
├── target-789.pid          → Contains: 12347
└── target-abc.pid          → Contains: 12348
```

### PID File Format
```bash
# Each file contains just the PID
cat /run/dms/s3/target-123.pid
12345
```

## 🔄 Complete Lifecycle

### 1. Process Spawn

```python
manager.spawn_s3vaultfuse('target-123', '/var/lib/trilio/mounts/xxx', env)
```

**What Happens:**
```
1. Check if process exists in memory     ← Fast check
2. Check if PID file exists on disk      ← Persistence check
3. If found and alive, load to memory    ← Recovery
4. Otherwise, spawn new process          ← Create new
5. Write PID to memory                   ← Track in RAM
6. Write PID file to disk                ← /run/dms/s3/target-123.pid
7. Log everything                        ← Audit trail
```

**Result:**
- ✅ Process running
- ✅ Tracked in memory: `manager.processes['target-123']`
- ✅ PID file on disk: `/run/dms/s3/target-123.pid`

### 2. Process Kill

```python
manager.kill_s3vaultfuse('target-123')
```

**What Happens:**
```
1. Get PID from memory OR disk           ← Find process
2. Send SIGTERM to process               ← Graceful kill
3. Wait 10 seconds                       ← Give it time
4. Force kill if needed (SIGKILL)        ← Ensure death
5. Remove from memory                    ← Clean RAM
6. Delete PID file from disk             ← Clean disk
7. Log everything                        ← Audit trail
```

**Result:**
- ✅ Process terminated
- ✅ Removed from memory: `'target-123'` deleted
- ✅ PID file removed: `/run/dms/s3/target-123.pid` deleted

### 3. Server Restart

**On Startup:**
```python
# Automatic - happens in __init__
manager = S3VaultFuseManager()
# → Calls _load_existing_pids() automatically
```

**What Happens:**
```
1. Scan /run/dms/s3/ directory           ← Find PID files
2. Read each .pid file                   ← Get PIDs
3. Check if process is alive             ← Verify running
4. If alive: Load into memory            ← Recover tracking
5. If dead: Delete PID file              ← Cleanup stale
6. Log results                           ← Show what was found
```

**Example Log:**
```
Loading existing PID files from /run/dms/s3
Found 4 PID files
✓ Loaded existing process: target=target-123, PID=12345
✓ Loaded existing process: target=target-456, PID=12346
Cleaning up stale PID file: target-old.pid (PID 99999 is dead)
PID file loading complete: loaded=2, cleaned=2
```

## 🔍 Checking Process Status

### Method 1: Manager API (Checks Both)
```python
# Checks memory first, then disk
is_running = manager.is_running('target-123')
```

**Logic:**
```python
def is_running(target_id):
    # 1. Check memory (fast)
    if target_id in memory:
        return is_alive(memory[target_id]['pid'])
    
    # 2. Check disk (fallback)
    pid = read_pid_file(target_id)
    if pid and is_alive(pid):
        load_to_memory(target_id, pid)  # Sync
        return True
    
    return False
```

### Method 2: Direct PID File Check
```bash
# Check if PID file exists
test -f /run/dms/s3/target-123.pid && echo "PID file exists"

# Read PID
cat /run/dms/s3/target-123.pid

# Check if process is running
ps -p $(cat /run/dms/s3/target-123.pid)
```

### Method 3: List All
```bash
# List all PID files
ls -la /run/dms/s3/

# List all tracked in memory
python3 << 'EOF'
from trilio_dms.s3vaultfuse_manager import S3VaultFuseManager
m = S3VaultFuseManager()
for tid in m.processes:
    print(f"{tid}: PID {m.processes[tid]['pid']}")
EOF
```

## 📊 Statistics

```python
stats = manager.get_stats()
print(stats)
```

**Output:**
```python
{
    'total_tracked': 3,              # In memory
    'alive': 3,                      # Alive processes
    'dead': 0,                       # Dead in memory
    'all_pids_ever_spawned': 5,      # Audit trail
    'pid_files_on_disk': 3,          # On disk
    'pid_directory': '/run/dms/s3',  # Location
    'processes': [
        {
            'target_id': 'target-123',
            'pid': 12345,
            'alive': True,
            'pid_file': '/run/dms/s3/target-123.pid',
            'pid_file_exists': True
        },
        ...
    ]
}
```

## 🔧 Synchronization

### Automatic Sync

The manager **automatically** keeps memory and disk in sync:

**Spawn:**
- ✅ Write to memory
- ✅ Write PID file to disk

**Kill:**
- ✅ Remove from memory
- ✅ Delete PID file from disk

**Check:**
- ✅ Check memory first (fast)
- ✅ Fallback to disk if not in memory
- ✅ Load to memory if found on disk

**Startup:**
- ✅ Load all valid PID files into memory
- ✅ Cleanup stale PID files

### Manual Sync

```python
# Cleanup dead processes (syncs both)
cleaned = manager.cleanup_dead_processes()

# This will:
# 1. Find dead processes in memory
# 2. Remove them from memory
# 3. Delete their PID files from disk
```

## 🛠️ Advanced Usage

### Find Orphaned PID Files
```bash
#!/bin/bash
# Find PID files where process is dead

for pidfile in /run/dms/s3/*.pid; do
    if [ -f "$pidfile" ]; then
        pid=$(cat "$pidfile")
        if ! ps -p $pid > /dev/null 2>&1; then
            target=$(basename "$pidfile" .pid)
            echo "Orphaned: $target (PID $pid is dead)"
            rm "$pidfile"
        fi
    fi
done
```

### Monitor Both Sources
```python
#!/usr/bin/env python3
"""Monitor memory and disk tracking"""

import os
from trilio_dms.s3vaultfuse_manager import S3VaultFuseManager

manager = S3VaultFuseManager()

print("=== Memory Tracking ===")
for target_id, info in manager.processes.items():
    print(f"  {target_id}: PID {info['pid']}")

print("\n=== Disk PID Files ===")
for filename in os.listdir(manager.pid_dir):
    if filename.endswith('.pid'):
        target_id = filename[:-4]
        pid_file = os.path.join(manager.pid_dir, filename)
        with open(pid_file, 'r') as f:
            pid = f.read().strip()
        print(f"  {target_id}: PID {pid}")

print("\n=== Comparison ===")
memory_targets = set(manager.processes.keys())
disk_files = {f[:-4] for f in os.listdir(manager.pid_dir) if f.endswith('.pid')}

only_memory = memory_targets - disk_files
only_disk = disk_files - memory_targets
both = memory_targets & disk_files

print(f"  In both: {len(both)}")
print(f"  Only in memory: {len(only_memory)}")
print(f"  Only on disk: {len(only_disk)}")

if only_memory:
    print(f"  WARNING: {only_memory} in memory but not on disk!")
if only_disk:
    print(f"  INFO: {only_disk} on disk but not in memory (will load on check)")
```

### Manual Process Registration
```bash
#!/bin/bash
# Manually register an s3vaultfuse process

TARGET_ID="target-manual"
PID=$(pgrep -f "s3vaultfuse.py.*target-manual")

if [ -n "$PID" ]; then
    echo $PID > /run/dms/s3/${TARGET_ID}.pid
    echo "Registered PID $PID for $TARGET_ID"
    
    # Manager will find it on next check
    python3 << EOF
from trilio_dms.s3vaultfuse_manager import S3VaultFuseManager
m = S3VaultFuseManager()
if m.is_running('$TARGET_ID'):
    print("Process loaded into memory!")
EOF
fi
```

## 🧪 Testing

### Run PID File Tests
```bash
# Run specific PID file tests
python -m pytest tests/test_pid_files.py -v

# Test specific functionality
python -m pytest tests/test_pid_files.py::TestPIDFiles::test_write_and_read_pid_file -v
```

### Manual Testing
```python
#!/usr/bin/env python3
"""Manual test of PID file functionality"""

import os
import time
from trilio_dms.s3vaultfuse_manager import S3VaultFuseManager

# Create manager
manager = S3VaultFuseManager()

# Test write
print("Writing PID file...")
manager._write_pid_file('test-target', 99999)

# Check file exists
pid_file = manager._get_pid_file_path('test-target')
print(f"PID file created: {os.path.exists(pid_file)}")

# Read back
pid = manager._read_pid_file('test-target')
print(f"Read PID: {pid}")

# Delete
manager._delete_pid_file('test-target')
print(f"PID file deleted: {not os.path.exists(pid_file)}")
```

## 📋 Summary

### ✅ Implementation Complete

**Dual Tracking System:**
- ✅ In-memory registry for fast access
- ✅ PID files on disk at `/run/dms/s3/<target_id>.pid`
- ✅ Automatic synchronization between both
- ✅ Loads existing PIDs on startup
- ✅ Cleanup of stale PID files
- ✅ Works exactly like existing GitHub repository

**Key Features:**
- ✅ Persists across server restarts
- ✅ Fast lookups (memory first)
- ✅ Fallback to disk if not in memory
- ✅ Automatic recovery of running processes
- ✅ Cleanup of dead processes and stale files
- ✅ System-wide visibility via PID files
- ✅ Thread-safe operations
- ✅ Comprehensive logging

**Compatibility:**
- ✅ Matches existing Trilio pattern
- ✅ Standard Unix PID file format
- ✅ Works with existing monitoring tools
- ✅ Compatible with manual interventions

### 🎯 Usage

**Just use the manager normally:**
```python
from trilio_dms.s3vaultfuse_manager import S3VaultFuseManager

manager = S3VaultFuseManager()

# Spawn (creates memory + disk)
manager.spawn_s3vaultfuse(target_id, mount_path, env)

# Check (checks both)
is_running = manager.is_running(target_id)

# Kill (removes from both)
manager.kill_s3vaultfuse(target_id)
```

**Everything is tracked automatically in both places!** 🎉
