"""Trilio Dynamic Mount Service - Main Package"""

__version__ = '1.0.0'
__author__ = 'Trilio Data'

# Core client
from trilio_dms.client.dms_client import DMSClient
from trilio_dms.client.context import MountContext

# Exceptions
from trilio_dms.utils.exceptions import (
    DMSException,
    MountException,
    UnmountException,
    AuthenticationException,
    TargetNotFoundException
)

__all__ = [
    # Client
    'DMSClient',
    'MountContext',
    
    # Exceptions
    'DMSException',
    'MountException',
    'UnmountException',
    'AuthenticationException',
    'TargetNotFoundException',
]

