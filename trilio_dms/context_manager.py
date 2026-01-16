# trilio_dms/context_manager.py
"""
Context managers for automatic mount/unmount operations.

This module provides convenient context managers that handle mount and unmount
operations automatically, ensuring proper cleanup even when exceptions occur.
"""

import logging
from contextlib import contextmanager
from typing import Optional, Dict, Any

from .client import DMSClient, DMSClientError

logger = logging.getLogger(__name__)


@contextmanager
def mount_context(client: DMSClient, 
                  jobid: int, 
                  backup_target_id: str, 
                  host: str,
                  token: str,
                  mount_options: Optional[Dict[str, Any]] = None):
    """
    Context manager for automatic mount/unmount with proper locking.
    
    This context manager ensures that:
    1. The backup target is mounted before entering the context
    2. The backup target is unmounted when exiting the context
    3. Unmount happens even if an exception occurs
    4. All operations use proper locking
    
    Args:
        client: DMSClient instance
        jobid: Job ID (integer)
        backup_target_id: Backup target ID
        host: Target host
        token: Authentication token
        mount_options: Optional mount-specific options
        
    Yields:
        Dict: Mount information including mount_path and other details
        
    Raises:
        DMSClientError: If mount or unmount operation fails
        
    Example:
        >>> from trilio_dms import DMSClient, mount_context
        >>> 
        >>> client = DMSClient(...)
        >>> 
        >>> # Automatic mount/unmount
        >>> with mount_context(client, 12345, 'target-001', 'compute-01', 'token') as mount:
        ...     print(f"Mounted at: {mount['mount_path']}")
        ...     # Perform backup operations
        ...     perform_backup(mount['mount_path'])
        ...     # Automatic unmount on exit (even if exception occurs)
        
        >>> # Example with exception handling
        >>> try:
        ...     with mount_context(client, 12345, 'target-001', 'compute-01', 'token') as mount:
        ...         raise Exception("Something went wrong!")
        ... except Exception:
        ...     pass  # Mount is still automatically unmounted
    """
    mount_info = None
    unmount_attempted = False
    
    try:
        # Mount operation (with locking handled internally by client)
        logger.info(
            f"Mounting backup target {backup_target_id} for job {jobid} on host {host}"
        )
        
        mount_info = client.mount_backup_target(
            jobid=jobid,
            backup_target_id=backup_target_id,
            host=host,
            token=token,
            mount_options=mount_options
        )
        
        if not mount_info.get('success'):
            raise DMSClientError(
                f"Mount failed for jobid={jobid}, "
                f"backup_target_id={backup_target_id}"
            )
        
        logger.info(
            f"Successfully mounted {backup_target_id} at {mount_info['mount_path']} "
            f"(reused_existing={mount_info.get('reused_existing', False)})"
        )
        
        # Yield control to the caller
        yield mount_info
        
    except Exception as e:
        # Log the error but don't suppress it
        logger.error(
            f"Error occurred while using mount for jobid={jobid}, "
            f"backup_target_id={backup_target_id}: {e}",
            exc_info=True
        )
        raise
        
    finally:
        # Unmount operation (with locking handled internally by client)
        if mount_info and mount_info.get('success'):
            try:
                unmount_attempted = True
                logger.info(
                    f"Unmounting backup target {backup_target_id} for job {jobid}"
                )
                
                result = client.unmount_backup_target(
                    jobid=jobid,
                    backup_target_id=backup_target_id,
                    host=host
                )
                
                if result['success']:
                    if result['unmounted']:
                        logger.info(
                            f"Successfully unmounted {backup_target_id} on {host} "
                            f"(physically unmounted)"
                        )
                    else:
                        logger.info(
                            f"Ledger updated for {backup_target_id} on {host} "
                            f"({result['active_mounts_remaining']} other jobs still using mount)"
                        )
                else:
                    logger.warning(
                        f"Unmount returned unsuccessful for jobid={jobid}, "
                        f"backup_target_id={backup_target_id}: {result.get('message')}"
                    )
                    
            except Exception as e:
                logger.error(
                    f"Error during unmount for jobid={jobid}, "
                    f"backup_target_id={backup_target_id}: {e}",
                    exc_info=True
                )
                # Don't raise the unmount error - we want to preserve the original exception
                # if one occurred in the try block


@contextmanager
def batch_mount_context(client: DMSClient,
                       jobid: int,
                       targets: list[Dict[str, str]],
                       token: str):
    """
    Context manager for mounting multiple backup targets at once.
    
    This is useful when a job needs to mount multiple backup targets simultaneously.
    All targets are mounted before entering the context, and all are unmounted
    when exiting (in reverse order of mounting).
    
    Args:
        client: DMSClient instance
        jobid: Job ID (integer)
        targets: List of target dictionaries, each containing:
                 {'backup_target_id': str, 'host': str, 'mount_options': dict}
        token: Authentication token
        
    Yields:
        List[Dict]: List of mount information for each target
        
    Example:
        >>> from trilio_dms import DMSClient, batch_mount_context
        >>> 
        >>> client = DMSClient(...)
        >>> 
        >>> targets = [
        ...     {'backup_target_id': 'target-001', 'host': 'compute-01'},
        ...     {'backup_target_id': 'target-002', 'host': 'compute-01'},
        ...     {'backup_target_id': 'target-003', 'host': 'compute-02'}
        ... ]
        >>> 
        >>> with batch_mount_context(client, 12345, targets, 'token') as mounts:
        ...     for mount in mounts:
        ...         print(f"Mounted {mount['backup_target_id']} at {mount['mount_path']}")
        ...         perform_backup(mount['mount_path'])
        ...     # All mounts are automatically unmounted on exit
    """
    mounted_targets = []
    
    try:
        # Mount all targets
        for target in targets:
            backup_target_id = target['backup_target_id']
            host = target['host']
            mount_options = target.get('mount_options')
            
            logger.info(
                f"Batch mount: Mounting {backup_target_id} for job {jobid}"
            )
            
            try:
                mount_info = client.mount_backup_target(
                    jobid=jobid,
                    backup_target_id=backup_target_id,
                    host=host,
                    token=token,
                    mount_options=mount_options
                )
                
                if mount_info.get('success'):
                    mounted_targets.append(mount_info)
                    logger.info(
                        f"Batch mount: Successfully mounted {backup_target_id}"
                    )
                else:
                    logger.error(
                        f"Batch mount: Failed to mount {backup_target_id}"
                    )
                    raise DMSClientError(
                        f"Failed to mount {backup_target_id}: "
                        f"{mount_info.get('message')}"
                    )
                    
            except Exception as e:
                logger.error(
                    f"Batch mount: Error mounting {backup_target_id}: {e}",
                    exc_info=True
                )
                raise
        
        # Yield all mount information
        yield mounted_targets
        
    finally:
        # Unmount all targets in reverse order
        for mount_info in reversed(mounted_targets):
            try:
                backup_target_id = mount_info['backup_target_id']
                host = mount_info['host']
                
                logger.info(
                    f"Batch unmount: Unmounting {backup_target_id} for job {jobid}"
                )
                
                result = client.unmount_backup_target(
                    jobid=jobid,
                    backup_target_id=backup_target_id,
                    host=host
                )
                
                if result['success']:
                    logger.info(
                        f"Batch unmount: Successfully unmounted {backup_target_id} "
                        f"(physically_unmounted={result['unmounted']})"
                    )
                else:
                    logger.warning(
                        f"Batch unmount: Unmount unsuccessful for {backup_target_id}: "
                        f"{result.get('message')}"
                    )
                    
            except Exception as e:
                logger.error(
                    f"Batch unmount: Error unmounting {backup_target_id}: {e}",
                    exc_info=True
                )
                # Continue with other unmounts even if one fails


class MountContext:
    """
    Class-based context manager for mount/unmount operations.
    
    This provides an alternative to the function-based mount_context for cases
    where more control is needed over the mount/unmount lifecycle.
    
    Example:
        >>> from trilio_dms import DMSClient, MountContext
        >>> 
        >>> client = DMSClient(...)
        >>> 
        >>> # Using with statement
        >>> with MountContext(client, 12345, 'target-001', 'compute-01', 'token') as ctx:
        ...     print(f"Mounted at: {ctx.mount_path}")
        ...     perform_backup(ctx.mount_path)
        
        >>> # Manual control
        >>> ctx = MountContext(client, 12345, 'target-001', 'compute-01', 'token')
        >>> try:
        ...     ctx.mount()
        ...     print(f"Mounted at: {ctx.mount_path}")
        ...     perform_backup(ctx.mount_path)
        ... finally:
        ...     ctx.unmount()
    """
    
    def __init__(self,
                 client: DMSClient,
                 jobid: int,
                 backup_target_id: str,
                 host: str,
                 token: str,
                 mount_options: Optional[Dict[str, Any]] = None):
        """
        Initialize mount context.
        
        Args:
            client: DMSClient instance
            jobid: Job ID (integer)
            backup_target_id: Backup target ID
            host: Target host
            token: Authentication token
            mount_options: Optional mount-specific options
        """
        self.client = client
        self.jobid = jobid
        self.backup_target_id = backup_target_id
        self.host = host
        self.token = token
        self.mount_options = mount_options
        
        self._mount_info = None
        self._is_mounted = False
    
    @property
    def mount_path(self) -> Optional[str]:
        """Get the mount path if mounted."""
        if self._mount_info:
            return self._mount_info.get('mount_path')
        return None
    
    @property
    def is_mounted(self) -> bool:
        """Check if currently mounted."""
        return self._is_mounted
    
    @property
    def mount_info(self) -> Optional[Dict[str, Any]]:
        """Get full mount information."""
        return self._mount_info
    
    def mount(self) -> Dict[str, Any]:
        """
        Perform mount operation.
        
        Returns:
            Dict with mount information
            
        Raises:
            DMSClientError: If already mounted or mount fails
        """
        if self._is_mounted:
            raise DMSClientError("Already mounted")
        
        logger.info(
            f"MountContext: Mounting {self.backup_target_id} for job {self.jobid}"
        )
        
        self._mount_info = self.client.mount_backup_target(
            jobid=self.jobid,
            backup_target_id=self.backup_target_id,
            host=self.host,
            token=self.token,
            mount_options=self.mount_options
        )
        
        if self._mount_info.get('success'):
            self._is_mounted = True
            logger.info(
                f"MountContext: Successfully mounted at {self.mount_path}"
            )
        else:
            raise DMSClientError(
                f"Mount failed: {self._mount_info.get('message')}"
            )
        
        return self._mount_info
    
    def unmount(self) -> Dict[str, Any]:
        """
        Perform unmount operation.
        
        Returns:
            Dict with unmount result
            
        Raises:
            DMSClientError: If not mounted or unmount fails
        """
        if not self._is_mounted:
            raise DMSClientError("Not mounted")
        
        logger.info(
            f"MountContext: Unmounting {self.backup_target_id} for job {self.jobid}"
        )
        
        result = self.client.unmount_backup_target(
            jobid=self.jobid,
            backup_target_id=self.backup_target_id,
            host=self.host
        )
        
        if result['success']:
            self._is_mounted = False
            logger.info(
                f"MountContext: Successfully unmounted "
                f"(physically_unmounted={result['unmounted']})"
            )
        else:
            logger.warning(
                f"MountContext: Unmount unsuccessful: {result.get('message')}"
            )
        
        return result
    
    def __enter__(self):
        """Context manager entry."""
        self.mount()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._is_mounted:
            try:
                self.unmount()
            except Exception as e:
                logger.error(f"Error during unmount in __exit__: {e}", exc_info=True)
                # Don't suppress the original exception
        return False


# Convenience function for simple use cases
def auto_mount_unmount(client: DMSClient,
                       jobid: int,
                       backup_target_id: str,
                       host: str,
                       token: str,
                       operation_func: callable,
                       mount_options: Optional[Dict[str, Any]] = None):
    """
    Helper function that handles mount, executes an operation, and unmounts.
    
    This is useful for simple operations that don't need the full context manager.
    
    Args:
        client: DMSClient instance
        jobid: Job ID (integer)
        backup_target_id: Backup target ID
        host: Target host
        token: Authentication token
        operation_func: Function to execute with mount_path as argument
        mount_options: Optional mount-specific options
        
    Returns:
        Result from operation_func
        
    Example:
        >>> from trilio_dms import DMSClient, auto_mount_unmount
        >>> 
        >>> def my_backup(mount_path):
        ...     # Perform backup
        ...     return {'status': 'success'}
        >>> 
        >>> client = DMSClient(...)
        >>> result = auto_mount_unmount(
        ...     client, 12345, 'target-001', 'compute-01', 'token', my_backup
        ... )
        >>> print(result)  # {'status': 'success'}
    """
    with mount_context(client, jobid, backup_target_id, host, token, mount_options) as mount:
        return operation_func(mount['mount_path'])
