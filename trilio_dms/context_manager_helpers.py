# trilio_dms/context_manager_helpers.py
"""
Additional context manager helpers for DMS Client.

These provide convenience functions for common mount/unmount patterns
while working with your existing request structure.
"""

import logging
from contextlib import contextmanager
from typing import Dict, Any, Optional, List

from trilio_dms.client import DMSClient, MountContext
from trilio_dms.exceptions import DMSClientException

logger = logging.getLogger(__name__)


@contextmanager
def simple_mount_context(client: DMSClient,
                        jobid: int,
                        backup_target: Dict[str, Any],
                        host: str,
                        token: Optional[str] = None):
    """
    Simplified context manager that builds the request structure automatically.
    
    This is useful when you want to use a simpler API without building
    the full request structure manually.
    
    Args:
        client: DMSClient instance
        jobid: Job ID (integer)
        backup_target: Backup target dictionary with 'id' and other fields
        host: Host where target should be mounted
        token: Authentication token (optional)
        
    Yields:
        MountContext instance with mount_path accessible
        
    Example:
        >>> with simple_mount_context(
        ...     client, 
        ...     12345, 
        ...     {'id': 'target-001', 'type': 's3'}, 
        ...     'compute-01'
        ... ) as ctx:
        ...     print(f"Mounted at: {ctx.mount_path}")
        ...     perform_backup(ctx.mount_path)
    """
    # Build request structure
    request = {
        'job': {'jobid': jobid},
        'backup_target': backup_target,
        'host': host
    }
    
    if token:
        request['token'] = token
    
    # Use the existing MountContext
    with MountContext(client, request) as ctx:
        yield ctx


@contextmanager
def batch_mount_context(client: DMSClient,
                       jobid: int,
                       targets: List[Dict[str, Any]],
                       host: str,
                       token: Optional[str] = None):
    """
    Context manager for mounting multiple backup targets at once.
    
    All targets are mounted before entering the context, and all are unmounted
    when exiting (in reverse order of mounting).
    
    Args:
        client: DMSClient instance
        jobid: Job ID (integer)
        targets: List of backup target dictionaries
        host: Host where targets should be mounted
        token: Authentication token (optional)
        
    Yields:
        List of MountContext instances
        
    Example:
        >>> targets = [
        ...     {'id': 'target-001', 'type': 's3'},
        ...     {'id': 'target-002', 'type': 'nfs'}
        ... ]
        >>> with batch_mount_context(client, 12345, targets, 'compute-01') as contexts:
        ...     for ctx in contexts:
        ...         print(f"Mounted: {ctx.mount_path}")
        ...         perform_backup(ctx.mount_path)
    """
    mounted_contexts = []
    
    try:
        # Mount all targets
        for backup_target in targets:
            logger.info(
                f"Batch mount: Mounting {backup_target['id']} for job {jobid}"
            )
            
            request = {
                'job': {'jobid': jobid},
                'backup_target': backup_target,
                'host': host
            }
            
            if token:
                request['token'] = token
            
            try:
                # Create mount context and enter it
                ctx = MountContext(client, request)
                ctx.__enter__()
                mounted_contexts.append(ctx)
                
                logger.info(
                    f"Batch mount: Successfully mounted {backup_target['id']}"
                )
                
            except Exception as e:
                logger.error(
                    f"Batch mount: Error mounting {backup_target['id']}: {e}",
                    exc_info=True
                )
                raise
        
        # Yield all contexts
        yield mounted_contexts
        
    finally:
        # Unmount all targets in reverse order
        for ctx in reversed(mounted_contexts):
            try:
                backup_target_id = ctx.request['backup_target']['id']
                logger.info(
                    f"Batch unmount: Unmounting {backup_target_id} for job {jobid}"
                )
                
                ctx.__exit__(None, None, None)
                
                logger.info(
                    f"Batch unmount: Successfully unmounted {backup_target_id}"
                )
                
            except Exception as e:
                logger.error(
                    f"Batch unmount: Error unmounting {backup_target_id}: {e}",
                    exc_info=True
                )
                # Continue with other unmounts even if one fails


def auto_mount_unmount(client: DMSClient,
                       jobid: int,
                       backup_target: Dict[str, Any],
                       host: str,
                       operation_func: callable,
                       token: Optional[str] = None) -> Any:
    """
    Helper function that handles mount, executes an operation, and unmounts.
    
    Args:
        client: DMSClient instance
        jobid: Job ID (integer)
        backup_target: Backup target dictionary
        host: Host where target should be mounted
        operation_func: Function to execute with mount_path as argument
        token: Authentication token (optional)
        
    Returns:
        Result from operation_func
        
    Example:
        >>> def my_backup(mount_path):
        ...     # Perform backup
        ...     return {'status': 'success'}
        >>> 
        >>> result = auto_mount_unmount(
        ...     client, 
        ...     12345, 
        ...     {'id': 'target-001'}, 
        ...     'compute-01', 
        ...     my_backup
        ... )
    """
    with simple_mount_context(client, jobid, backup_target, host, token) as ctx:
        return operation_func(ctx.mount_path)


# Additional helper for building request structures
def build_mount_request(jobid: int,
                       backup_target_id: str,
                       host: str,
                       backup_target_type: str = 's3',
                       additional_backup_target_fields: Optional[Dict[str, Any]] = None,
                       token: Optional[str] = None) -> Dict[str, Any]:
    """
    Build a mount request structure.
    
    Args:
        jobid: Job ID
        backup_target_id: Backup target ID
        host: Host
        backup_target_type: Type of backup target (s3, nfs, etc.)
        additional_backup_target_fields: Additional fields for backup_target
        token: Authentication token
        
    Returns:
        Complete request dictionary
        
    Example:
        >>> request = build_mount_request(
        ...     jobid=12345,
        ...     backup_target_id='target-001',
        ...     host='compute-01',
        ...     backup_target_type='s3',
        ...     additional_backup_target_fields={
        ...         'filesystem_export_mount_path': '/mnt/target-001'
        ...     }
        ... )
        >>> response = client.mount(request)
    """
    request = {
        'job': {'jobid': jobid},
        'backup_target': {
            'id': backup_target_id,
            'type': backup_target_type
        },
        'host': host
    }
    
    # Add additional backup target fields
    if additional_backup_target_fields:
        request['backup_target'].update(additional_backup_target_fields)
    
    # Add token if provided
    if token:
        request['token'] = token
    
    return request


def build_unmount_request(jobid: int,
                         backup_target_id: str,
                         host: str,
                         backup_target_type: str = 's3',
                         additional_backup_target_fields: Optional[Dict[str, Any]] = None,
                         token: Optional[str] = None) -> Dict[str, Any]:
    """
    Build an unmount request structure.
    
    Args:
        jobid: Job ID
        backup_target_id: Backup target ID
        host: Host
        backup_target_type: Type of backup target (s3, nfs, etc.)
        additional_backup_target_fields: Additional fields for backup_target
        token: Authentication token
        
    Returns:
        Complete request dictionary
        
    Example:
        >>> request = build_unmount_request(
        ...     jobid=12345,
        ...     backup_target_id='target-001',
        ...     host='compute-01'
        ... )
        >>> response = client.unmount(request)
    """
    # Same structure as mount request, action will be set by unmount() method
    return build_mount_request(
        jobid=jobid,
        backup_target_id=backup_target_id,
        host=host,
        backup_target_type=backup_target_type,
        additional_backup_target_fields=additional_backup_target_fields,
        token=token
    )
