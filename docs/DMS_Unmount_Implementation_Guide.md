# DMS Client Unmount Implementation Guide

## Overview

This implementation provides a robust unmount mechanism for the Trilio DMS (Dynamic Mount Service) with the following key features:

1. **Global Locking**: Ensures only one process can perform mount/unmount operations at a time on the same server
2. **Smart Unmount Logic**: Checks if other jobs are using the same mount before physically unmounting
3. **Ledger Management**: Properly tracks mount states across multiple concurrent jobs
4. **Thread-Safe**: Uses file-based locking (flock) for cross-process synchronization

## Architecture

```
┌─────────────┐         ┌──────────────────┐         ┌─────────────┐
│  Process 1  │         │   Global Lock    │         │  Process 2  │
│ (DMS Client)│────────▶│  (/var/lock/)    │◀────────│ (DMS Client)│
└─────────────┘         └──────────────────┘         └─────────────┘
       │                                                      │
       │                                                      │
       ▼                                                      ▼
┌────────────────────────────────────────────────────────────────┐
│                    Mount Ledger Database                       │
│  ┌──────────────────────────────────────────────────────┐     │
│  │  job_id │ backup_target_id │ host │ mounted │ path   │     │
│  ├─────────┼──────────────────┼──────┼─────────┼────────┤     │
│  │ job-001 │    target-001    │ c-01 │  true   │ /mnt/1 │     │
│  │ job-002 │    target-001    │ c-01 │  true   │ /mnt/1 │     │
│  │ job-003 │    target-002    │ c-01 │  true   │ /mnt/2 │     │
│  └──────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Lock Manager (`lock_manager.py`)

Manages file-based locks for serializing mount/unmount operations across multiple processes.

**Features:**
- Uses `fcntl.flock()` for reliable cross-process locking
- Configurable timeout for lock acquisition
- Automatic cleanup on context exit
- Singleton pattern for global access

### 2. Enhanced DMS Client (`client.py`)

The main client interface with intelligent unmount logic.

**Unmount Flow:**
```
1. Acquire global lock
2. Query mount ledger for active mounts (mounted=True)
3. Count active mounts for (backup_target_id, host)
4. IF count == 1 AND belongs to current job:
   └─▶ Send unmount request to DMS server
   └─▶ Mark ledger entry as mounted=False
5. ELIF count > 1:
   └─▶ Skip physical unmount (other jobs using it)
   └─▶ Mark ledger entry as mounted=False
6. Release lock
```

### 3. Database Model (`models.py`)

Tracks mount state across all jobs with composite primary key and efficient indexes.

## Installation

### 1. Add Files to Your Repository

Place the provided files in your `trilio-dms` repository:

```
trilio-dms/
├── trilio_dms/
│   ├── __init__.py
│   ├── client.py          # Enhanced with unmount logic
│   ├── lock_manager.py    # NEW - Global locking
│   ├── models.py          # Enhanced with indexes
│   └── context_manager.py # Enhanced context manager
└── tests/
    └── test_unmount_with_lock.py  # NEW - Comprehensive tests
```

### 2. Update Database Schema

Run migration to add indexes (if using Alembic):

```python
# alembic/versions/xxx_add_mount_ledger_indexes.py
def upgrade():
    op.create_index(
        'idx_target_host_mounted',
        'backup_target_mount_ledger',
        ['backup_target_id', 'host', 'mounted']
    )
    op.create_index(
        'idx_job_id',
        'backup_target_mount_ledger',
        ['job_id']
    )
```

Or manually:

```sql
CREATE INDEX idx_target_host_mounted 
ON backup_target_mount_ledger(backup_target_id, host, mounted);

CREATE INDEX idx_job_id 
ON backup_target_mount_ledger(job_id);
```

### 3. Install Dependencies

Ensure your `requirements.txt` includes:

```
sqlalchemy>=1.4.0
fcntl  # Built-in on Unix systems
```

## Usage Examples

### Basic Usage

```python
from trilio_dms import DMSClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup database session
engine = create_engine('mysql://user:pass@localhost/trilio_dms')
Session = sessionmaker(bind=engine)
session = Session()

# Create DMS client
client = DMSClient(
    rabbitmq_url='amqp://user:pass@localhost:5672',
    db_session=session,
    lock_timeout=300  # 5 minutes
)

# Unmount a backup target
result = client.unmount_backup_target(
    job_id='job-12345',
    backup_target_id='target-67890',
    host='compute-01'
)

print(f"Success: {result['success']}")
print(f"Physically unmounted: {result['unmounted']}")
print(f"Message: {result['message']}")
```

### Using Context Manager (Recommended)

```python
from trilio_dms import DMSClient, mount_context

# Automatic mount/unmount with proper cleanup
with mount_context(client, job_id, target_id, host, token) as mount:
    # Mount is ready at mount.mount_path
    print(f"Mounted at: {mount['mount_path']}")
    
    # Perform backup operations
    perform_backup(mount['mount_path'])
    
    # Automatic unmount on exit (even if exception occurs)
```

### Concurrent Job Scenario

```python
# Multiple jobs using same backup target
jobs = ['job-001', 'job-002', 'job-003']
target_id = 'shared-target'
host = 'compute-01'

# All jobs mount the same target
for job_id in jobs:
    with mount_context(client, job_id, target_id, host, token) as mount:
        perform_backup(mount['mount_path'])
        # When job-001 exits, mount stays active (job-002 & job-003 using it)
        # When job-002 exits, mount stays active (job-003 using it)
        # When job-003 exits, mount is physically unmounted (last user)
```

### Error Handling

```python
from trilio_dms import DMSClient

try:
    result = client.unmount_backup_target(
        job_id='job-123',
        backup_target_id='target-456',
        host='compute-01'
    )
    
    if result['success']:
        if result['unmounted']:
            print("Target physically unmounted")
        else:
            print(f"Ledger updated, {result['active_mounts_remaining']} jobs still using mount")
    else:
        print(f"Unmount failed: {result['message']}")
        
except TimeoutError as e:
    print(f"Could not acquire lock: {e}")
    # Retry or alert
    
except Exception as e:
    print(f"Unexpected error: {e}")
    # Log and handle
```

## Configuration

### Environment Variables

```bash
# Lock configuration
export DMS_LOCK_DIR="/var/lock/trilio-dms"
export DMS_LOCK_TIMEOUT=300  # seconds

# Database configuration
export DMS_DB_URL="mysql://user:pass@localhost/trilio_dms"

# RabbitMQ configuration
export DMS_RABBITMQ_URL="amqp://user:pass@localhost:5672"
```

### Lock Directory Permissions

Ensure the lock directory has proper permissions:

```bash
sudo mkdir -p /var/lock/trilio-dms
sudo chmod 755 /var/lock/trilio-dms
sudo chown trilio:trilio /var/lock/trilio-dms
```

## Testing

### Run Unit Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run all tests
pytest tests/test_unmount_with_lock.py -v

# Run with coverage
pytest tests/test_unmount_with_lock.py --cov=trilio_dms --cov-report=html
```

### Test Scenarios Covered

1. **Single Mount Unmount**: Verify physical unmount when only one job has target mounted
2. **Multiple Mounts**: Verify physical unmount is skipped when other jobs are using target
3. **Last of Multiple**: Verify physical unmount when last remaining job unmounts
4. **Lock Serialization**: Verify concurrent operations are properly serialized
5. **Lock Timeout**: Verify timeout behavior when lock cannot be acquired
6. **Concurrent Different Targets**: Verify operations on different targets can proceed

### Manual Testing

```python
# Test 1: Single job unmount
import logging
logging.basicConfig(level=logging.INFO)

client = DMSClient(...)
result = client.unmount_backup_target('job-1', 'target-1', 'host-1')
# Expected: Physical unmount occurs

# Test 2: Multiple jobs
# Setup: Create 3 mount ledger entries for same target/host
result1 = client.unmount_backup_target('job-1', 'target-1', 'host-1')
# Expected: No physical unmount, 2 active mounts remaining

result2 = client.unmount_backup_target('job-2', 'target-1', 'host-1')
# Expected: No physical unmount, 1 active mount remaining

result3 = client.unmount_backup_target('job-3', 'target-1', 'host-1')
# Expected: Physical unmount occurs, 0 active mounts remaining
```

## Monitoring and Logging

### Enable Detailed Logging

```python
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Enable DMS client logging
dms_logger = logging.getLogger('trilio_dms')
dms_logger.setLevel(logging.DEBUG)
```

### Log Messages to Monitor

- `Successfully acquired lock for mount_unmount` - Lock acquired
- `Found N active mount(s) for ...` - Active mount count
- `Single active mount detected. Sending unmount request` - Physical unmount triggered
- `Multiple active mounts (N) detected. Skipping physical unmount` - Shared mount detected
- `Could not acquire lock after N seconds` - Lock timeout

### Metrics to Track

1. **Lock Wait Time**: Time spent waiting to acquire lock
2. **Mount Count**: Number of active mounts per target/host
3. **Unmount Skips**: Count of skipped physical unmounts (indicates sharing)
4. **Lock Timeouts**: Number of timeout errors (indicates contention)

## Troubleshooting

### Issue: Lock Timeout Errors

**Symptoms**: `TimeoutError: Could not acquire lock after 300 seconds`

**Causes:**
- Another process holding lock too long
- Stale lock file from crashed process
- Lock timeout too short for operation duration

**Solutions:**
```bash
# Check for stale lock files
ls -la /var/lock/trilio-dms/

# Remove stale lock (if process is confirmed dead)
rm /var/lock/trilio-dms/dms_mount_unmount.lock

# Increase timeout in configuration
export DMS_LOCK_TIMEOUT=600  # 10 minutes
```

### Issue: Ledger Entry Not Found

**Symptoms**: `No active mount found for this job`

**Causes:**
- Job never mounted the target
- Ledger entry already marked as unmounted
- Database synchronization issue

**Solutions:**
```python
# Query ledger manually
from trilio_dms.models import BackupTargetMountLedger

entries = session.query(BackupTargetMountLedger).filter_by(
    job_id='job-123'
).all()

for entry in entries:
    print(f"Job: {entry.job_id}, Mounted: {entry.mounted}")
```

### Issue: Physical Unmount Not Occurring

**Symptoms**: Mount remains after all jobs complete

**Causes:**
- Ledger entries not properly updated to `mounted=False`
- Other hidden jobs still using the mount
- Database transaction not committed

**Solutions:**
```python
# Audit mount ledger
active_mounts = session.query(BackupTargetMountLedger).filter_by(
    backup_target_id='target-1',
    host='host-1',
    mounted=True
).all()

print(f"Active mounts: {len(active_mounts)}")
for mount in active_mounts:
    print(f"  Job: {mount.job_id}")

# Force cleanup if needed (use with caution)
for mount in active_mounts:
    mount.mounted = False
session.commit()
```

## Performance Considerations

### Lock Contention

With multiple processes attempting mount/unmount operations:

- **Low Contention** (< 10 processes): Lock wait time typically < 1 second
- **Medium Contention** (10-50 processes): Lock wait time 1-10 seconds
- **High Contention** (> 50 processes): Consider implementing lock queuing

### Database Query Optimization

The implementation uses indexed queries for efficiency:

```sql
-- Optimized query used by unmount operation
SELECT * FROM backup_target_mount_ledger
WHERE backup_target_id = ? 
  AND host = ? 
  AND mounted = true;
-- Uses index: idx_target_host_mounted
```

### Scaling Recommendations

For large deployments (> 100 concurrent jobs):

1. **Use Connection Pooling**: Configure SQLAlchemy connection pool
   ```python
   engine = create_engine(
       db_url,
       pool_size=20,
       max_overflow=40
   )
   ```

2. **Implement Lock Priority**: Priority queue for critical operations
3. **Partition by Host**: Separate lock files per host for better concurrency
4. **Monitor Lock Metrics**: Track lock acquisition times and timeouts

## Migration Guide

### From Existing Implementation

If you have an existing unmount implementation:

1. **Add Global Lock Manager**:
   ```python
   # Old code
   result = unmount_target(target_id, host)
   
   # New code
   with lock_manager.acquire_lock():
       result = unmount_target(target_id, host)
   ```

2. **Update Unmount Logic**:
   Replace direct unmount calls with the new ledger-aware unmount:
   ```python
   # Old code
   def unmount(target_id, host):
       send_rpc_unmount(target_id, host)
   
   # New code
   def unmount(job_id, target_id, host):
       active_count = count_active_mounts(target_id, host)
       if active_count == 1:
           send_rpc_unmount(target_id, host)
       update_ledger(job_id, mounted=False)
   ```

3. **Test Migration**:
   - Run existing tests with new implementation
   - Verify no regression in mount/unmount behavior
   - Add new tests for concurrent scenarios

## Best Practices

1. **Always Use Context Manager**: Ensures proper cleanup even on errors
2. **Configure Appropriate Timeouts**: Balance between responsiveness and operation duration
3. **Monitor Lock Metrics**: Track contention and adjust configuration
4. **Regular Ledger Cleanup**: Periodically clean old ledger entries
5. **Log All Operations**: Essential for troubleshooting concurrent issues
6. **Handle Timeouts Gracefully**: Implement retry logic with exponential backoff

## FAQ

**Q: What happens if a process crashes while holding the lock?**
A: The lock is automatically released when the file descriptor is closed (process termination). The lock file remains but doesn't block other processes.

**Q: Can multiple hosts use the same lock directory?**
A: No, locks are per-host. Each host needs its own lock directory (typically `/var/lock/trilio-dms`).

**Q: How long should the lock timeout be?**
A: Default 5 minutes (300s) is reasonable. Adjust based on your mount/unmount operation duration. Monitor actual times and set timeout to 2-3x the typical duration.

**Q: What if two jobs start unmounting simultaneously?**
A: The global lock ensures operations are serialized. The first job acquires the lock, completes its unmount, then releases. The second job then acquires the lock and proceeds.

**Q: Can I use this with remote/shared mounts?**
A: Yes, the implementation tracks mounts by (backup_target_id, host) combination, supporting any mount type including remote/shared mounts.

## Support

For issues or questions:
- Check logs for detailed error messages
- Review the test suite for usage examples
- Consult the inline code documentation
- Open an issue in the GitHub repository
