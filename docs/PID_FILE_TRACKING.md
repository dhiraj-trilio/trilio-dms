# PID File Tracking - `/run/dms/s3/<backup_target_id>.pid`

## Quick Reference

### PID File Location
```
/run/dms/s3/<backup_target_id>.pid
```

### Examples
```bash
# Target: target-123, PID: 12345
/run/dms/s3/target-123.pid → Contains: 12345

# Target: target-prod-001, PID: 23456
/run/dms/s3/target-prod-001.pid → Contains: 23456
```

## Why Dual Tracking?

**Memory Only** ❌
- Lost on server restart
- No external visibility
- Can't recover running processes

**Disk Only** ❌
- Slow lookups
- No resource monitoring
- Limited metadata

**Memory + Disk** ✅
- Fast + Persistent
- Survives restarts
- External visibility
- Rich monitoring
- Best of both worlds!

## How It Works

### Spawn Process
```
User calls spawn()
       ↓
Create process
       ↓
Get PID: 12345
       ↓
┌──────────────────┬─────────────────┐
│   Write Memory   │  Write Disk     │
│   processes[id]  │  /run/dms/...   │
└──────────────────┴─────────────────┘
       ↓
Process tracked in BOTH places
```

### Kill Process
```
User calls kill()
       ↓
Find PID from memory OR disk
       ↓
Terminate process
       ↓
┌──────────────────┬─────────────────┐
│   Clear Memory   │  Delete File    │
│   del processes  │  rm /run/dms... │
└──────────────────┴─────────────────┘
       ↓
Process removed from BOTH places
```

### Server Restart
```
Server starts
       ↓
Scan /run/dms/s3/
       ↓
Find .pid files
       ↓
For each file:
  Read PID
       ↓
  Is process alive?
  ┌───────┴────────┐
  Yes              No
  ↓                ↓
Load to memory   Delete file
```

## Commands

### View All PID Files
```bash
ls -la /run/dms/s3/
```

### Read Specific PID
```bash
cat /run/dms/s3/target-123.pid
```

### Check Process is Running
```bash
PID=$(cat /run/dms/s3/target-123.pid)
ps -p $PID
```

### Find All S3VaultFuse Processes
```bash
ps aux | grep s3vaultfuse
```

### Compare Memory vs Disk
```python
from trilio_dms.s3vaultfuse_manager import S3VaultFuseManager
import os

manager = S3VaultFuseManager()

# In memory
memory_count = len(manager.processes)

# On disk
disk_count = len([f for f in os.listdir('/run/dms/s3') if f.endswith('.pid')])

print(f"Memory: {memory_count}, Disk: {disk_count}")
```

### Cleanup Orphaned Files
```bash
# Find and remove PID files for dead processes
for f in /run/dms/s3/*.pid; do
    pid=$(cat "$f")
    if ! ps -p $pid > /dev/null 2>&1; then
        echo "Removing stale: $f"
        rm "$f"
    fi
done
```

## Python API

### Check Status (Checks Both)
```python
manager.is_running('target-123')
# → Checks memory first, then disk
```

### Get Process Info
```python
info = manager.get_process_info('target-123')
print(info['pid_file'])          # /run/dms/s3/target-123.pid
print(info['pid_file_exists'])   # True/False
```

### Statistics
```python
stats = manager.get_stats()
print(stats['total_tracked'])     # In memory
print(stats['pid_files_on_disk']) # On disk
```

### Manual PID File Operations
```python
# Write
manager._write_pid_file('target-123', 12345)

# Read
pid = manager._read_pid_file('target-123')

# Delete
manager._delete_pid_file('target-123')
```

## Benefits

### 1. Persistence
```
Server crashes/restarts
       ↓
PID files still exist
       ↓
Server starts
       ↓
Loads existing processes
       ↓
Continues tracking
```

### 2. External Visibility
```bash
# Any tool can check
cat /run/dms/s3/target-123.pid

# Standard monitoring
ps -p $(cat /run/dms/s3/target-123.pid)

# Integration with other systems
pidof s3vaultfuse
```

### 3. Recovery
```python
# Process started externally
# PID file created manually
echo 12345 > /run/dms/s3/target-123.pid

# Manager will find it
if manager.is_running('target-123'):
    print("Automatically loaded!")
```

### 4. Debugging
```bash
# List all tracked targets
ls /run/dms/s3/

# Check each one
for f in /run/dms/s3/*.pid; do
    target=$(basename "$f" .pid)
    pid=$(cat "$f")
    echo "$target: PID $pid"
    ps -p $pid
done
```

## Troubleshooting

### PID File Exists but Process Dead
```bash
# Symptom
cat /run/dms/s3/target-123.pid  # Shows: 12345
ps -p 12345  # No such process

# Solution
rm /run/dms/s3/target-123.pid

# Or use manager
python3 << EOF
from trilio_dms.s3vaultfuse_manager import S3VaultFuseManager
m = S3VaultFuseManager()
m.cleanup_dead_processes()
EOF
```

### Process Running but No PID File
```bash
# Find process
PID=$(pgrep -f "s3vaultfuse.*target-123")

# Create PID file
echo $PID > /run/dms/s3/target-123.pid

# Manager will pick it up
```

### Memory and Disk Out of Sync
```python
# This should not happen, but if it does:
from trilio_dms.s3vaultfuse_manager import S3VaultFuseManager

manager = S3VaultFuseManager()

# Force reload from disk
manager._load_existing_pids()

# Cleanup dead entries
manager.cleanup_dead_processes()
```

## Comparison with Existing Repository

### ✅ Same Pattern
Your existing GitHub repository uses:
```
/run/dms/s3/<backup_target_id>.pid
```

Our implementation uses:
```
/run/dms/s3/<backup_target_id>.pid
```

**Identical!** ✅

### ✅ Same Format
Existing: Single line with PID
```
12345
```

Ours: Single line with PID
```
12345
```

**Identical!** ✅

### ✅ Same Behavior
Existing:
- Write on spawn
- Delete on kill
- Load on startup

Ours:
- Write on spawn ✅
- Delete on kill ✅
- Load on startup ✅

**Identical!** ✅

### ➕ Additional Features
We also add:
- ✅ Thread-safe operations
- ✅ Automatic sync between memory and disk
- ✅ Resource monitoring (CPU, memory)
- ✅ Comprehensive logging
- ✅ Python API access
- ✅ Statistics and monitoring
- ✅ Automatic dead process cleanup

## Best Practices

### 1. Let Manager Handle It
```python
# Good - Manager handles both automatically
manager.spawn_s3vaultfuse(target_id, path, env)

# Don't manually create PID files unless necessary
```

### 2. Check Both Sources
```python
# Good - Checks both automatically
is_running = manager.is_running(target_id)

# Avoid checking just one source
```

### 3. Use Cleanup
```python
# Regular cleanup
manager.cleanup_dead_processes()

# Full cleanup on shutdown
manager.cleanup_all()
```

### 4. Monitor Regularly
```bash
# Cron job to check sync
*/5 * * * * /usr/local/bin/check_dms_pids.sh
```

## Summary

✅ **PID files at:** `/run/dms/s3/<backup_target_id>.pid`

✅ **Tracked in:** Memory AND Disk

✅ **Automatic:** Sync, load, cleanup

✅ **Compatible:** With existing repository

✅ **Enhanced:** More features, better monitoring

**Just use the manager - everything is tracked automatically!** 🎯
