# DMS Configuration Files

## Server Configuration (`/etc/trilio-dms/server.conf`)

```ini
[server]
# RabbitMQ connection
rabbitmq_url = amqp://openstack:PASSWORD@172.26.0.8:5672/

# Node identifier (hostname)
node_id = controller

# Keystone auth URL
auth_url = https://keystone:5000

# Mount base path (optional, default: /var/lib/trilio/mounts)
mount_base_path = /var/lib/trilio/mounts

# Log level (optional, default: INFO)
log_level = INFO

# S3VaultFuse binary path (optional, default: /usr/bin/s3vaultfuse.py)
# If not found, will auto-detect using 'which s3vaultfuse.py'
s3vaultfuse_bin = /usr/bin/s3vaultfuse.py

# Rootwrap binary path (optional, default: /usr/bin/workloadmgr-rootwrap)
rootwrap_bin = /usr/bin/workloadmgr-rootwrap

# Rootwrap config path (optional, default: /etc/triliovault-wlm/rootwrap.conf)
rootwrap_conf = /etc/triliovault-wlm/rootwrap.conf
```

## Client Configuration (`/etc/trilio-dms/client.conf`)

```ini
[client]
# RabbitMQ connection
rabbitmq_url = amqp://openstack:PASSWORD@172.26.0.8:5672/

# Database connection
db_url = mysql+pymysql://workloadmgr:PASSWORD@kolla-internal:3306/workloadmgr

# Node identifier (optional)
node_id = controller

# Request timeout in seconds (optional, default: 60)
request_timeout = 60

# Log level (optional, default: INFO)
log_level = INFO
```

## Environment Variables (Override Config File)

You can also use environment variables to override config file values:

### Server Environment Variables
```bash
export DMS_RABBITMQ_URL="amqp://user:pass@host:5672/"
export DMS_NODE_ID="controller"
export DMS_AUTH_URL="https://keystone:5000"
export DMS_MOUNT_BASE_PATH="/var/lib/trilio/mounts"
export DMS_S3VAULTFUSE_BIN="/usr/local/bin/s3vaultfuse.py"
export DMS_ROOTWRAP_BIN="/usr/bin/workloadmgr-rootwrap"
export DMS_ROOTWRAP_CONF="/etc/triliovault-wlm/rootwrap.conf"
export DMS_LOG_LEVEL="DEBUG"
```

### Client Environment Variables
```bash
export DMS_RABBITMQ_URL="amqp://user:pass@host:5672/"
export DMS_DB_URL="mysql+pymysql://user:pass@host/db"
export DMS_REQUEST_TIMEOUT="120"
export DMS_LOG_LEVEL="DEBUG"
```

## Configuration Priority

The configuration is loaded in this order (later overrides earlier):

1. **Default values** (hardcoded in DMSConfig)
2. **Config file** (`/etc/trilio-dms/server.conf` or `client.conf`)
3. **Environment variables** (highest priority)

## Minimal Configuration

### Server (Minimal)
```ini
[server]
rabbitmq_url = amqp://user:pass@host:5672/
node_id = controller
auth_url = https://keystone:5000
```

### Client (Minimal)
```ini
[client]
rabbitmq_url = amqp://user:pass@host:5672/
db_url = mysql+pymysql://user:pass@host/db
```

## Auto-Detection Features

### S3VaultFuse Binary
If `s3vaultfuse_bin` is not specified or the path doesn't exist, the server will:
1. Try the default path `/usr/bin/s3vaultfuse.py`
2. If not found, run `which s3vaultfuse.py` to find it in PATH
3. Log a warning if not found

```
2026-01-16 18:00:00,000 - WARNING - S3VaultFuse binary not found at /usr/bin/s3vaultfuse.py, searching...
2026-01-16 18:00:00,001 - INFO - Found s3vaultfuse.py at: /usr/local/bin/s3vaultfuse.py
```

## NFS Mount Command

With the new configuration, NFS mounts use rootwrap:

```bash
sudo /usr/bin/workloadmgr-rootwrap \
     /etc/triliovault-wlm/rootwrap.conf \
     mount -t nfs -o <options> <export> <mount_path>
```

You can customize the rootwrap paths in the config:

```ini
[server]
rootwrap_bin = /usr/local/bin/custom-rootwrap
rootwrap_conf = /etc/custom/rootwrap.conf
```

## Verification

### Check Current Configuration
```bash
# As server
python3 -c "
from trilio_dms.config import DMSConfig
DMSConfig.load_config(config_type='server')
DMSConfig.print_config()
"

# As client
python3 -c "
from trilio_dms.config import DMSConfig
DMSConfig.load_config(config_type='client')
DMSConfig.print_config()
"
```

### Verify Paths
```bash
# Check if s3vaultfuse exists
ls -la /usr/bin/s3vaultfuse.py
which s3vaultfuse.py

# Check if rootwrap exists
ls -la /usr/bin/workloadmgr-rootwrap
ls -la /etc/triliovault-wlm/rootwrap.conf
```

## Troubleshooting

### S3VaultFuse Not Found
```
WARNING - s3vaultfuse.py not found in PATH
```

**Solution**: Install s3vaultfuse or specify the correct path:
```ini
s3vaultfuse_bin = /path/to/s3vaultfuse.py
```

### Rootwrap Not Found
```
ERROR - Failed to execute NFS mount: [Errno 2] No such file or directory: '/usr/bin/workloadmgr-rootwrap'
```

**Solution**: Specify correct rootwrap paths in config:
```ini
rootwrap_bin = /usr/bin/sudo
rootwrap_conf = 
```

Or use direct mount (not recommended for production):
```ini
# This would require the config and code changes to support non-rootwrap mounting
```
