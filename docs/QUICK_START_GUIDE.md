# Trilio DMS - Quick Start Guide

Get started with Trilio DMS in 10 minutes!

## What is Trilio DMS?

Trilio DMS (Dynamic Mount Service) is a centralized system for managing mount/unmount operations for backup targets (S3, NFS). It separates concerns between:

- **DMS Client**: Manages database, sends requests (integrate in your app)
- **DMS Server**: Executes mounts, tracks processes (runs on compute nodes)

## 30-Second Overview

```
Your App → DMS Client → RabbitMQ → DMS Server → Mount S3/NFS
              ↓
            MySQL
           (Ledger)
```

## Prerequisites

- Python 3.8+
- MySQL 5.7+
- RabbitMQ 3.8+
- Root access on compute nodes (for mounts)

## Step 1: Install (5 minutes)

### Install Package

```bash
pip install trilio-dms

# Or from source
git clone https://github.com/dhiraj-trilio/trilio-dms.git
cd trilio-dms
pip install -e .
```

### Setup Database

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

### Setup RabbitMQ

```bash
# Create user
sudo rabbitmqctl add_user dms_user dms_password
sudo rabbitmqctl set_permissions -p / dms_user ".*" ".*" ".*"
```

## Step 2: Start DMS Server (2 minutes)

On each compute node:

```bash
# Set environment
export DMS_RABBITMQ_URL="amqp://dms_user:dms_password@rabbitmq-host:5672"
export DMS_NODE_ID="compute-01"
export DMS_AUTH_URL="http://keystone:5000/v3"

# Start server
trilio-dms-server

# Or as systemd service
sudo systemctl start trilio-dms-server
```

## Step 3: Use DMS Client (3 minutes)

In your backup application:

```python
from trilio_dms.client import DMSClient, MountContext

# Initialize client
client = DMSClient(
    db_url='mysql+pymysql://dms_user:dms_password@localhost/trilio_dms',
    rabbitmq_url='amqp://dms_user:dms_password@localhost:5672'
)

# Prepare request
request = {
    'context': {
        'user_id': 'user-123',
        'tenant_id': 'tenant-456'
    },
    'keystone_token': 'your-keystone-token',
    'job': {
        'jobid': 12345,  # INTEGER
        'progress': 0,
        'status': 'running',
        'action': 'backup',
        'job_details': []
    },
    'host': 'compute-01',
    'backup_target': {
        'id': 'target-123',
        'type': 's3',
        'filesystem_export_mount_path': '/var/lib/trilio/triliovault-mounts/xxx',
        'secret_ref': 'http://barbican:9311/v1/secrets/uuid'
    }
}

# Mount and backup (automatic unmount)
with MountContext(client, request) as mount:
    # Mount is ready at mount.get_mount_path()
    perform_your_backup(mount.get_mount_path())
    # Automatic unmount on exit

client.close()
```

## Complete Example

### S3 Backup

```python
#!/usr/bin/env python3
import os
from trilio_dms.client import DMSClient, MountContext

# Initialize
client = DMSClient(
    db_url=os.getenv('DMS_DB_URL'),
    rabbitmq_url=os.getenv('DMS_RABBITMQ_URL')
)

# S3 target configuration
s3_target = {
    'id': 'target-s3-prod',
    'type': 's3',
    'filesystem_export_mount_path': '/var/lib/trilio/triliovault-mounts/s3-prod',
    'secret_ref': 'http://barbican:9311/v1/secrets/s3-creds'
}

# Request
request = {
    'context': {'user_id': 'user-123', 'tenant_id': 'tenant-456'},
    'keystone_token': os.getenv('KEYSTONE_TOKEN'),
    'job': {
        'jobid': 12345,
        'progress': 0,
        'status': 'running',
        'action': 'backup',
        'job_details': [{'id': 'vm-001', 'data': {'vm_id': 'vm-001'}}]
    },
    'host': 'compute-01',
    'backup_target': s3_target
}

# Execute backup
try:
    with MountContext(client, request) as mount:
        print(f"✓ Mounted at: {mount.get_mount_path()}")
        
        # Your backup logic here
        backup_path = os.path.join(mount.get_mount_path(), 'backup-vm-001')
        os.makedirs(backup_path, exist_ok=True)
        # ... copy data to backup_path ...
        
        print(f"✓ Backup completed")
except Exception as e:
    print(f"✗ Backup failed: {e}")
finally:
    client.close()
```

### NFS Backup

```python
# NFS target configuration
nfs_target = {
    'id': 'target-nfs-prod',
    'type': 'nfs',
    'filesystem_export': '192.168.1.100:/backups',
    'filesystem_export_mount_path': '/var/lib/trilio/triliovault-mounts/nfs-prod',
    'nfs_mount_opts': 'rw,sync,hard,intr,nfsvers=4'
}

# Use same pattern as S3
request['backup_target'] = nfs_target
with MountContext(client, request) as mount:
    perform_backup(mount.get_mount_path())
```

## Verification

### Check Server is Running

```bash
# System status
systemctl status trilio-dms-server

# View logs
journalctl -u trilio-dms-server -f

# Check processes
ps aux | grep trilio-dms-server
```

### Check Mounts

```bash
# List all s3vaultfuse processes
python scripts/monitor_s3vaultfuse.py

# Check mount points
df -h | grep trilio

# View PID files
ls -la /run/dms/s3/
```

### Query Database

```python
from trilio_dms.client import DMSClient

client = DMSClient()

# Check active mounts
active = client.get_active_mounts()
print(f"Active mounts: {len(active)}")

# Check specific mount
status = client.get_mount_status(job_id=12345, backup_target_id='target-123')
print(f"Mounted: {status.mounted if status else 'Not found'}")

client.close()
```

## Common Operations

### Manual Mount/Unmount

```python
from trilio_dms.client import DMSClient

client = DMSClient()

# Mount
response = client.mount(request)
if response['status'] == 'success':
    print(f"✓ {response['success_msg']}")

# ... do work ...

# Unmount
request['action'] = 'unmount'
response = client.unmount(request)
if response['status'] == 'success':
    print(f"✓ {response['success_msg']}")

client.close()
```

### List Active Mounts

```python
from trilio_dms.client import DMSClient

client = DMSClient()
active = client.get_active_mounts()

for mount in active:
    print(f"{mount.backup_target_id}: Job {mount.jobid}, Host {mount.host}")

client.close()
```

### View Mount History

```python
from trilio_dms.client import DMSClient

client = DMSClient()
history = client.get_ledger_history('target-123', limit=10)

for entry in history:
    print(f"{entry.created_at}: Job {entry.jobid}, Mounted={entry.mounted}")

client.close()
```

## Troubleshooting

### Mount Fails

**Problem:** Mount operation fails

**Solution:**
```bash
# Check server logs
journalctl -u trilio-dms-server -n 50

# Check server is running
ps aux | grep trilio-dms-server

# Check RabbitMQ
rabbitmqctl list_queues | grep dms

# Check credentials
curl -H "X-Auth-Token: $TOKEN" http://barbican:9311/v1/secrets
```

### Timeout Error

**Problem:** Request times out

**Solution:**
```python
# Increase timeout
client = DMSClient(timeout=600)  # 10 minutes

# Check server is responsive
# systemctl status trilio-dms-server
```

### Process Not Tracked

**Problem:** s3vaultfuse process not showing

**Solution:**
```bash
# Check PID files
ls -la /run/dms/s3/

# Reload processes
python3 << EOF
from trilio_dms.server import DMSServer
s = DMSServer()
s.s3vaultfuse_manager._load_existing_pids()
EOF
```

## Next Steps

### Production Deployment

1. **Setup systemd services** for automatic startup
2. **Configure monitoring** for processes and mounts
3. **Setup log rotation** for server logs
4. **Create backup** of PID directory
5. **Implement alerting** for mount failures

### Read More

- [DMS Server README](docs/DMS_SERVER_README.md) - Detailed server guide
- [DMS Client README](docs/DMS_CLIENT_README.md) - Detailed client guide
- [Process Tracking](docs/PROCESS_TRACKING.md) - How process tracking works
- [Main README](README.md) - Complete documentation

## Getting Help

- **Issues**: https://github.com/dhiraj-trilio/trilio-dms/issues
- **Docs**: https://github.com/dhiraj-trilio/trilio-dms#readme
- **Logs**: 
  - Server: `journalctl -u trilio-dms-server`
  - Client: Check your application logs

## Summary

✅ **Install** - Install package and setup database
✅ **Start Server** - Run on compute nodes
✅ **Use Client** - Integrate in your app

**That's it! You're ready to use Trilio DMS!** 🚀

### Quick Reference

```python
# Basic pattern
from trilio_dms.client import DMSClient, MountContext

client = DMSClient()

with MountContext(client, request) as mount:
    # Do backup at mount.get_mount_path()
    pass

client.close()
```

**Happy mounting!** 🎯
