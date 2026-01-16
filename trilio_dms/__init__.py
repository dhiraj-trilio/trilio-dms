"""
Trilio Dynamic Mount Service (DMS)

A centralized mount/unmount service for backup targets with:
- DMS Server: Handles mount/unmount operations via RabbitMQ
- DMS Client: Manages database ledger and sends requests
- S3VaultFuse: Custom S3 mount manager for Trilio
"""

__version__ = '1.0.0'
__author__ = 'Trilio'

from trilio_dms.client import DMSClient, MountContext
from trilio_dms.server import DMSServer
from trilio_dms.models import BackupTargetMountLedger
from trilio_dms.s3vaultfuse_manager import S3VaultFuseManager

__all__ = [
    'DMSClient',
    'MountContext',
    'BackupTargetMountLedger',
    'DMSServer',
    'S3VaultFuseManager',
]
