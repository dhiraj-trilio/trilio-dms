# DMS Client Request Structure Reference

## 📋 Mount Request Structure

```python
mount_request = {
    'job': {
        'jobid': 12345  # Integer - job identifier
    },
    'backup_target': {
        'id': 'target-001',  # String - backup target identifier
        'type': 's3',  # String - backup target type (s3, nfs, etc.)
        
        # Mount path - REQUIRED field
        'filesystem_export_mount_path': '/mnt/backup-target-001',
        
        # Filesystem export info
        'filesystem_export': '/export/path',  # Optional
        
        # Additional fields based on type
        'bucket_name': 'my-backup-bucket',  # For S3
        'region': 'us-east-1',  # For S3
        # ... other type-specific fields
    },
    'host': 'compute-01',  # String - target host for mount
    'token': 'auth-token-xyz'  # Optional - authentication token
}
```

## 📋 Unmount Request Structure

```python
unmount_request = {
    'job': {
        'jobid': 12345  # Integer - same job that mounted
    },
    'backup_target': {
        'id': 'target-001',  # String - same target ID
        'type': 's3',  # String - backup target type
        
        # Mount path is used for verification/logging
        'filesystem_export_mount_path': '/mnt/backup-target-001',
        
        # Filesystem export info
        'filesystem_export': '/export/path'  # Optional
    },
    'host': 'compute-01',  # String - same host
    'token': 'auth-token-xyz'  # Optional
}
```

## 🔑 Key Fields

### Required Fields

| Field | Location | Type | Description |
|-------|----------|------|-------------|
| `jobid` | `job.jobid` | Integer | Job identifier (composite key) |
| `id` | `backup_target.id` | String | Backup target ID (composite key) |
| `type` | `backup_target.type` | String | Target type (s3, nfs, etc.) |
| `filesystem_export_mount_path` | `backup_target.filesystem_export_mount_path` | String | **Mount path location** |
| `host` | `host` | String | Target host (composite key) |

### Optional Fields

| Field | Location | Type | Description |
|-------|----------|------|-------------|
| `filesystem_export` | `backup_target.filesystem_export` | String | Export path |
| `token` | `token` | String | Authentication token |
| Additional fields | `backup_target.*` | Various | Type-specific config |

## 📝 Mount Path Handling

### Where Mount Path Comes From

```python
# Client receives request with mount path
request = {
    'backup_target': {
        'id': 'target-001',
        'filesystem_export_mount_path': '/mnt/target-001'  # ← Provided by caller
    }
}

# Client uses this path directly (no config lookup)
mount_path = request['backup_target']['filesystem_export_mount_path']

# Returns in response
response = {
    'status': 'success',
    'mount_path': '/mnt/target-001'  # ← Same path from request
}
```

### Flow Diagram

```
Request Body
    ↓
backup_target.filesystem_export_mount_path = '/mnt/target-001'
    ↓
DMS Client (uses this path directly)
    ↓
Response
    ↓
mount_path = '/mnt/target-001' (returned to caller)
```

## 💡 Usage Examples

### Example 1: S3 Target Mount

```python
from trilio_dms.client import DMSClient

client = DMSClient()

request = {
    'job': {'jobid': 12345},
    'backup_target': {
        'id': 's3-backup-001',
        'type': 's3',
        'filesystem_export_mount_path': '/mnt/s3-backup-001',  # ← Mount location
        'filesystem_export': 's3://my-bucket/backups',
        'bucket_name': 'my-backup-bucket',
        'region': 'us-east-1',
        'access_key': 'AKIA...',
        'secret_key': '***'
    },
    'host': 'compute-01'
}

response = client.mount(request)
# response['mount_path'] = '/mnt/s3-backup-001'
```

### Example 2: NFS Target Mount

```python
request = {
    'job': {'jobid': 12346},
    'backup_target': {
        'id': 'nfs-backup-001',
        'type': 'nfs',
        'filesystem_export_mount_path': '/mnt/nfs-backup-001',  # ← Mount location
        'filesystem_export': '192.168.1.100:/exports/backups',
        'nfs_version': '4',
        'mount_options': 'rw,sync'
    },
    'host': 'compute-02'
}

response = client.mount(request)
# response['mount_path'] = '/mnt/nfs-backup-001'
```

### Example 3: Multiple Jobs, Same Target

```python
# Job 1001 mounts
request_1001 = {
    'job': {'jobid': 1001},
    'backup_target': {
        'id': 'shared-target',
        'type': 's3',
        'filesystem_export_mount_path': '/mnt/shared-target'  # ← Same path
    },
    'host': 'compute-01'
}
client.mount(request_1001)

# Job 1002 mounts same target
request_1002 = {
    'job': {'jobid': 1002},
    'backup_target': {
        'id': 'shared-target',
        'type': 's3',
        'filesystem_export_mount_path': '/mnt/shared-target'  # ← Same path
    },
    'host': 'compute-01'
}
response = client.mount(request_1002)
# response['reused_existing'] = True (mount already exists)
```

## 🔍 Field Validation

The client expects these fields to be present:

```python
# Required structure validation
assert 'job' in request
assert 'jobid' in request['job']
assert 'backup_target' in request
assert 'id' in request['backup_target']
assert 'filesystem_export_mount_path' in request['backup_target']
assert 'host' in request
```

## 🎯 Common Patterns

### Pattern 1: Building Request from Job Config

```python
def build_mount_request(job_config, backup_target_config):
    """Build mount request from configuration."""
    return {
        'job': {
            'jobid': job_config['id']
        },
        'backup_target': {
            'id': backup_target_config['id'],
            'type': backup_target_config['type'],
            'filesystem_export_mount_path': backup_target_config['mount_path'],
            'filesystem_export': backup_target_config.get('export'),
            **backup_target_config.get('credentials', {})
        },
        'host': job_config['target_host']
    }
```

### Pattern 2: Using with Context Manager

```python
from trilio_dms.client import MountContext

# Build request
request = {
    'job': {'jobid': 12345},
    'backup_target': {
        'id': 'target-001',
        'type': 's3',
        'filesystem_export_mount_path': '/mnt/target-001'  # ← Mount path
    },
    'host': 'compute-01'
}

# Use context manager
with MountContext(client, request) as ctx:
    # ctx.mount_path = '/mnt/target-001' (from request)
    perform_backup(ctx.mount_path)
```

### Pattern 3: Unmount After Work

```python
# Mount
mount_request = {
    'job': {'jobid': 12345},
    'backup_target': {
        'id': 'target-001',
        'filesystem_export_mount_path': '/mnt/target-001'
    },
    'host': 'compute-01'
}
mount_response = client.mount(mount_request)

# Do work using mount_response['mount_path']
perform_backup(mount_response['mount_path'])

# Unmount (same structure)
unmount_request = mount_request.copy()
unmount_response = client.unmount(unmount_request)
```

## ⚠️ Important Notes

1. **Mount Path Source**: Always comes from `backup_target.filesystem_export_mount_path` in request
2. **No Config Lookup**: Client does NOT look up mount paths in config files
3. **Caller Responsibility**: The caller must provide the correct mount path
4. **Path Consistency**: Same path must be used for mount and unmount requests
5. **Composite Key**: (jobid, backup_target_id, host) uniquely identifies a mount

## 🔧 Debugging

### Check What Path Was Used

```python
response = client.mount(request)

if response['status'] == 'success':
    print(f"Mounted at: {response['mount_path']}")
    # This will be the same as:
    print(f"Original path: {request['backup_target']['filesystem_export_mount_path']}")
    # They should match!
```

### Verify Request Structure

```python
def validate_mount_request(request):
    """Validate request has all required fields."""
    required_fields = [
        ('job', 'jobid'),
        ('backup_target', 'id'),
        ('backup_target', 'filesystem_export_mount_path'),
        ('host',)
    ]
    
    for field_path in required_fields:
        obj = request
        for key in field_path:
            if key not in obj:
                raise ValueError(f"Missing required field: {'.'.join(field_path)}")
            obj = obj[key] if len(field_path) > 1 else None
    
    return True
```

## 📊 Complete Example Flow

```python
from trilio_dms.client import DMSClient, MountContext

# 1. Prepare request with mount path
request = {
    'job': {'jobid': 12345},
    'backup_target': {
        'id': 'target-001',
        'type': 's3',
        'filesystem_export_mount_path': '/mnt/target-001',  # ← From config/database
        'filesystem_export': 's3://bucket/path',
        'bucket_name': 'my-bucket'
    },
    'host': 'compute-01'
}

# 2. Initialize client
client = DMSClient()

# 3. Mount using context manager
with MountContext(client, request) as ctx:
    # 4. Use the mount path
    mount_path = ctx.mount_path  # = '/mnt/target-001'
    
    print(f"Performing backup at {mount_path}")
    backup_files(mount_path)
    
    # 5. Automatic unmount on exit
    
print("Done!")
```
