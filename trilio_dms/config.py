"""
Configuration module for Trilio DMS
"""

import os
from typing import Optional


class DMSConfig:
    """Configuration class for DMS"""
    
    # Database Configuration (Client only)
    DB_URL: str = os.getenv('DMS_DB_URL', 'mysql+pymysql://dms_user:dms_password@localhost:3306/trilio_dms')
    
    # RabbitMQ Configuration (Both client and server)
    RABBITMQ_URL: str = os.getenv('DMS_RABBITMQ_URL', 'amqp://dms_user:dms_password@localhost:5672')
    
    # Keystone Configuration (Server only)
    AUTH_URL: str = os.getenv('DMS_AUTH_URL', 'http://keystone:5000/v3')
    
    # Node Configuration (Server only)
    NODE_ID: str = os.getenv('DMS_NODE_ID', os.uname().nodename)
    
    # Mount Configuration (Server only)
    MOUNT_BASE_PATH: str = os.getenv('DMS_MOUNT_BASE', '/var/lib/trilio/mounts')
    
    # Request timeout (Client only)
    REQUEST_TIMEOUT: int = int(os.getenv('DMS_REQUEST_TIMEOUT', '300'))
    
    # Logging
    LOG_LEVEL: str = os.getenv('DMS_LOG_LEVEL', 'INFO')
    LOG_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    @classmethod
    def get_server_config(cls) -> dict:
        """Get server-specific configuration"""
        return {
            'rabbitmq_url': cls.RABBITMQ_URL,
            'node_id': cls.NODE_ID,
            'auth_url': cls.AUTH_URL,
            'mount_base_path': cls.MOUNT_BASE_PATH,
            'log_level': cls.LOG_LEVEL,
        }
    
    @classmethod
    def get_client_config(cls) -> dict:
        """Get client-specific configuration"""
        return {
            'db_url': cls.DB_URL,
            'rabbitmq_url': cls.RABBITMQ_URL,
            'timeout': cls.REQUEST_TIMEOUT,
            'log_level': cls.LOG_LEVEL,
        }
    
    @classmethod
    def validate_server_config(cls) -> bool:
        """Validate server configuration"""
        required = ['RABBITMQ_URL', 'NODE_ID', 'AUTH_URL']
        for attr in required:
            if not getattr(cls, attr):
                raise ValueError(f"Missing required server configuration: {attr}")
        return True
    
    @classmethod
    def validate_client_config(cls) -> bool:
        """Validate client configuration"""
        required = ['DB_URL', 'RABBITMQ_URL']
        for attr in required:
            if not getattr(cls, attr):
                raise ValueError(f"Missing required client configuration: {attr}")
        return True
