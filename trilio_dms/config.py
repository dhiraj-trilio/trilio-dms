"""Configuration management - Added URL validation"""

import os
from typing import Optional
from dataclasses import dataclass

from trilio_dms.utils.validators import validate_and_fix_rabbitmq_url


@dataclass
class DMSConfig:
    """DMS Configuration with automatic URL validation"""
    
    # Database
    db_url: str = os.getenv('DMS_DB_URL', 'mysql://root@localhost/trilio_dms')
    db_pool_size: int = int(os.getenv('DMS_DB_POOL_SIZE', '10'))
    db_pool_recycle: int = int(os.getenv('DMS_DB_POOL_RECYCLE', '3600'))
    
    # RabbitMQ
    _rabbitmq_url: str = os.getenv('DMS_RABBITMQ_URL', 'amqp://guest:guest@localhost:5672')
    rabbitmq_queue: str = os.getenv('DMS_RABBITMQ_QUEUE', 'trilio_dms_ops')
    rabbitmq_prefetch: int = int(os.getenv('DMS_RABBITMQ_PREFETCH', '1'))
    rabbitmq_heartbeat: int = int(os.getenv('DMS_RABBITMQ_HEARTBEAT', '60'))
    
    # Authentication
    auth_url: str = os.getenv('DMS_AUTH_URL', 'http://localhost:5000/v3')
    
    # Service
    node_id: str = os.getenv('DMS_NODE_ID', 'localhost')
    log_level: str = os.getenv('DMS_LOG_LEVEL', 'INFO')
    
    # Mounts
    mount_base_path: str = os.getenv('DMS_MOUNT_BASE', '/mnt/trilio')
    s3_pidfile_dir: str = os.getenv('DMS_S3_PIDFILE_DIR', '/run/dms/s3')
    mount_timeout: int = int(os.getenv('DMS_MOUNT_TIMEOUT', '60'))
    
    # Operations
    operation_timeout: int = int(os.getenv('DMS_OPERATION_TIMEOUT', '300'))
    reconcile_interval: int = int(os.getenv('DMS_RECONCILE_INTERVAL', '300'))
    
    # Security
    verify_ssl: bool = os.getenv('DMS_VERIFY_SSL', 'false').lower() == 'true'
    
    @property
    def rabbitmq_url(self) -> str:
        """Get validated RabbitMQ URL"""
        return validate_and_fix_rabbitmq_url(self._rabbitmq_url)
    
    @rabbitmq_url.setter
    def rabbitmq_url(self, value: str):
        """Set RabbitMQ URL (will be validated on access)"""
        self._rabbitmq_url = value
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        # Validate RabbitMQ URL on init
        try:
            _ = self.rabbitmq_url  # Trigger validation
        except ValueError as e:
            from trilio_dms.utils.logger import get_logger
            LOG = get_logger(__name__)
            LOG.warning(f"RabbitMQ URL validation: {e}")
    
    @classmethod
    def from_file(cls, config_file: str) -> 'DMSConfig':
        """Load configuration from file"""
        import json
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        # Rename rabbitmq_url to _rabbitmq_url for internal storage
        if 'rabbitmq_url' in config_data:
            config_data['_rabbitmq_url'] = config_data.pop('rabbitmq_url')
        
        return cls(**config_data)
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary"""
        return {
            'db_url': self.db_url,
            'rabbitmq_url': self.rabbitmq_url,  # Use validated property
            'auth_url': self.auth_url,
            'node_id': self.node_id,
            'log_level': self.log_level,
            'mount_base_path': self.mount_base_path,
            's3_pidfile_dir': self.s3_pidfile_dir,
            'mount_timeout': self.mount_timeout,
            'operation_timeout': self.operation_timeout,
            'verify_ssl': self.verify_ssl
        }
