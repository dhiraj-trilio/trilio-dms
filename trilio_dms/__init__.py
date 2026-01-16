# trilio_dms/__init__.py
"""
Trilio Dynamic Mount Service (DMS) Client Library

This library provides a client interface for interacting with the Trilio DMS server,
enabling centralized mount/unmount operations for backup targets with proper locking
and ledger management.

Key Features:
- Global locking to prevent concurrent mount/unmount conflicts
- Smart unmount logic that only unmounts when no other jobs are using the target
- Soft-delete aware queries
- Context managers for automatic cleanup
- Comprehensive error handling

Example:
    >>> from trilio_dms import DMSClient, mount_context
    >>> 
    >>> # Create client
    >>> client = DMSClient(
    ...     rabbitmq_url='amqp://localhost:5672',
    ...     db_session=session
    ... )
    >>> 
    >>> # Use context manager for automatic mount/unmount
    >>> with mount_context(client, 12345, 'target-001', 'compute-01', 'token') as mount:
    ...     perform_backup(mount['mount_path'])
"""

from .client import (
    DMSClient,
    DMSClientError,
    DMSMountError,
    DMSUnmountError,
    DMSLockTimeoutError,
    MountContext
)

from .lock_manager import (
    DMSLockManager,
    get_lock_manager
)

from .models import (
    BackupTargetMountLedger,
    Base
)

from .context_manager import (
    mount_context,
    batch_mount_context,
    MountContext,
    auto_mount_unmount
)

__version__ = '1.0.0'
__author__ = 'Trilio Data'
__license__ = 'Apache 2.0'

__all__ = [
    # Client
    'DMSClient',
    
    # Exceptions
    'DMSClientError',
    'DMSMountError',
    'DMSUnmountError',
    'DMSLockTimeoutError',
    
    # Lock Manager
    'DMSLockManager',
    'get_lock_manager',
    
    # Models
    'BackupTargetMountLedger',
    'Base',
    
    # Context Managers
    'mount_context',
    'batch_mount_context',
    'MountContext',
    'auto_mount_unmount',
    
    # Version
    '__version__',
]


# Package metadata
__doc_url__ = 'https://github.com/dhiraj-trilio/trilio-dms'
__download_url__ = 'https://github.com/dhiraj-trilio/trilio-dms/releases'


def get_version():
    """Get the current version of the package."""
    return __version__


def get_info():
    """Get package information."""
    return {
        'name': 'trilio-dms',
        'version': __version__,
        'author': __author__,
        'license': __license__,
        'description': 'Trilio Dynamic Mount Service Client Library',
        'url': __doc_url__
    }
