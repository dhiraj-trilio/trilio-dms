"""
Global lock manager for DMS client mount/unmount operations.
Uses file-based locking to ensure only one process can perform
mount/unmount operations at a time on the same server.
"""

import os
import fcntl
import time
import errno
from contextlib import contextmanager
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DMSLockManager:
    """
    Manages global locks for DMS mount/unmount operations.
    Uses file-based locking (flock) for cross-process synchronization.
    """
    
    DEFAULT_LOCK_DIR = "/var/lock/trilio-dms"
    LOCK_TIMEOUT = 300  # 5 minutes default timeout
    
    def __init__(self, lock_dir: Optional[str] = None, timeout: int = LOCK_TIMEOUT):
        """
        Initialize the lock manager.
        
        Args:
            lock_dir: Directory to store lock files (default: /var/lock/trilio-dms)
            timeout: Maximum time to wait for lock acquisition in seconds
        """
        self.lock_dir = lock_dir or self.DEFAULT_LOCK_DIR
        self.timeout = timeout
        self._lock_file = None
        
        # Create lock directory if it doesn't exist
        os.makedirs(self.lock_dir, mode=0o755, exist_ok=True)
    
    @contextmanager
    def acquire_lock(self, operation: str = "mount_unmount"):
        """
        Context manager to acquire a global lock for mount/unmount operations.
        
        Args:
            operation: Name of the operation (used in lock filename)
            
        Yields:
            bool: True if lock was acquired
            
        Raises:
            TimeoutError: If lock cannot be acquired within timeout period
            
        Example:
            with lock_manager.acquire_lock():
                # Perform mount/unmount operation
                pass
        """
        lock_file_path = os.path.join(self.lock_dir, f"dms_{operation}.lock")
        lock_file = None
        acquired = False
        
        try:
            # Open lock file
            lock_file = open(lock_file_path, 'w')
            self._lock_file = lock_file
            
            # Try to acquire lock with timeout
            start_time = time.time()
            while True:
                try:
                    # Non-blocking lock attempt
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    logger.info(f"Successfully acquired lock for {operation}")
                    break
                except IOError as e:
                    if e.errno != errno.EAGAIN:
                        raise
                    
                    # Check timeout
                    elapsed = time.time() - start_time
                    if elapsed >= self.timeout:
                        raise TimeoutError(
                            f"Could not acquire lock for {operation} "
                            f"after {self.timeout} seconds"
                        )
                    
                    # Wait a bit before retrying
                    time.sleep(0.1)
                    logger.debug(
                        f"Waiting for lock on {operation} "
                        f"({elapsed:.1f}s elapsed)..."
                    )
            
            yield True
            
        finally:
            # Release lock
            if acquired and lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    logger.info(f"Released lock for {operation}")
                except Exception as e:
                    logger.error(f"Error releasing lock: {e}")
            
            # Close and cleanup
            if lock_file:
                try:
                    lock_file.close()
                except Exception as e:
                    logger.error(f"Error closing lock file: {e}")
            
            self._lock_file = None


# Singleton instance for global use
_global_lock_manager = None


def get_lock_manager(lock_dir: Optional[str] = None, 
                     timeout: int = DMSLockManager.LOCK_TIMEOUT) -> DMSLockManager:
    """
    Get or create the global lock manager instance.
    
    Args:
        lock_dir: Directory for lock files
        timeout: Lock acquisition timeout in seconds
        
    Returns:
        DMSLockManager: The global lock manager instance
    """
    global _global_lock_manager
    if _global_lock_manager is None:
        _global_lock_manager = DMSLockManager(lock_dir=lock_dir, timeout=timeout)
    return _global_lock_manager

