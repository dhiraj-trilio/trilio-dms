# DMS Client - User Guide

## Overview

The **DMS Client** is your interface to the DMS system. It manages the database ledger and sends mount/unmount requests to DMS Servers via RabbitMQ. Integrate it into your backup application to handle all mount operations.

## Key Responsibilities

- ✅ Manage `backup_target_mount_ledger` database table
- ✅ Send mount/unmount requests to DMS Server
- ✅ Track mount operations in database
- ✅ Update ledger with mount status
- ✅ Query mount history and status
- ❌ **NO mount operations** (handled by DMS Server)

## Architecture

```
┌──────────────┐        ┌─────────────┐        ┌──────────────┐
│    Your      │───────►│  DMS Client │───────►│   RabbitMQ   │
│  Backup App  │        │             │        │              │
└──────────────┘        │  DB Access  │        └──────────────┘
                        └──────┬──────┘
                               │
                        ┌──────▼──────┐
                        │    MySQL    │
                        │   (Ledger)  │
                        └─────────────┘
```

## Installation

### System Requirements

- Python 3.8+
- MySQL 5.7+ or MariaDB 10.3+
- RabbitMQ 3.8+

### Install Dependencies

```bash
# Install DMS package
pip install trilio-dms

# Or from source
git clone https://github.com/dhiraj-trilio/trilio-dms.git
cd trilio-dms
pip install -e .
```

### Database Setup

```bash
# Create database
mysql -u root -p << EOF
CREATE DATABASE trilio_dms;
CREATE USER 'dms_user'@'%' IDENTIFIED BY 'dms_password';
GRANT ALL PRIVILEGES ON trilio_dms.* TO 'dms_user'@'%';
FLUSH PRIVILEGES;
EOF

# Import schema
mysql -u dms_user -p trilio_dms < schema.sql
```

## Configuration

### Environment Variables

```bash
# Required
export DMS_DB_URL="mysql+pymysql://dms_user:dms_password@localhost:3306/trilio_dms"
export DMS_RABBITMQ_URL="amqp://dms_user:dms_password@localhost:5672"

# Optional
export DMS_REQUEST_TIMEOUT="300"
export DMS_LOG_LEVEL="INFO"
export KEYSTONE_TOKEN="your-token"
```

### Configuration File

Create `~/.trilio-dms/client.conf`:

```ini
[client]
db_url = mysql+pymysql://dms_user:dms_password@localhost:3306/trilio_dms
rabbitmq_url = amqp://dms_user:dms_password@localhost:5672
timeout = 300
log_level = INFO
```

## Basic Usage

### Initialize Client

```python
from trilio_dms.client import DMSClient

# Using environment variables
client = DMSClient()

# Or with explicit configuration
client = DMSClient(
    db_url='mysql+pymysql://user:pass@localhost/trilio_dms',
    rabbitmq_url='amqp://user:pass@localhost:5672',
    timeout=300
)
```

### Mount a Backup Target

```python
# Prepare request
request = {
    'context': {
        'user_id': 'user-123',
        'tenant_id': 'tenant-456',
        'project_id': 'project-789'
    },
    'keystone_token': 'your-keystone-token',
    'job': {
        'jobid': 12345,  # INTEGER
        'progress': 0,
        'status': 'running',
        'completed_at': None,
        'action': 'backup',
        'parent_jobid': None,
        'job_details': [
            {
                'id': 'vm-detail-1',
                'data': {'vm_id': 'vm-001', 'vm_name': 'web-server'}
            }
        ]
    },
    'host': 'compute-01',
    'action': 'mount',
    'backup_target': {
        'id': 'target-123',
        'deleted': False,
        'type': 's3',  # or 'nfs'
        'filesystem_export': None,  # For NFS: '192.168.1.100:/export'
        'filesystem_export_mount_path': '/var/lib/trilio/triliovault-mounts/xxx',
        'status': 'available',
        'secret_ref': 'http://barbican:9311/v1/secrets/uuid',  # For S3
        'nfs_mount_opts': None  # For NFS: 'rw,sync,hard'
    }
}

# Execute mount
response = client.mount(request)

if response['status'] == 'success':
    print(f"✓ {response['success_msg']}")
else:
    print(f"✗ {response['error_msg']}")
```

### Unmount a Backup Target

```python
# Same request, just change action
request['action'] = 'unmount'

response = client.unmount(request)

if response['status'] == 'success':
    print(f"✓ {response['success_msg']}")
else:
    print(f"✗ {response['error_msg']}")
```

### Using Context Manager (Recommended)

```python
from trilio_dms.client import MountContext

# Automatic mount/unmount
with MountContext(client, request) as mount:
    # Mount is ready
    print(f"Mounted at: {mount.get_mount_path()}")
    
    # Perform your backup operations
    perform_backup(mount.get_mount_path())
    
    # Automatic unmount when exiting
```

## Advanced Usage

### Check Mount Status

```python
# Get status for specific job and target
status = client.get_mount_status(
    job_id=12345,
    backup_target_id='target-123'
)

if status:
    print(f"Mounted: {status.mounted}")
    print(f"Host: {status.host}")
    print(f"Created: {status.created_at}")
else:
    print("No mount record found")
```

### List Active Mounts

```python
# All active mounts
active_mounts = client.get_active_mounts()

# Filter by host
active_mounts = client.get_active_mounts(host='compute-01')

# Filter by target
active_mounts = client.get_active_mounts(backup_target_id='target-123')

# Display
for mount in active_mounts:
    print(f"Target: {mount.backup_target_id}")
    print(f"  Job: {mount.jobid}")
    print(f"  Host: {mount.host}")
    print(f"  Mounted: {mount.mounted}")
    print(f"  Created: {mount.created_at}")
```

### View Mount History

```python
# Get history for a target
history = client.get_ledger_history(
    backup_target_id='target-123',
    limit=20
)

for entry in history:
    print(f"{entry.created_at}: Job {entry.jobid}, Mounted: {entry.mounted}")
```

### Soft Delete Entry

```python
# Soft delete (sets deleted=True)
success = client.soft_delete_entry(
    job_id=12345,
    backup_target_id='target-123'
)
```

## Request Format

### Complete Request Structure

```python
{
    # User context
    'context': {
        'user_id': '<user_id>',
        'tenant_id': '<tenant_id>',
        'project_id': '<project_id>',
        'request_id': '<request_id>'
    },
    
    # Keystone token for Barbican access
    'keystone_token': '<token>',
    
    # Job information
    'job': {
        'jobid': 12345,  # INTEGER (not string!)
        'progress': 0,  # 0-100
        'status': 'running',  # running|completed|failed
        'completed_at': None,  # datetime or None
        'action': 'backup',  # backup|restore|etc
        'parent_jobid': None,  # parent job ID or None
        'job_details': [
            {
                'id': '<detail_id>',
                'data': {
                    'vm_id': 'vm-001',
                    'vm_name': 'web-server',
                    # ... other data
                }
            }
        ]
    },
    
    # Target compute node
    'host': 'compute-01',
    
    # Action to perform
    'action': 'mount',  # or 'unmount'
    
    # Backup target configuration
    'backup_target': {
        'id': 'target-123',
        'deleted': False,
        'type': 's3',  # or 'nfs'
        
        # For NFS
        'filesystem_export': '192.168.1.100:/backups',  # NFS export
        'filesystem_export_mount_path': '/var/lib/trilio/triliovault-mounts/xxx',
        'nfs_mount_opts': 'rw,sync,hard,intr,nfsvers=4',
        
        # For S3
        'secret_ref': 'http://barbican:9311/v1/secrets/uuid',
        
        'status': 'available'
    }
}
```

### S3 Backup Target Example

```python
request = {
    'context': {'user_id': 'user-123', 'tenant_id': 'tenant-456'},
    'keystone_token': 'gAAAAABxxx...',
    'job': {
        'jobid': 12345,
        'progress': 0,
        'status': 'running',
        'action': 'backup',
        'job_details': []
    },
    'host': 'compute-01',
    'action': 'mount',
    'backup_target': {
        'id': 'target-s3-prod',
        'type': 's3',
        'deleted': False,
        'status': 'available',
        'filesystem_export': None,
        'filesystem_export_mount_path': '/var/lib/trilio/triliovault-mounts/s3-prod',
        'secret_ref': 'http://barbican:9311/v1/secrets/abc-123',
        'nfs_mount_opts': None
    }
}
```

### NFS Backup Target Example

```python
request = {
    'context': {'user_id': 'user-123', 'tenant_id': 'tenant-456'},
    'keystone_token': 'gAAAAABxxx...',
    'job': {
        'jobid': 12346,
        'progress': 0,
        'status': 'running',
        'action': 'backup',
        'job_details': []
    },
    'host': 'compute-01',
    'action': 'mount',
    'backup_target': {
        'id': 'target-nfs-prod',
        'type': 'nfs',
        'deleted': False,
        'status': 'available',
        'filesystem_export': '192.168.1.100:/backups',
        'filesystem_export_mount_path': '/var/lib/trilio/triliovault-mounts/nfs-prod',
        'secret_ref': None,
        'nfs_mount_opts': 'rw,sync,hard,intr,nfsvers=4'
    }
}
```

## Response Format

All methods return a standardized response:

```python
{
    'status': 'success',  # or 'error'
    'error_msg': None,    # Error message if status='error'
    'success_msg': 'S3 target mounted successfully at /var/lib/trilio/...'
}
```

**Success Example:**
```python
{
    'status': 'success',
    'error_msg': None,
    'success_msg': 'S3 target mounted successfully at /var/lib/trilio/triliovault-mounts/xxx'
}
```

**Error Example:**
```python
{
    'status': 'error',
    'error_msg': 'Mount failed: Permission denied',
    'success_msg': None
}
```

## Integration Examples

### Full Backup Workflow

```python
import os
from trilio_dms.client import DMSClient, MountContext

class BackupManager:
    def __init__(self):
        self.dms_client = DMSClient()
    
    def backup_vm(self, vm_id, backup_target, job_id):
        """Backup a VM to a backup target"""
        
        # Prepare DMS request
        request = {
            'context': {
                'user_id': os.getenv('USER_ID'),
                'tenant_id': os.getenv('TENANT_ID')
            },
            'keystone_token': os.getenv('KEYSTONE_TOKEN'),
            'job': {
                'jobid': job_id,
                'progress': 0,
                'status': 'running',
                'action': 'backup',
                'job_details': [
                    {'id': vm_id, 'data': {'vm_id': vm_id}}
                ]
            },
            'host': os.uname().nodename,
            'backup_target': backup_target
        }
        
        try:
            # Use context manager for automatic cleanup
            with MountContext(self.dms_client, request) as mount:
                mount_path = mount.get_mount_path()
                print(f"Backing up VM {vm_id} to {mount_path}")
                
                # Perform backup
                self.create_snapshot(vm_id)
                self.copy_to_target(vm_id, mount_path)
                self.create_metadata(vm_id, mount_path)
                
                print(f"Backup completed for VM {vm_id}")
                return True
                
        except Exception as e:
            print(f"Backup failed: {e}")
            return False
        
        finally:
            self.dms_client.close()
    
    def create_snapshot(self, vm_id):
        """Create VM snapshot"""
        # Your snapshot logic
        pass
    
    def copy_to_target(self, vm_id, mount_path):
        """Copy data to backup target"""
        # Your copy logic
        pass
    
    def create_metadata(self, vm_id, mount_path):
        """Create backup metadata"""
        # Your metadata logic
        pass

# Usage
manager = BackupManager()
success = manager.backup_vm(
    vm_id='vm-001',
    backup_target={
        'id': 'target-123',
        'type': 's3',
        'filesystem_export_mount_path': '/var/lib/trilio/triliovault-mounts/xxx',
        'secret_ref': 'http://barbican:9311/v1/secrets/uuid'
    },
    job_id=12345
)
```

### Restore Workflow

```python
def restore_vm(self, vm_id, backup_id, backup_target, job_id):
    """Restore a VM from backup"""
    
    request = {
        'context': {
            'user_id': os.getenv('USER_ID'),
            'tenant_id': os.getenv('TENANT_ID')
        },
        'keystone_token': os.getenv('KEYSTONE_TOKEN'),
        'job': {
            'jobid': job_id,
            'progress': 0,
            'status': 'running',
            'action': 'restore',
            'job_details': [
                {
                    'id': vm_id,
                    'data': {
                        'vm_id': vm_id,
                        'backup_id': backup_id
                    }
                }
            ]
        },
        'host': os.uname().nodename,
        'backup_target': backup_target
    }
    
    try:
        with MountContext(self.dms_client, request) as mount:
            mount_path = mount.get_mount_path()
            print(f"Restoring VM {vm_id} from {mount_path}")
            
            # Perform restore
            backup_data = self.read_backup(backup_id, mount_path)
            self.restore_vm_data(vm_id, backup_data)
            
            print(f"Restore completed for VM {vm_id}")
            return True
            
    except Exception as e:
        print(f"Restore failed: {e}")
        return False
```

### Monitoring Mounts

```python
def monitor_mounts(self):
    """Monitor all active mounts"""
    
    client = DMSClient()
    
    # Get all active mounts
    active = client.get_active_mounts()
    
    print(f"Active mounts: {len(active)}")
    for mount in active:
        print(f"\nTarget: {mount.backup_target_id}")
        print(f"  Job: {mount.jobid}")
        print(f"  Host: {mount.host}")
        print(f"  Created: {mount.created_at}")
        print(f"  Updated: {mount.updated_at}")
    
    client.close()
```

## Database Schema

The client manages the `backup_target_mount_ledger` table:

```sql
CREATE TABLE backup_target_mount_ledger (
    id INT AUTO_INCREMENT PRIMARY KEY,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at DATETIME NULL,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    version VARCHAR(32),
    backup_target_id VARCHAR(255) NOT NULL,
    jobid INT NOT NULL,
    host VARCHAR(255) NOT NULL,
    mounted BOOLEAN NOT NULL DEFAULT FALSE,
    
    INDEX idx_backup_target_id (backup_target_id),
    INDEX idx_jobid (jobid),
    INDEX idx_host (host),
    INDEX idx_job_target (jobid, backup_target_id),
    INDEX idx_mounted_host (mounted, host),
    INDEX idx_deleted (deleted)
);
```

### Query Examples

```python
# Get mount status
status = client.get_mount_status(job_id=12345, backup_target_id='target-123')

# Active mounts on specific host
active = client.get_active_mounts(host='compute-01')

# History for target
history = client.get_ledger_history(backup_target_id='target-123', limit=10)
```

## Error Handling

### Common Errors

**RequestValidationException:**
```python
try:
    response = client.mount(request)
except RequestValidationException as e:
    print(f"Invalid request: {e}")
```

**RequestTimeoutException:**
```python
try:
    response = client.mount(request)
except RequestTimeoutException as e:
    print(f"Request timed out: {e}")
    # DMS Server might be down or queue is full
```

**DatabaseException:**
```python
try:
    client = DMSClient()
except DatabaseException as e:
    print(f"Database error: {e}")
    # Check database connectivity and credentials
```

**RabbitMQException:**
```python
try:
    client = DMSClient()
except RabbitMQException as e:
    print(f"RabbitMQ error: {e}")
    # Check RabbitMQ connectivity
```

### Handling Mount Failures

```python
response = client.mount(request)

if response['status'] == 'error':
    error_msg = response['error_msg']
    
    if 'Permission denied' in error_msg:
        print("Check mount permissions")
    elif 'timeout' in error_msg.lower():
        print("Server not responding")
    elif 'credentials' in error_msg.lower():
        print("Check Barbican credentials")
    else:
        print(f"Mount failed: {error_msg}")
```

## Troubleshooting

### Database Connection Issues

```python
# Test database connection
from sqlalchemy import create_engine

try:
    engine = create_engine('mysql+pymysql://user:pass@host/db')
    conn = engine.connect()
    print("✓ Database connection successful")
    conn.close()
except Exception as e:
    print(f"✗ Database connection failed: {e}")
```

### RabbitMQ Connection Issues

```python
# Test RabbitMQ connection
import pika

try:
    connection = pika.BlockingConnection(
        pika.URLParameters('amqp://user:pass@host:5672')
    )
    print("✓ RabbitMQ connection successful")
    connection.close()
except Exception as e:
    print(f"✗ RabbitMQ connection failed: {e}")
```

### Request Timeout

```python
# Increase timeout
client = DMSClient(timeout=600)  # 10 minutes

# Or check server is running
# ps aux | grep trilio-dms-server
```

### Mount Not Updating

```python
# Check ledger entry
status = client.get_mount_status(job_id, target_id)
print(f"Mounted: {status.mounted}")
print(f"Updated: {status.updated_at}")

# Verify server processed request
# Check server logs: journalctl -u trilio-dms-server
```

## Best Practices

### 1. Always Use Context Manager

```python
# ✓ Good - Automatic cleanup
with MountContext(client, request) as mount:
    perform_backup(mount.get_mount_path())

# ✗ Bad - Manual cleanup required
response = client.mount(request)
try:
    perform_backup(path)
finally:
    client.unmount(request)
```

### 2. Handle Errors Gracefully

```python
try:
    with MountContext(client, request) as mount:
        perform_backup(mount.get_mount_path())
except DMSClientException as e:
    logger.error(f"DMS error: {e}")
    notify_admin(e)
except Exception as e:
    logger.error(f"Backup failed: {e}")
    raise
```

### 3. Close Client Connection

```python
client = DMSClient()
try:
    # Use client
    response = client.mount(request)
finally:
    client.close()  # Important!
```

### 4. Monitor Active Mounts

```python
# Periodically check for orphaned mounts
def check_orphaned_mounts():
    client = DMSClient()
    active = client.get_active_mounts()
    
    for mount in active:
        age = datetime.utcnow() - mount.created_at
        if age > timedelta(hours=24):
            logger.warning(f"Long-running mount: {mount.backup_target_id}")
    
    client.close()
```

### 5. Use Proper Job IDs

```python
# ✓ Good - Integer job ID
request['job']['jobid'] = 12345

# ✗ Bad - String job ID
request['job']['jobid'] = 'job-12345'  # Will cause error!
```

## Performance Tips

### Connection Pooling

```python
# Reuse client instance
class BackupService:
    def __init__(self):
        self.client = DMSClient()
    
    def backup(self, vm_id):
        # Reuse same client
        response = self.client.mount(request)
    
    def __del__(self):
        self.client.close()
```

### Batch Operations

```python
# Process multiple backups with same client
client = DMSClient()

for vm in vms:
    request = prepare_request(vm)
    
    with MountContext(client, request) as mount:
        backup_vm(vm, mount.get_mount_path())

client.close()
```

## API Reference

### DMSClient

```python
class DMSClient:
    def __init__(self, db_url=None, rabbitmq_url=None, timeout=None):
        """Initialize DMS Client"""
    
    def mount(self, request: dict) -> dict:
        """Send mount request"""
    
    def unmount(self, request: dict) -> dict:
        """Send unmount request"""
    
    def get_mount_status(self, job_id: int, backup_target_id: str):
        """Get mount status from ledger"""
    
    def get_active_mounts(self, host=None, backup_target_id=None):
        """Get all active mounts"""
    
    def get_ledger_history(self, backup_target_id: str, limit: int = 100):
        """Get mount history"""
    
    def soft_delete_entry(self, job_id: int, backup_target_id: str) -> bool:
        """Soft delete ledger entry"""
    
    def close(self):
        """Close connections"""
```

### MountContext

```python
class MountContext:
    def __init__(self, client: DMSClient, request: dict):
        """Initialize mount context"""
    
    def __enter__(self):
        """Mount on enter"""
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Unmount on exit"""
    
    def get_mount_path(self) -> str:
        """Get mount path"""
```

## Support

For issues or questions:
- GitHub Issues: https://github.com/dhiraj-trilio/trilio-dms/issues
- Documentation: https://github.com/dhiraj-trilio/trilio-dms#readme

## See Also

- [DMS Server README](DMS_SERVER_README.md)
- [Main README](../README.md)
- [Examples](../examples/)
