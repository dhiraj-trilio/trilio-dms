# DMS Server - User Guide

## Overview

The **DMS Server** is responsible for handling mount/unmount operations for S3 and NFS backup targets. It runs on each compute node and listens to RabbitMQ for mount/unmount requests.

## Key Responsibilities

- ✅ Listen to RabbitMQ for mount/unmount requests
- ✅ Execute mount operations (S3 via s3vaultfuse, NFS via mount)
- ✅ Execute unmount operations
- ✅ Fetch credentials from Barbican
- ✅ Track all s3vaultfuse processes (memory + disk)
- ✅ Return standardized responses
- ❌ **NO database access** (handled by DMS Client)

## Architecture

```
┌─────────────┐         ┌──────────────┐
│  RabbitMQ   │◄───────►│  DMS Server  │
│   Queue     │         │              │
└─────────────┘         │  No DB!      │
                        └──────┬───────┘
                               │
                    ┌──────────┼──────────┐
                    │          │          │
               ┌────▼───┐ ┌───▼────┐ ┌──▼────┐
               │Barbican│ │ Mounts │ │ PIDs  │
               │(Secrets)│ │/var/lib│ │/run/  │
               └────────┘ └────────┘ └───────┘
```

## Installation

### System Requirements

- Python 3.8+
- Ubuntu 22.04 or RHEL 8+
- Root/sudo access (for mount operations)
- s3fs-fuse or s3vaultfuse (for S3 mounts)
- nfs-common/nfs-utils (for NFS mounts)

### Install System Dependencies

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install -y \
    python3 \
    python3-pip \
    s3fs \
    nfs-common
```

#### RHEL/CentOS
```bash
sudo yum install -y \
    python3 \
    python3-pip \
    s3fs-fuse \
    nfs-utils
```

### Install Trilio S3VaultFuse

```bash
# Install Trilio s3vaultfuse package
# Ensure /usr/bin/s3vaultfuse.py exists
which s3vaultfuse.py
```

### Install DMS Server

```bash
# From source
git clone https://github.com/dhiraj-trilio/trilio-dms.git
cd trilio-dms
pip install -e .

# Or from package
pip install trilio-dms
```

## Configuration

### Environment Variables

Create a configuration file or set environment variables:

```bash
# Required
export DMS_RABBITMQ_URL="amqp://dms_user:dms_password@rabbitmq-host:5672"
export DMS_NODE_ID="compute-01"
export DMS_AUTH_URL="http://keystone:5000/v3"

# Optional
export DMS_MOUNT_BASE="/var/lib/trilio/triliovault-mounts"
export DMS_LOG_LEVEL="INFO"
```

### Configuration File

Create `/etc/trilio-dms/server.conf`:

```ini
[server]
rabbitmq_url = amqp://dms_user:dms_password@rabbitmq-host:5672
node_id = compute-01
auth_url = http://keystone:5000/v3
mount_base_path = /var/lib/trilio/triliovault-mounts
log_level = INFO
```

## Running the Server

### Command Line

```bash
# Basic usage
trilio-dms-server

# With environment variables
DMS_RABBITMQ_URL=amqp://localhost:5672 \
DMS_NODE_ID=compute-01 \
trilio-dms-server

# With debug logging
DMS_LOG_LEVEL=DEBUG trilio-dms-server
```

### As Systemd Service

Create `/etc/systemd/system/trilio-dms-server.service`:

```ini
[Unit]
Description=Trilio DMS Server
After=network.target rabbitmq-server.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/trilio-dms
Environment="DMS_RABBITMQ_URL=amqp://dms_user:dms_password@localhost:5672"
Environment="DMS_NODE_ID=compute-01"
Environment="DMS_AUTH_URL=http://keystone:5000/v3"
Environment="DMS_MOUNT_BASE=/var/lib/trilio/triliovault-mounts"
ExecStart=/usr/local/bin/trilio-dms-server
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable trilio-dms-server
sudo systemctl start trilio-dms-server
sudo systemctl status trilio-dms-server
```

### Docker

```bash
docker run -d \
  --name trilio-dms-server \
  --privileged \
  --network host \
  -e DMS_RABBITMQ_URL=amqp://localhost:5672 \
  -e DMS_NODE_ID=compute-01 \
  -e DMS_AUTH_URL=http://keystone:5000/v3 \
  -v /var/lib/trilio/triliovault-mounts:/var/lib/trilio/triliovault-mounts:shared \
  -v /run/dms:/run/dms \
  trilio/dms-server:latest
```

## How It Works

### Request Flow

```
1. Client sends request to RabbitMQ
        ↓
2. Server receives from queue: dms.{node_id}
        ↓
3. Server processes request:
   - Mount: Spawn s3vaultfuse or mount NFS
   - Unmount: Kill process and unmount
        ↓
4. Server sends response back to client
```

### Mount Request Processing

**For S3:**
```
1. Receive mount request
2. Fetch credentials from Barbican
3. Prepare environment variables
4. Spawn s3vaultfuse process
5. Track process (memory + PID file)
6. Verify mount successful
7. Return success/error response
```

**For NFS:**
```
1. Receive mount request
2. Extract NFS export and options
3. Execute mount command
4. Verify mount successful
5. Return success/error response
```

### Unmount Request Processing

**For S3:**
```
1. Receive unmount request
2. Kill s3vaultfuse process (SIGTERM → SIGKILL)
3. Remove PID file
4. Execute umount command
5. Return success/error response
```

**For NFS:**
```
1. Receive unmount request
2. Execute umount command (with force/lazy fallbacks)
3. Return success/error response
```

## Request Format

The server expects requests in this format:

```python
{
    'context': {
        'user_id': 'user-123',
        'tenant_id': 'tenant-456'
    },
    'keystone_token': 'your-keystone-token',
    'job': {
        'jobid': 12345,
        'progress': 0,
        'status': 'running',
        'completed_at': None,
        'action': 'backup',
        'parent_jobid': None,
        'job_details': [...]
    },
    'host': 'compute-01',
    'action': 'mount',  # or 'unmount'
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
```

## Response Format

The server returns responses in this format:

```python
{
    'status': 'success',  # or 'error'
    'error_msg': None,    # Error message if failed
    'success_msg': 'S3 target mounted successfully at /var/lib/trilio/...'
}
```

## Process Tracking

### PID Files

The server tracks all s3vaultfuse processes using PID files:

**Location:** `/run/dms/s3/<backup_target_id>.pid`

**Example:**
```bash
# List all tracked processes
ls -la /run/dms/s3/

# Output:
# -rw-r--r-- 1 root root 5 Jan 01 12:00 target-123.pid
# -rw-r--r-- 1 root root 5 Jan 01 12:15 target-456.pid
```

### Monitor Processes

```bash
# List all s3vaultfuse processes
python scripts/monitor_s3vaultfuse.py

# Watch continuously
python scripts/monitor_s3vaultfuse.py --watch

# Detailed view
python scripts/monitor_s3vaultfuse.py --detailed

# Kill specific process
python scripts/monitor_s3vaultfuse.py --kill 12345
```

### Python API

```python
from trilio_dms.server import DMSServer

server = DMSServer()

# Check if process is running
is_running = server.s3vaultfuse_manager.is_running('target-123')

# Get process info
info = server.s3vaultfuse_manager.get_process_info('target-123')
print(f"PID: {info['pid']}, CPU: {info['cpu_percent']}%")

# List all processes
processes = server.s3vaultfuse_manager.list_all_processes()

# Get statistics
stats = server.s3vaultfuse_manager.get_stats()
print(f"Total: {stats['total_tracked']}, Alive: {stats['alive']}")

# Cleanup dead processes
cleaned = server.s3vaultfuse_manager.cleanup_dead_processes()
```

## Environment Variables for S3VaultFuse

When mounting S3, the server automatically sets these environment variables:

```bash
vault_s3_bucket=trilio-qa
vault_s3_region_name=us-west-2
vault_s3_auth_version=DEFAULT
vault_s3_signature_version=default
vault_s3_ssl=true
vault_s3_ssl_verify=true
vault_storage_nfs_export=trilio-qa
bucket_object_lock=false
use_manifest_suffix=false
vault_s3_ssl_cert=
vault_s3_endpoint_url=
vault_s3_max_pool_connections=500
vault_data_directory_old=/var/triliovault
vault_data_directory=/var/lib/trilio/triliovault-mounts/xxx
log_config_append=/etc/triliovault-object-store/object_store_logging.conf
helper_command=sudo /usr/bin/workloadmgr-rootwrap /etc/triliovault-wlm/rootwrap.conf privsep-helper
AWS_ACCESS_KEY_ID=<from_barbican>
AWS_SECRET_ACCESS_KEY=<from_barbican>
```

## Monitoring

### Logs

```bash
# View server logs (systemd)
sudo journalctl -u trilio-dms-server -f

# View server logs (docker)
docker logs -f trilio-dms-server

# View server logs (file)
tail -f /var/log/trilio-dms/server.log
```

### Log Messages

**Successful Mount:**
```
INFO - Spawning s3vaultfuse for target target-123
INFO - ✓ s3vaultfuse spawned successfully for target target-123
INFO -   PID: 12345
INFO -   Mount path: /var/lib/trilio/triliovault-mounts/xxx
INFO -   PID file: /run/dms/s3/target-123.pid
INFO -   Total tracked processes: 5
```

**Successful Unmount:**
```
INFO - Killing s3vaultfuse process for target target-123
INFO -   PID: 12345
INFO -   Uptime: 1:23:45
INFO - ✓ s3vaultfuse process killed for target target-123
INFO - ✓ PID file deleted: /run/dms/s3/target-123.pid
```

### Health Checks

```bash
# Check server is running
systemctl status trilio-dms-server

# Check RabbitMQ queue
rabbitmqctl list_queues | grep dms.

# Check mounts
df -h | grep trilio

# Check processes
ps aux | grep s3vaultfuse
```

## Troubleshooting

### Server Won't Start

**Problem:** Server fails to start

**Solutions:**
```bash
# Check RabbitMQ connectivity
telnet rabbitmq-host 5672

# Check credentials
rabbitmqctl list_users

# Check logs
journalctl -u trilio-dms-server -n 50

# Validate configuration
python3 -c "from trilio_dms.config import DMSConfig; DMSConfig.validate_server_config()"
```

### Mount Fails

**Problem:** Mount operation fails

**Solutions:**
```bash
# Check s3vaultfuse binary exists
which s3vaultfuse.py

# Check mount directory permissions
ls -la /var/lib/trilio/triliovault-mounts/

# Check Barbican connectivity
curl -H "X-Auth-Token: $TOKEN" http://barbican:9311/v1/secrets

# Check logs for error details
journalctl -u trilio-dms-server | grep -A 10 "Mount failed"

# Test manual mount
AWS_ACCESS_KEY_ID=xxx AWS_SECRET_ACCESS_KEY=yyy \
/usr/bin/s3vaultfuse.py /tmp/test-mount
```

### Process Not Tracked

**Problem:** s3vaultfuse process not showing in tracking

**Solutions:**
```bash
# Check PID files
ls -la /run/dms/s3/

# Reload from disk
python3 << EOF
from trilio_dms.server import DMSServer
server = DMSServer()
server.s3vaultfuse_manager._load_existing_pids()
EOF

# Manual process registration
PID=$(pgrep -f "s3vaultfuse.*target-123")
echo $PID > /run/dms/s3/target-123.pid
```

### Orphaned Processes

**Problem:** s3vaultfuse processes running but not tracked

**Solutions:**
```bash
# Find orphaned processes
ps aux | grep s3vaultfuse

# Cleanup orphaned processes
python scripts/monitor_s3vaultfuse.py --cleanup

# Or manually
for pidfile in /run/dms/s3/*.pid; do
    pid=$(cat "$pidfile")
    if ! ps -p $pid > /dev/null; then
        rm "$pidfile"
    fi
done
```

### Permission Denied

**Problem:** Mount fails with permission denied

**Solutions:**
```bash
# Run server as root
sudo trilio-dms-server

# Or add mount capabilities
sudo setcap cap_sys_admin+ep /usr/bin/python3

# Check mount directory ownership
sudo chown -R root:root /var/lib/trilio/triliovault-mounts/
```

## Performance Tuning

### RabbitMQ Connection Pool

```python
# In server.py, adjust connection parameters
connection = pika.BlockingConnection(
    pika.URLParameters(
        f"{self.rabbitmq_url}?"
        f"heartbeat=30&"
        f"connection_attempts=3&"
        f"retry_delay=1"
    )
)
```

### Process Limits

```bash
# Increase open file limits
echo "* soft nofile 65536" >> /etc/security/limits.conf
echo "* hard nofile 65536" >> /etc/security/limits.conf

# Increase process limits
echo "* soft nproc 65536" >> /etc/security/limits.conf
echo "* hard nproc 65536" >> /etc/security/limits.conf
```

### Mount Options

**For NFS:**
```python
# Optimize NFS mount options
nfs_mount_opts = "rw,sync,hard,intr,nfsvers=4,timeo=600,retrans=2"
```

**For S3:**
```bash
# Increase connection pool
vault_s3_max_pool_connections=1000
```

## Best Practices

### 1. Run One Server Per Node

```bash
# Each compute node should have its own server
# Set unique NODE_ID for each
export DMS_NODE_ID="compute-01"  # On node 1
export DMS_NODE_ID="compute-02"  # On node 2
```

### 2. Monitor Resource Usage

```bash
# Regular monitoring
*/5 * * * * python scripts/monitor_s3vaultfuse.py --detailed > /var/log/dms-monitor.log
```

### 3. Regular Cleanup

```bash
# Cleanup dead processes daily
0 2 * * * python3 -c "from trilio_dms.server import DMSServer; s=DMSServer(); s.s3vaultfuse_manager.cleanup_dead_processes()"
```

### 4. Backup PID Files

```bash
# Backup PID directory
rsync -av /run/dms/s3/ /backup/dms-pids/
```

### 5. Use Monitoring

```bash
# Set up monitoring alerts
if [ $(ls /run/dms/s3/*.pid | wc -l) -gt 100 ]; then
    echo "Too many s3vaultfuse processes!" | mail -s "DMS Alert" admin@example.com
fi
```

## Security

### Credential Management

- ✅ Credentials fetched from Barbican (never stored)
- ✅ Sensitive environment variables sanitized in logs
- ✅ AWS keys marked as `***REDACTED***`

### Process Isolation

- ✅ Each s3vaultfuse runs in own process group
- ✅ Processes can be killed independently
- ✅ No shared state between processes

### Access Control

```bash
# Restrict PID directory access
chmod 755 /run/dms/s3/
chown root:root /run/dms/s3/

# Restrict mount directory
chmod 755 /var/lib/trilio/triliovault-mounts/
chown root:root /var/lib/trilio/triliovault-mounts/
```

## API Reference

### Server Class

```python
from trilio_dms.server import DMSServer

server = DMSServer(
    rabbitmq_url='amqp://localhost:5672',
    node_id='compute-01',
    auth_url='http://keystone:5000/v3',
    mount_base_path='/var/lib/trilio/triliovault-mounts'
)

# Start server (blocking)
server.start()
```

### S3VaultFuseManager

```python
from trilio_dms.s3vaultfuse_manager import S3VaultFuseManager

manager = S3VaultFuseManager(pid_dir='/run/dms/s3')

# Spawn process
success = manager.spawn_s3vaultfuse(target_id, mount_path, env)

# Kill process
success = manager.kill_s3vaultfuse(target_id, force=False)

# Check if running
is_running = manager.is_running(target_id)

# Get info
info = manager.get_process_info(target_id)

# List all
processes = manager.list_all_processes()

# Get stats
stats = manager.get_stats()

# Cleanup
count = manager.cleanup_dead_processes()
manager.cleanup_all(force=False)
```

## Support

For issues or questions:
- GitHub Issues: https://github.com/dhiraj-trilio/trilio-dms/issues
- Documentation: https://github.com/dhiraj-trilio/trilio-dms#readme
- Logs: Check `/var/log/trilio-dms/` or `journalctl -u trilio-dms-server`

## See Also

- [DMS Client README](DMS_CLIENT_README.md)
- [Process Tracking Guide](PROCESS_TRACKING.md)
- [PID File Documentation](PID_FILE_TRACKING.md)
- [Main README](../README.md)
