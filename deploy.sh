DEPLOY_SCRIPT = """#!/bin/bash
# Trilio DMS Deployment Script

set -e

echo "========================================="
echo "Trilio DMS Deployment"
echo "========================================="

# Check root
if [ "$EUID" -ne 0 ]; then 
  echo "Please run as root"
  exit 1
fi

# Install system dependencies
echo "Installing system dependencies..."
apt-get update
apt-get install -y python3-pip python3-venv s3fs fuse mysql-client

# Create directories
echo "Creating directories..."
mkdir -p /opt/trilio/dms
mkdir -p /run/dms/s3
mkdir -p /var/log/trilio
mkdir -p /mnt/trilio

# Install Python package
echo "Installing Trilio DMS..."
pip3 install trilio-dms

# Generate systemd service
echo "Generating systemd service..."
trilio-dms-cli generate-systemd

# Reload systemd
systemctl daemon-reload

# Enable service
systemctl enable trilio-dms

echo ""
echo "✅ Trilio DMS installed successfully!"
echo ""
echo "Next steps:"
echo "  1. Configure environment in /etc/systemd/system/trilio-dms.service"
echo "  2. systemctl start trilio-dms"
echo "  3. systemctl status trilio-dms"
echo "  4. trilio-dms-cli register  # Register backup targets"
"""

