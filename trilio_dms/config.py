"""
Trilio DMS Configuration Module
Supports loading from:
1. INI config file (/etc/trilio-dms/server.conf or /etc/trilio-dms/client.conf)
2. Environment variables (override config file)
3. Default values (fallback)
"""

import os
import logging
from configparser import ConfigParser
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class DMSConfig:
    """DMS Configuration Manager"""
    
    # Default configuration file paths
    SERVER_CONFIG_FILE = '/etc/trilio-dms/server.conf'
    CLIENT_CONFIG_FILE = '/etc/trilio-dms/client.conf'
    
    # Default values
    DEFAULT_RABBITMQ_URL = 'amqp://guest:guest@localhost:5672/'
    DEFAULT_DB_URL = 'sqlite:///tmp/trilio_dms.db'
    DEFAULT_NODE_ID = 'default-node'
    DEFAULT_AUTH_URL = 'http://localhost:5000'
    DEFAULT_MOUNT_BASE_PATH = '/var/lib/trilio/mounts'
    DEFAULT_LOG_LEVEL = 'INFO'
    DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    DEFAULT_REQUEST_TIMEOUT = 60
    DEFAULT_S3VAULTFUSE_BIN = '/usr/bin/s3vaultfuse.py'
    DEFAULT_ROOTWRAP_BIN = '/usr/bin/workloadmgr-rootwrap'
    DEFAULT_ROOTWRAP_CONF = '/etc/triliovault-wlm/rootwrap.conf'
    
    # Class attributes (loaded values)
    RABBITMQ_URL = None
    DB_URL = None
    NODE_ID = None
    AUTH_URL = None
    MOUNT_BASE_PATH = None
    LOG_LEVEL = None
    LOG_FORMAT = None
    REQUEST_TIMEOUT = None
    S3VAULTFUSE_BIN = None
    ROOTWRAP_BIN = None
    ROOTWRAP_CONF = None
    
    _loaded = False
    _config_data = {}
    _config_type = None  # Track which config type was loaded
    
    @classmethod
    def load_config(cls, config_file: Optional[str] = None, config_type: str = 'server'):
        """
        Load configuration from file and environment variables.
        
        Args:
            config_file: Path to config file (optional)
            config_type: 'server' or 'client' (determines default config file)
        """
        if cls._loaded and cls._config_type == config_type:
            logger.debug(f"Configuration already loaded for {config_type}, skipping reload")
            return
        
        # If different config type requested, reload
        if cls._loaded and cls._config_type != config_type:
            logger.info(f"Reloading config: {cls._config_type} -> {config_type}")
            cls._loaded = False
        
        # Determine config file path
        if config_file is None:
            config_file = cls.SERVER_CONFIG_FILE if config_type == 'server' else cls.CLIENT_CONFIG_FILE
        
        logger.debug(f"Loading config from: {config_file} (type: {config_type})")
        
        # Load from INI file
        config_data = cls._load_ini_file(config_file)
        cls._config_data = config_data
        cls._config_type = config_type
        
        # Load configuration with priority: env var > config file > default
        cls.RABBITMQ_URL = os.environ.get(
            'DMS_RABBITMQ_URL',
            config_data.get('rabbitmq_url', cls.DEFAULT_RABBITMQ_URL)
        )
        
        cls.DB_URL = os.environ.get(
            'DMS_DB_URL',
            config_data.get('db_url', cls.DEFAULT_DB_URL)
        )
        
        cls.NODE_ID = os.environ.get(
            'DMS_NODE_ID',
            config_data.get('node_id', cls.DEFAULT_NODE_ID)
        )
        
        cls.AUTH_URL = os.environ.get(
            'DMS_AUTH_URL',
            config_data.get('auth_url', cls.DEFAULT_AUTH_URL)
        )
        
        cls.MOUNT_BASE_PATH = os.environ.get(
            'DMS_MOUNT_BASE_PATH',
            config_data.get('mount_base_path', cls.DEFAULT_MOUNT_BASE_PATH)
        )
        
        cls.LOG_LEVEL = os.environ.get(
            'DMS_LOG_LEVEL',
            config_data.get('log_level', cls.DEFAULT_LOG_LEVEL)
        )
        
        cls.LOG_FORMAT = os.environ.get(
            'DMS_LOG_FORMAT',
            config_data.get('log_format', cls.DEFAULT_LOG_FORMAT)
        )
        
        cls.REQUEST_TIMEOUT = int(os.environ.get(
            'DMS_REQUEST_TIMEOUT',
            config_data.get('request_timeout', cls.DEFAULT_REQUEST_TIMEOUT)
        ))
        
        cls.S3VAULTFUSE_BIN = os.environ.get(
            'DMS_S3VAULTFUSE_BIN',
            config_data.get('s3vaultfuse_bin', cls.DEFAULT_S3VAULTFUSE_BIN)
        )
        
        cls.ROOTWRAP_BIN = os.environ.get(
            'DMS_ROOTWRAP_BIN',
            config_data.get('rootwrap_bin', cls.DEFAULT_ROOTWRAP_BIN)
        )
        
        cls.ROOTWRAP_CONF = os.environ.get(
            'DMS_ROOTWRAP_CONF',
            config_data.get('rootwrap_conf', cls.DEFAULT_ROOTWRAP_CONF)
        )
        
        cls._loaded = True
        
        logger.info(f"Configuration loaded from: {config_file}")
        logger.debug(f"RABBITMQ_URL: {cls._mask_password(cls.RABBITMQ_URL)}")
        logger.debug(f"NODE_ID: {cls.NODE_ID}")
        logger.debug(f"AUTH_URL: {cls.AUTH_URL}")
    
    @classmethod
    def _load_ini_file(cls, config_file: str) -> Dict[str, Any]:
        """
        Load configuration from INI file.
        
        Expected format:
        [server]
        rabbitmq_url = amqp://user:pass@host:5672/
        node_id = controller
        auth_url = http://localhost:5000
        log_level = INFO
        
        [client]
        db_url = mysql://user:pass@host/db
        rabbitmq_url = amqp://user:pass@host:5672/
        """
        config_data = {}
        
        if not os.path.exists(config_file):
            logger.warning(f"Config file not found: {config_file}, using defaults")
            return config_data
        
        try:
            parser = ConfigParser()
            parser.read(config_file)
            
            # Try to read from [server] section first, then [client], then [DEFAULT]
            for section in ['server', 'client', 'DEFAULT']:
                if parser.has_section(section) or section == 'DEFAULT':
                    for key, value in parser.items(section):
                        if key not in config_data:  # Don't override already set values
                            config_data[key] = value
            
            logger.info(f"Loaded {len(config_data)} config parameters from {config_file}")
            
        except Exception as e:
            logger.error(f"Failed to load config file {config_file}: {e}")
        
        return config_data
    
    @classmethod
    def get_server_config(cls) -> Dict[str, Any]:
        """
        Get server configuration as dictionary.
        
        Returns:
            Dictionary with server configuration
        """
        if not cls._loaded:
            cls.load_config(config_type='server')
        
        return {
            'rabbitmq_url': cls.RABBITMQ_URL,
            'node_id': cls.NODE_ID,
            'auth_url': cls.AUTH_URL,
            'mount_base_path': cls.MOUNT_BASE_PATH,
            'log_level': cls.LOG_LEVEL,
            's3vaultfuse_bin': cls.S3VAULTFUSE_BIN,
            'rootwrap_bin': cls.ROOTWRAP_BIN,
            'rootwrap_conf': cls.ROOTWRAP_CONF
        }
    
    @classmethod
    def get_client_config(cls) -> Dict[str, Any]:
        """
        Get client configuration as dictionary.
        
        Returns:
            Dictionary with client configuration
        """
        if not cls._loaded:
            cls.load_config(config_type='client')
        
        return {
            'db_url': cls.DB_URL,
            'rabbitmq_url': cls.RABBITMQ_URL,
            'timeout': cls.REQUEST_TIMEOUT
        }
    
    @classmethod
    def validate_server_config(cls):
        """
        Validate server configuration.
        
        Raises:
            ValueError if configuration is invalid
        """
        if not cls._loaded:
            cls.load_config(config_type='server')
        
        if not cls.RABBITMQ_URL:
            raise ValueError("RABBITMQ_URL is required")
        
        if not cls.NODE_ID:
            raise ValueError("NODE_ID is required")
        
        logger.info("Server configuration validated successfully")
    
    @classmethod
    def validate_client_config(cls):
        """
        Validate client configuration.
        
        Raises:
            ValueError if configuration is invalid
        """
        if not cls._loaded:
            cls.load_config(config_type='client')
        
        if not cls.DB_URL:
            raise ValueError("DB_URL is required")
        
        if not cls.RABBITMQ_URL:
            raise ValueError("RABBITMQ_URL is required")
        
        logger.info("Client configuration validated successfully")
    
    @classmethod
    def _mask_password(cls, url: str) -> str:
        """Mask password in URL for logging."""
        if '@' in url and '://' in url:
            try:
                protocol, rest = url.split('://', 1)
                if '@' in rest:
                    auth, host = rest.split('@', 1)
                    if ':' in auth:
                        user, _ = auth.split(':', 1)
                        return f"{protocol}://{user}:***@{host}"
            except:
                pass
        return url
    
    @classmethod
    def reload(cls):
        """Reload configuration (useful for testing)."""
        cls._loaded = False
        cls._config_data = {}
        cls.load_config()
    
    @classmethod
    def print_config(cls):
        """Print current configuration (for debugging)."""
        if not cls._loaded:
            cls.load_config()
        
        print("="*60)
        print("DMS Configuration")
        print("="*60)
        print(f"RABBITMQ_URL: {cls._mask_password(cls.RABBITMQ_URL)}")
        print(f"DB_URL: {cls._mask_password(cls.DB_URL)}")
        print(f"NODE_ID: {cls.NODE_ID}")
        print(f"AUTH_URL: {cls.AUTH_URL}")
        print(f"MOUNT_BASE_PATH: {cls.MOUNT_BASE_PATH}")
        print(f"LOG_LEVEL: {cls.LOG_LEVEL}")
        print(f"REQUEST_TIMEOUT: {cls.REQUEST_TIMEOUT}")
        print("="*60)


# Auto-load configuration on module import
# This ensures config is loaded before any other module uses it
try:
    # Check which config file exists
    import sys
    
    server_exists = os.path.exists(DMSConfig.SERVER_CONFIG_FILE)
    client_exists = os.path.exists(DMSConfig.CLIENT_CONFIG_FILE)
    
    # Determine config type based on what's available and script name
    if 'server' in ' '.join(sys.argv).lower() or 'dms-server' in ' '.join(sys.argv).lower():
        if server_exists:
            DMSConfig.load_config(config_type='server')
            logger.debug("Auto-loaded server config")
    elif 'client' in ' '.join(sys.argv).lower() or 'dms-client' in ' '.join(sys.argv).lower():
        if client_exists:
            DMSConfig.load_config(config_type='client')
            logger.debug("Auto-loaded client config")
    else:
        # Don't auto-load - let the user specify explicitly
        # This prevents loading the wrong config
        logger.debug("Config not auto-loaded - use DMSConfig.load_config() explicitly")
        
except Exception as e:
    logger.warning(f"Failed to auto-load config: {e}")
    # Will load on first use
