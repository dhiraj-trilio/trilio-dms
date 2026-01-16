# ✅ Yes, All S3 Processes Are Fully Tracked!

## Dual Tracking System: Memory + Disk

### 🎯 How We Track

**EVERY s3vaultfuse process is tracked in TWO places:**

1. **In Memory** (fast access, runtime tracking)
2. **On Disk** (persistence across restarts)

### 📁 PID Files on Disk

**Location:** `/run/dms/s3/<backup_target_id>.pid`

**Example:**
```
/run/dms/s3/target-123.pid         → Contains: 12345
/run/dms/s3/target-456.pid         → Contains: 12346
/run/dms/s3/target-789.pid         → Contains: 12347
```

**Benefits:**
- ✅ Survives DMS server restarts
- ✅ Can track existing processes
- ✅ System-wide process registry
- ✅ Easy external monitoring
- ✅ Compatible with existing Trilio patterns

### 💾 In-Memory Registry

**Structure:**
```python
manager.processes = {
    'target-123': {
        'pid': 12345,
        'process': <subprocess.Popen>,
        'target_id': 'target-123',
        'mount_path': '/var/lib/trilio/...',
        'start_time': datetime(...),
        'env_keys': ['vault_s3_bucket', ...],
        'status': 'running',
        'loaded_from_disk': False  # True if loaded from PID file
    },
    ...
}
```

**Benefits:**
- ✅ Fast lookups (O(1))
- ✅ Real-time monitoring
- ✅ Resource tracking (CPU, memory)
- ✅ Direct process control

## 🔄 Process Lifecycle with Dual Tracking

### 1. Spawn Process

```python
manager.spawn_s3vaultfuse(target_id, mount_path, env)
```

**Steps:**
1. ✅ Check if already running (memory)
2. ✅ Check if PID file exists (disk)
3. ✅ If exists and alive, load into memory
4. ✅ Otherwise, spawn new process
5. ✅ Write PID to disk: `/run/dms/s3/<target_id>.pid`
6. ✅ Store in memory registry
7. ✅ Log everything

**Logged:**
```
✓ s3vaultfuse spawned successfully for target target-123
  PID: 12345
  Mount path: /var/lib/trilio/triliovault-mounts/xxx
  PID file: /run/dms/s3/target-123.pid
  Start time: 2024-01-01 12:00:00
  Total tracked processes: 5
```

### 2. Kill Process

```python
manager.kill_s3vaultfuse(target_id)
```

**Steps:**
1. ✅ Get PID from memory or disk
2. ✅ Send SIGTERM (graceful)
3. ✅ Wait 10 seconds
4. ✅ Force kill if needed
5. ✅ Remove from memory
6. ✅ Delete PID file from disk
7. ✅ Log everything

**Logged:**
```
Killing s3vaultfuse process for target target-123
  PID: 12345
✓ PID file deleted: /run/dms/s3/target-123.pid
✓ s3vaultfuse process killed for target target-123
```

### 3. Server Restart

**On Startup:**
```python
manager._load_existing_pids()
```

**Steps:**
1. ✅ Scan `/run/dms/s3/` directory
2. ✅ Read all `.pid` files
3. ✅ Check if processes are alive
4. ✅ Load alive processes into memory
5. ✅ Clean up dead PID files
6. ✅ Log results

**Logged:**
```
Loading existing PID files from /run/dms/s3
Found 3 PID files
✓ Loaded existing process: target=target-123, PID=12345
✓ Loaded existing process: target=target-456, PID=12346
Cleaning up stale PID file: target-789.pid (PID 12347 is dead)
PID file loading complete: loaded=2, cleaned=1
```

### 4. Check if Running

```python
is_running = manager.is_running(target_id)
```

**Checks in order:**
1. ✅ Memory registry first (fast)
2. ✅ PID file on disk if not in memory
3. ✅ Verify process is actually alive
4. ✅ Load into memory if found on disk

## 📊 Monitoring with Dual Tracking

### View PID Files
```bash
# List all PID files
ls -la /run/dms/s3/

# Output:
# -rw-r--r-- 1 root root 5 Jan 01 12:00 target-123.pid
# -rw-r--r-- 1 root root 5 Jan 01 12:15 target-456.pid
# -rw-r--r-- 1 root root 5 Jan 01 12:30 target-789.pid

# Read specific PID file
cat /run/dms/s3/target-123.pid
# Output: 12345
```

### Check Process from PID File
```bash
# Get PID
PID=$(cat /run/dms/s3/target-123.pid)

# Check if running
ps -p $PID

# Get process details
ps aux | grep $PID
```

### Statistics Include Both
```python
stats = manager.get_stats()
# Returns:
{
    'total_tracked': 5,           # In memory
    'alive': 4,
    'dead': 1,
    'pid_files_on_disk': 5,       # On disk
    'pid_directory': '/run/dms/s3',
    'processes': [
        {
            'target_id': 'target-123',
            'pid': 12345,
            'pid_file': '/run/dms/s3/target-123.pid',
            'pid_file_exists': True,  # Confirmed on disk
            'alive': True
        },
        ...
    ]
}
```

### Process Info Shows Both
```python
info = manager.get_process_info('target-123')
# Returns:
{
    'pid': 12345,
    'target_id': 'target-123',
    'mount_path': '/var/lib/trilio/...',
    'pid_file': '/run/dms/s3/target-123.pid',  # Disk location
    'pid_file_exists': True,                    # File exists
    'loaded_from_disk': False,                  # Spawned or loaded?
    'alive': True,
    'cpu_percent': 2.5,
    'memory_mb': 145.2
}
```

## 🔍 Troubleshooting with Dual Tracking

### Orphaned PID Files
```bash
# Find PID files with dead processes
for pidfile in /run/dms/s3/*.pid; do
    pid=$(cat "$pidfile")
    if ! ps -p $pid > /dev/null; then
        echo "Stale: $pidfile (PID $pid is dead)"
        rm "$pidfile"
    fi
done
```

### Memory vs Disk Mismatch
```python
# Cleanup dead processes (syncs memory with disk)
manager.cleanup_dead_processes()

# This will:
# 1. Find dead processes in memory
# 2. Remove from memory
# 3. Delete PID files from disk
```

### Manual Process Recovery
```bash
# If you manually started s3vaultfuse
PID=$(pgrep -f "s3vaultfuse.py /var/lib/trilio/...")

# Create PID file
echo $PID > /run/dms/s3/target-123.pid

# Manager will pick it up on next check or restart
```

## 🎯 Key Benefits of Dual Tracking

### Memory Tracking
- ✅ **Fast:** O(1) lookups
- ✅ **Rich:** Full process objects, resource stats
- ✅ **Real-time:** Live monitoring
- ✅ **Control:** Direct process management

### Disk Tracking  
- ✅ **Persistent:** Survives restarts
- ✅ **Portable:** Standard Unix pattern
- ✅ **Compatible:** Works with existing tools
- ✅ **Simple:** Just PID in a file
- ✅ **System-wide:** Visible to all processes

### Combined
- ✅ **Reliable:** Two sources of truth
- ✅ **Recoverable:** Can reload from disk
- ✅ **Synchronized:** Automatically kept in sync
- ✅ **Auditable:** Full tracking history

## 📝 Example Usage

### Check Both Sources
```python
# Check memory
in_memory = 'target-123' in manager.processes

# Check disk
pid_file = '/run/dms/s3/target-123.pid'
on_disk = os.path.exists(pid_file)

# Check if actually running
is_running = manager.is_running('target-123')  # Checks both!

print(f"In memory: {in_memory}")
print(f"On disk: {on_disk}")
print(f"Running: {is_running}")
```

### Manual Cleanup
```python
# Cleanup specific target (memory + disk)
manager.kill_s3vaultfuse('target-123')

# Cleanup all dead processes
manager.cleanup_dead_processes()

# Cleanup everything
manager.cleanup_all()
```

### Monitoring Script
```bash
#!/bin/bash
# Monitor PID files and memory

echo "=== PID Files on Disk ==="
ls -la /run/dms/s3/

echo -e "\n=== Processes in Memory ==="
python3 << EOF
from trilio_dms.server import DMSServer
server = DMSServer()
for proc in server.s3vaultfuse_manager.list_all_processes():
    print(f"{proc['target_id']}: PID {proc['pid']}, File exists: {proc['pid_file_exists']}")
EOF

echo -e "\n=== Statistics ==="
python3 << EOF
from trilio_dms.server import DMSServer
server = DMSServer()
stats = server.s3vaultfuse_manager.get_stats()
print(f"Memory: {stats['total_tracked']} tracked, {stats['alive']} alive")
print(f"Disk: {stats['pid_files_on_disk']} PID files")
EOF
```

## ✅ Summary

**We track processes in TWO ways for maximum reliability:**

1. **Memory (Runtime)**
   - Fast access
   - Rich information
   - Real-time monitoring

2. **Disk (Persistent)**
   - `/run/dms/s3/<target_id>.pid`
   - Survives restarts
   - System-wide visibility

**Both are automatically synchronized!**

- ✅ Spawn: Write to memory AND disk
- ✅ Kill: Remove from memory AND disk
- ✅ Check: Query memory first, fallback to disk
- ✅ Restart: Reload from disk into memory
- ✅ Cleanup: Sync both sources

**Just like the existing GitHub repository!** 🎯
