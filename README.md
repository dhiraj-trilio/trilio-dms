# Trilio Dynamic Mount Service (DMS)

Centralized mount/unmount service for backup targets (S3, NFS) with job-driven bindings, database ledger tracking, and secure credential management.

## 🏗️ Architecture

```
┌─────────────────┐         RabbitMQ          ┌──────────────────┐
│   DMS Client    │ ◄────────────────────────► │   DMS Server     │
│                 │                            │                  │
│ - DB Access     │                            │ - Mount/Unmount  │
│ - Ledger Mgmt   │                            │ - NO DB Access   │
│ - Request Send  │                            │ - RabbitMQ Only  │
└────────┬────────┘                            └─────────┬────────┘
         │                                               │
         ▼                                               ▼
   ┌──────────┐                                   ┌───────────┐
   │  MySQL   │                                   │  Mounts   │
   │ (Ledger) │                                   │ /var/lib/ │
   └──────────┘                                   └───────────┘
              │
              ▼
        ┌──────────┐
        │ Barbican │
        │ (Secrets)│
        └──────────┘
```

## 🎯 Key Features

* 🔐 **Secure Credential Management** - Integration with OpenStack Barbican for secret storage
* 📦 **Job-Driven Mount Bindings** - Each mount tied to specific backup jobs
* 🗄️ **Complete Operation Tracking** - All mount/unmount operations logged in database ledger
* 🔄 **Automatic Reconciliation** - Smart cleanup of stale entries
* 🚀 **Horizontal Scalability** - Deploy DMS server on multiple compute nodes
* 💾 **Persistent Mounts** - Mounts tracked across service restarts
* 🔧 **Multiple Interfaces** - Python API, CLI, and context managers
* 🎭 **Separation of Concerns** - Client handles DB, Server handles mounts

## 📋 Components

### DMS Server (`trilio_dms/server.py`)
**Responsibilities:**
- Listen to RabbitMQ for mount/unmount requests
- Execute mount/unmount operations for S3 and NFS
- Fetch credentials from Barbican
- Return standardized responses
- **NO database access**

### DMS Client (`trilio_dms/client.py`)
**Responsibilities:**
- Manage `backup_target_mount_ledger` table
- Send mount/unmount requests to DMS Server via RabbitMQ
- Track all operations in database
- Provide context manager for automatic cleanup
- Query mount status and history

### Database Ledger
Tracks every mount/unmount operation with:
- Job and target associations
- Status tracking (pending/success/error)
- Complete request/response data
- Timestamps and host information

## 🚀 Quick Start

### Installation

```bash
# From source
git clone https://github.com/dhiraj-trilio/trilio-dms.git
cd trilio-dms
pip install -e .

# Or with pip (once published)
pip install trilio-dms
```

### Configuration

Create `.env` file:

```bash
# Database (Client)
DMS_DB_URL=mysql+pymysql://user:pass@localhost:3306/trilio_dms

# RabbitMQ (Both)
DMS_RABBITMQ_URL=amqp://user:pass@localhost:5672

# Keystone (Server)
DMS_AUTH_URL=http://keystone:5000/v3
KEYSTONE_TOKEN=your-token

# Node (Server)
DMS_NODE_ID=compute-01

```

### Database Setup

```bash
# Create database
mysql -u root -p -e "CREATE DATABASE trilio_dms;"

# Import schema
mysql -u root -p trilio_dms < schema.sql
```

### Start DMS Server

```bash
# Using command
trilio-dms-server

# Or with environment variables
DMS_RABBITMQ_URL=amqp://localhost:5672 \
DMS_NODE_ID=compute-01 \
trilio-dms-server

# Or as systemd service
sudo systemctl start trilio-dms-server
```

## 💻 Usage

### Python API - Context Manager (Recommended)

```python
from trilio_dms.client import DMSClient, MountContext

# Initialize client
client = DMSClient(
    db_url='mysql+pymysql://user:pass@localhost/trilio_dms',
    rabbitmq_url='amqp://user:pass@localhost:5672'
)

# Prepare request
request = {
    'context': {
        'user_id': 'user-123',
        'tenant_id': 'tenant-456'
    },
    'keystone_token': 'your-keystone-token',
    'job': {
        'jobid': 'job-789',
        'progress': 0,
        'status': 'running',
        'completed_at': None,
        'action': 'backup',
        'parent_jobid': None,
        'job_details': [
            {'id': 'detail-1', 'data': {'vm_id': 'vm-001'}}
        ]
    },
    'host': 'compute-01',
    'backup_target': {
        'id': 'target-123',
        'deleted': False,
        'type': 's3',  # or 'nfs'
        'filesystem_export': None,  # for NFS: '192.168.1.100:/export'
        'filesystem_export_mount_path': None,
        'status': 'available',
        'secret_ref': 'http://barbican:9311/v1/secrets/abc-123',
        'nfs_mount_opts': None  # for NFS: 'rw,sync,hard'
    }
}

# Use context manager for automatic mount/unmount
with MountContext(client, request) as mount:
    # Mount is ready
    print(f"Mounted at: {mount.get_mount_path()}")
    
    # Perform backup operations
    perform_backup(mount.get_mount_path())
    
    # Automatic unmount on exit

client.close()
```

### Python API - Manual Control

```python
from trilio_dms.client import DMSClient

client = DMSClient()

# Mount
response = client.mount(request)
if response['status'] == 'success':
    print(f"Success: {response['success_msg']}")
else:
    print(f"Error: {response['error_msg']}")

# Unmount
request['action'] = 'unmount'
response = client.unmount(request)

client.close()
```

### Query Operations

```python
# Get mount status
status = client.get_mount_status('job-123', 'target-456')
print(f"Status: {status.status}")
print(f"Mount path: {status.mount_path}")

# List active mounts
active_mounts = client.get_active_mounts(host='compute-01')
for mount in active_mounts:
    print(f"{mount.backup_target_id}: {mount.mount_path}")

# Get history
history = client.get_ledger_history('target-456', limit=20)

# Cleanup stale entries
count = client.cleanup_stale_entries(hours=24)
print(f"Cleaned up {count} stale entries")
```

### Command Line Interface

```bash
# Mount a target
trilio-dms-cli mount \
  --job-id job-123 \
  --target-id target-456 \
  --target-type s3 \
  --host compute-01 \
  --secret-ref http://barbican:9311/v1/secrets/abc \
  --token $KEYSTONE_TOKEN

# Unmount a target
trilio-dms-cli unmount \
  --job-id job-123 \
  --target-id target-456 \
  --target-type s3 \
  --host compute-01 \
  --token $KEYSTONE_TOKEN

# Check status
trilio-dms-cli status --job-id job-123 --target-id target-456

# List active mounts
trilio-dms-cli list-mounts --host compute-01

# View history
trilio-dms-cli history --target-id target-456 --limit 20

# Cleanup
trilio-dms-cli cleanup --hours 24
```

## 📊 Request/Response Format

### Request Structure

```python
{
    'context': {
        'user_id': '<user_id>',
        'tenant_id': '<tenant_id>',
        'project_id': '<project_id>'
    },
    'keystone_token': '<token_for_barbican>',
    'job': {
        'jobid': '<job_id>',
        'progress': <progress_percentage>,
        'status': '<running|completed|failed>',
        'completed_at': '<timestamp_or_none>',
        'action': '<backup|restore|etc>',
        'parent_jobid': '<parent_job_id_or_none>',
        'job_details': [
            {
                'id': '<detail_id>',
                'data': {<detail_data>}
            }
        ]
    },
    'host': '<target_compute_node>',
    'action': 'mount' or 'unmount',
    'backup_target': {
        'id': '<backup_target_id>',
        'deleted': <boolean>,
        'type': 'nfs' or 's3',
        'filesystem_export': '<nfs_export_path>',  # NFS only
        'filesystem_export_mount_path': '<mount_path>',
        'status': '<available|unavailable>',
        'secret_ref': '<barbican_secret_href>',  # S3 only
        'nfs_mount_opts': '<mount_options>'  # NFS only
    }
}
```

### Response Structure

```python
{
    'status': 'success' or 'error',
    'error_msg': '<error_message_if_failed>',
    'success_msg': '<success_message_if_succeeded>'
}
```

## 🗄️ Database Schema

```sql
CREATE TABLE backup_target_mount_ledger (
    id VARCHAR(36) PRIMARY KEY,
    backup_target_id VARCHAR(36) NOT NULL,
    job_id VARCHAR(36) NOT NULL,
    host VARCHAR(255) NOT NULL,
    action VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    mount_path VARCHAR(512),
    error_msg TEXT,
    success_msg TEXT,
    request_data TEXT,
    response_data TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    completed_at DATETIME,
    INDEX idx_backup_target_id (backup_target_id),
    INDEX idx_job_id (job_id),
    INDEX idx_host (host),
    INDEX idx_status (status),
    INDEX idx_job_target (job_id, backup_target_id)
);
```

## 🚢 Deployment

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f dms-server

# Stop services
docker-compose down
```

### Manual Deployment

```bash
# Deploy everything
./deploy.sh all

# Deploy only server
./deploy.sh server

# Deploy only client
./deploy.sh client
```

### Systemd Service

```bash
# Enable and start
sudo systemctl enable trilio-dms-server
sudo systemctl start trilio-dms-server

# Check status
sudo systemctl status trilio-dms-server

# View logs
sudo journalctl -u trilio-dms-server -f
```

### Kubernetes DaemonSet

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: trilio-dms-server
spec:
  selector:
    matchLabels:
      app: trilio-dms-server
  template:
    metadata:
      labels:
        app: trilio-dms-server
    spec:
      hostNetwork: true
      hostPID: true
      containers:
      - name: dms-server
        image: trilio/dms-server:1.0.0
        securityContext:
          privileged: true
        env:
        - name: DMS_RABBITMQ_URL
          value: "amqp://user:pass@rabbitmq:5672"
        - name: DMS_NODE_ID
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        volumeMounts:
        - name: mounts
          mountPath: /var/lib/trilio/mounts
          mountPropagation: Bidirectional
      volumes:
      - name: mounts
        hostPath:
          path: /var/lib/trilio/mounts
```

## 🧪 Testing

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run integration tests (requires services)
RUN_INTEGRATION_TESTS=1 make test-integration

# Run with coverage
make test-coverage

# Or using pytest directly
pytest tests/ -v
```

## 📝 Development

```bash
# Install development dependencies
make install-dev

# Format code
make format

# Lint code
make lint

# Build package
make build
```

## 🔧 System Requirements

### DMS Server
- Python 3.8+
- Ubuntu 22.04 or RHEL 8+ (or compatible)
- s3fs-fuse (for S3 mounts)
- nfs-common/nfs-utils (for NFS mounts)
- RabbitMQ access
- Privileged access for mount operations

### DMS Client
- Python 3.8+
- MySQL/MariaDB access
- RabbitMQ access

## 📖 Examples

See `examples/` directory for complete working examples:
- `example_backup_workflow.py` - Full backup/restore workflow
- Integration with existing backup systems

## 🐛 Troubleshooting

### Mount fails with permission denied
```bash
# Ensure server runs with privileges
sudo chown root:root /usr/local/bin/trilio-dms-server
sudo chmod +s /usr/local/bin/trilio-dms-server

# Or run with sudo
sudo trilio-dms-server
```

### Request timeout
```bash
# Increase timeout
export DMS_REQUEST_TIMEOUT=600

# Check RabbitMQ connectivity
rabbitmqctl list_queues

# Check server is running
systemctl status trilio-dms-server
```

### Database connection issues
```bash
# Test connection
mysql -h localhost -u dms_user -p trilio_dms -e "SELECT 1;"

# Check ledger table
mysql -u dms_user -p trilio_dms -e "SELECT * FROM backup_target_mount_ledger LIMIT 5;"
```

## 📊 Monitoring

### Server Logs
```bash
# systemd
journalctl -u trilio-dms-server -f

# Docker
docker logs -f trilio-dms-server

# File
tail -f /var/log/trilio-dms/server.log
```

### Database Queries
```sql
-- Recent operations
SELECT * FROM backup_target_mount_ledger 
ORDER BY created_at DESC LIMIT 10;

-- Failed operations
SELECT * FROM backup_target_mount_ledger 
WHERE status = 'error' 
ORDER BY created_at DESC;

-- Active mounts by host
SELECT host, COUNT(*) as count 
FROM backup_target_mount_ledger 
WHERE action = 'mount' AND status = 'success'
GROUP BY host;
```

### Check Mounts
```bash
# List all mounts
df -h | grep trilio

# Check specific mount
mountpoint /var/lib/trilio/mounts/target-123
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

Apache License 2.0 - see LICENSE file for details

## 🆘 Support

- GitHub Issues: https://github.com/dhiraj-trilio/trilio-dms/issues
- Documentation: https://github.com/dhiraj-trilio/trilio-dms#readme
- Email: support@trilio.io

## 🙏 Acknowledgments

- OpenStack Barbican for secret management
- RabbitMQ for reliable messaging
- s3fs and nfs-common for filesystem support
