#!/bin/bash
# Deployment script for Trilio DMS

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependencies() {
    log_info "Checking dependencies..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed"
        exit 1
    fi
    
    # Check pip
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3 is not installed"
        exit 1
    fi
    
    log_info "All dependencies satisfied"
}

install_system_packages() {
    log_info "Installing system packages..."
    
    if [ -f /etc/debian_version ]; then
        # Debian/Ubuntu
        sudo apt-get update
        sudo apt-get install -y \
            python3-dev \
            python3-pip \
            s3fs \
            nfs-common \
            mysql-client \
            rabbitmq-server
    elif [ -f /etc/redhat-release ]; then
        # RHEL/CentOS
        sudo yum install -y \
            python3-devel \
            python3-pip \
            s3fs-fuse \
            nfs-utils \
            mysql \
            rabbitmq-server
    else
        log_warn "Unknown OS, please install dependencies manually"
    fi
}

setup_database() {
    log_info "Setting up database..."
    
    DB_HOST=${DMS_DB_HOST:-localhost}
    DB_USER=${DMS_DB_USER:-dms_user}
    DB_PASS=${DMS_DB_PASS:-dms_password}
    DB_NAME=${DMS_DB_NAME:-trilio_dms}
    
    # Create database and user
    mysql -h $DB_HOST -u root -p << EOF
CREATE DATABASE IF NOT EXISTS $DB_NAME;
CREATE USER IF NOT EXISTS '$DB_USER'@'%' IDENTIFIED BY '$DB_PASS';
GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'%';
FLUSH PRIVILEGES;
EOF
    
    # Import schema
    if [ -f schema.sql ]; then
        log_info "Importing database schema..."
        mysql -h $DB_HOST -u $DB_USER -p$DB_PASS $DB_NAME < schema.sql
    fi
    
    log_info "Database setup complete"
}

setup_rabbitmq() {
    log_info "Setting up RabbitMQ..."
    
    RABBITMQ_USER=${DMS_RABBITMQ_USER:-dms_user}
    RABBITMQ_PASS=${DMS_RABBITMQ_PASS:-dms_password}
    
    # Enable RabbitMQ management plugin
    sudo rabbitmq-plugins enable rabbitmq_management
    
    # Create user and set permissions
    sudo rabbitmqctl add_user $RABBITMQ_USER $RABBITMQ_PASS || true
    sudo rabbitmqctl set_permissions -p / $RABBITMQ_USER ".*" ".*" ".*"
    sudo rabbitmqctl set_user_tags $RABBITMQ_USER administrator
    
    log_info "RabbitMQ setup complete"
}

install_dms() {
    log_info "Installing Trilio DMS..."
    
    # Install package
    pip3 install -e .
    
    log_info "Installation complete"
}

setup_service() {
    COMPONENT=$1
    
    if [ "$COMPONENT" == "server" ]; then
        log_info "Setting up DMS Server service..."
        
        # Create systemd service file
        sudo tee /etc/systemd/system/trilio-dms-server.service > /dev/null << EOF
[Unit]
Description=Trilio DMS Server
After=network.target rabbitmq-server.service

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
Environment="DMS_RABBITMQ_URL=${DMS_RABBITMQ_URL}"
Environment="DMS_NODE_ID=${DMS_NODE_ID}"
Environment="DMS_AUTH_URL=${DMS_AUTH_URL}"
Environment="DMS_MOUNT_BASE=${DMS_MOUNT_BASE}"
ExecStart=/usr/local/bin/trilio-dms-server
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        
        # Reload systemd and enable service
        sudo systemctl daemon-reload
        sudo systemctl enable trilio-dms-server
        
        log_info "DMS Server service created"
        log_info "Start with: sudo systemctl start trilio-dms-server"
    fi
}

create_mount_directory() {
    log_info "Creating mount directory..."
    
    MOUNT_BASE=${DMS_MOUNT_BASE:-/var/lib/trilio/mounts}
    sudo mkdir -p $MOUNT_BASE
    sudo chmod 755 $MOUNT_BASE
    
    log_info "Mount directory created: $MOUNT_BASE"
}

# Main deployment logic
main() {
    log_info "Starting Trilio DMS deployment..."
    
    # Parse arguments
    COMPONENT=${1:-all}
    
    case $COMPONENT in
        all)
            check_dependencies
            install_system_packages
            setup_database
            setup_rabbitmq
            install_dms
            create_mount_directory
            setup_service server
            log_info "Complete deployment finished!"
            ;;
        server)
            check_dependencies
            install_system_packages
            install_dms
            create_mount_directory
            setup_service server
            log_info "Server deployment finished!"
            ;;
        client)
            check_dependencies
            install_dms
            log_info "Client deployment finished!"
            ;;
        database)
            setup_database
            ;;
        rabbitmq)
            setup_rabbitmq
            ;;
        *)
            log_error "Unknown component: $COMPONENT"
            echo "Usage: $0 {all|server|client|database|rabbitmq}"
            exit 1
            ;;
    esac
    
    log_info "Deployment complete!"
}

# Run main
main "$@"
