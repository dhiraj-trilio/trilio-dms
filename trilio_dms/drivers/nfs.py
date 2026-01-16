"""NFS mount driver implementation"""

import os
import subprocess
from typing import Dict, Any

from trilio_dms.drivers.base import BaseMountDriver
from trilio_dms.utils.logger import get_logger
from trilio_dms.utils.exceptions import MountException, UnmountException

LOG = get_logger(__name__)


class NFSDriver(BaseMountDriver):
    """Driver for mounting NFS shares."""
    
    def mount(self, target_id: str, mount_path: str, share: str, options: str = 'defaults') -> bool:
        """
        Mount NFS share.
        
        Args:
            target_id: Target identifier
            mount_path: Local mount point
            share: NFS share (server:/export/path)
            options: Mount options
            
        Returns:
            True if successful, False otherwise
        """
        try:
            LOG.info(f"Mounting NFS share {share} at {mount_path}")
            
            # Create mount point if it doesn't exist
            if not os.path.exists(mount_path):
                LOG.info(f"Creating mount directory: {mount_path}")
                os.makedirs(mount_path, mode=0o755, exist_ok=True)
            
            # Check if already mounted
            if self.is_mounted(mount_path):
                LOG.warning(f"{mount_path} appears to be already mounted")
                # Verify it's actually accessible, not stale
                try:
                    os.listdir(mount_path)
                    LOG.info(f"{mount_path} is accessible, mount is valid")
                    return True
                except Exception as e:
                    LOG.warning(f"{mount_path} is not accessible, may be stale: {e}")
                    LOG.info("Attempting to clean up stale mount")
                    if not self.cleanup_stale_mount(mount_path):
                        raise Exception(f"Failed to clean up stale mount at {mount_path}")
            
            # Mount the NFS share
            cmd = ['mount', '-t', 'nfs', '-o', options, share, mount_path]
            LOG.debug(f"Executing: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                LOG.error(f"Mount failed: {result.stderr}")
                return False
            
            # Verify mount
            if not self.is_mounted(mount_path):
                LOG.error("Mount command succeeded but mount not verified")
                return False
            
            LOG.info(f"Successfully mounted {share} at {mount_path}")
            return True
            
        except subprocess.TimeoutExpired:
            LOG.error(f"Mount command timed out for {share}")
            return False
        except Exception as e:
            LOG.error(f"Failed to mount {share}: {e}", exc_info=True)
            return False
    
    def unmount(self, target_id: str, mount_path: str) -> bool:
        """
        Unmount NFS share.
        
        Args:
            target_id: Target identifier
            mount_path: Mount point to unmount
            
        Returns:
            True if successful, False otherwise
        """
        try:
            LOG.info(f"Unmounting NFS from {mount_path}")
            
            # Check if mounted
            if not self.is_mounted(mount_path):
                LOG.warning(f"{mount_path} is not mounted")
                return True
            
            # Try normal unmount first
            result = subprocess.run(
                ['umount', mount_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                LOG.info(f"Successfully unmounted {mount_path}")
                return True
            
            # If normal unmount failed, try lazy unmount
            LOG.warning(f"Normal unmount failed, trying lazy unmount: {result.stderr}")
            result = subprocess.run(
                ['umount', '-l', mount_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                LOG.info(f"Successfully lazy unmounted {mount_path}")
                return True
            else:
                LOG.error(f"Lazy unmount failed: {result.stderr}")
                return False
            
        except subprocess.TimeoutExpired:
            LOG.error(f"Unmount command timed out for {mount_path}")
            # Try force unmount as last resort
            try:
                subprocess.run(['umount', '-f', '-l', mount_path], timeout=5)
                return True
            except:
                return False
        except Exception as e:
            LOG.error(f"Failed to unmount {mount_path}: {e}", exc_info=True)
            return False
    
    def is_mounted(self, mount_path: str) -> bool:
        """
        Check if NFS share is mounted and accessible.
        
        Args:
            mount_path: Path to check
            
        Returns:
            True if mounted and accessible, False otherwise
        """
        try:
            # Check /proc/mounts
            mount_entry_exists = False
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == mount_path:
                        mount_entry_exists = True
                        break
            
            if not mount_entry_exists:
                return False
            
            # Check if mount point is accessible (not stale)
            # Use a timeout to detect stale mounts
            def timeout_handler(signum, frame):
                raise TimeoutError("Mount point access timeout")
            
            # Set a 2-second timeout for the stat call
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(2)
            
            try:
                # Try to access the mount point
                os.stat(mount_path)
                # Try to list directory (additional verification)
                os.listdir(mount_path)
                signal.alarm(0)  # Cancel alarm
                return True
            except TimeoutError:
                LOG.warning(f"NFS mount point {mount_path} appears stale (timeout)")
                signal.alarm(0)  # Cancel alarm
                return False
            except (OSError, PermissionError) as e:
                LOG.warning(f"NFS mount point {mount_path} not accessible: {e}")
                signal.alarm(0)  # Cancel alarm
                return False
            finally:
                signal.signal(signal.SIGALRM, old_handler)
            
        except Exception as e:
            LOG.error(f"Error checking NFS mount status for {mount_path}: {e}")
            return False
    
    def cleanup_stale_mount(self, mount_path: str) -> bool:
        """
        Clean up a stale NFS mount entry.
        
        Args:
            mount_path: Path to clean up
            
        Returns:
            True if cleanup successful, False otherwise
        """
        try:
            LOG.info(f"Attempting to clean up stale NFS mount: {mount_path}")
            
            # Try lazy unmount
            LOG.info(f"Attempting umount -l {mount_path}")
            result = subprocess.run(
                ['umount', '-l', mount_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                LOG.info(f"Successfully cleaned up stale NFS mount: {mount_path}")
                return True
            else:
                LOG.warning(f"umount -l failed: {result.stderr}")
            
            # If lazy unmount failed, try force unmount
            LOG.info(f"Attempting umount -f -l {mount_path}")
            result = subprocess.run(
                ['umount', '-f', '-l', mount_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                LOG.info(f"Successfully cleaned up stale NFS mount with force: {mount_path}")
                return True
            else:
                LOG.error(f"Force unmount failed: {result.stderr}")
                return False
            
        except subprocess.TimeoutExpired:
            LOG.error(f"Timeout while cleaning up NFS mount {mount_path}")
            return False
        except Exception as e:
            LOG.error(f"Error cleaning up stale NFS mount {mount_path}: {e}", exc_info=True)
            return False
    
    def get_mount_info(self, mount_path: str) -> Dict[str, Any]:
        """Get NFS mount information"""
        try:
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 4 and parts[1] == mount_path:
                        return {
                            'device': parts[0],
                            'mount_point': parts[1],
                            'fs_type': parts[2],
                            'options': parts[3]
                        }
            return {}
        except Exception as e:
            LOG.error(f"Error getting mount info: {e}")
            return {}

