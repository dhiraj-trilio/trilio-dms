"""
S3 Driver for mounting S3 backup targets using s3vaultfuse plugin.
"""

import os
import subprocess
import logging
import time
from typing import Dict, Optional

LOG = logging.getLogger(__name__)


class S3Driver:
    """Driver for mounting S3 using s3vaultfuse plugin."""
    
    # Mapping of credential keys to environment variable names
    ENV_VAR_MAPPING = {
        # S3 credentials
        'access_key': 'AWS_ACCESS_KEY_ID',
        'secret_key': 'AWS_SECRET_ACCESS_KEY',
        
        # s3vaultfuse specific variables
        'vault_s3_bucket': 'vault_s3_bucket',
        'vault_s3_region_name': 'vault_s3_region_name',
        'vault_s3_auth_version': 'vault_s3_auth_version',
        'vault_s3_signature_version': 'vault_s3_signature_version',
        'vault_s3_ssl': 'vault_s3_ssl',
        'vault_s3_ssl_verify': 'vault_s3_ssl_verify',
        'vault_storage_nfs_export': 'vault_storage_nfs_export',
        'bucket_object_lock': 'bucket_object_lock',
        'use_manifest_suffix': 'use_manifest_suffix',
        'vault_s3_ssl_cert': 'vault_s3_ssl_cert',
        'vault_s3_endpoint_url': 'vault_s3_endpoint_url',
        'vault_s3_max_pool_connections': 'vault_s3_max_pool_connections',
        'vault_data_directory_old': 'vault_data_directory_old',
        'vault_data_directory': 'vault_data_directory',
        'log_config_append': 'log_config_append',
    }
    
    def __init__(self, config: Dict):
        """
        Initialize S3Driver.
        
        Args:
            config: Configuration dictionary containing:
                - s3vaultfuse_path: Path to s3vaultfuse.py (default: /usr/bin/s3vaultfuse.py)
                - default_log_config: Default logging config path
                - default_data_directory: Default data directory base path
                - pidfile_dir: Directory for PID files (optional)
        """
        self.config = config
        self.s3vaultfuse_path = config.get('s3vaultfuse_path', '/usr/bin/s3vaultfuse.py')
        self.default_log_config = config.get(
            'default_log_config',
            '/etc/triliovault-object-store/object_store_logging.conf'
        )
        self.default_data_directory_base = config.get(
            'default_data_directory',
            '/var/lib/trilio/triliovault-mounts'
        )
        
        # Optional PID file directory
        self.pidfile_dir = config.get('pidfile_dir', '/run/dms/s3')
        if self.pidfile_dir:
            # Create PID directory if it doesn't exist
            try:
                os.makedirs(self.pidfile_dir, mode=0o755, exist_ok=True)
                LOG.info(f"PID file directory: {self.pidfile_dir}")
            except Exception as e:
                LOG.warning(f"Could not create PID directory {self.pidfile_dir}: {e}")
                self.pidfile_dir = None
        
        # Store active mount processes
        self.mount_processes = {}
        
        # Start background thread to reap zombie processes
        self._reaper_thread = threading.Thread(target=self._reap_zombies, daemon=True)
        self._reaper_thread.start()
        self._reaper_running = True
    
    def mount(self, target_id: str, mount_path: str, credentials: Dict) -> bool:
        """
        Mount S3 bucket using s3vaultfuse with credentials from Barbican.
        
        Args:
            target_id: Unique identifier for the backup target
            mount_path: Directory where the S3 bucket should be mounted
            credentials: Dictionary containing S3 credentials and configuration
            
        Returns:
            True if mount successful, False otherwise
        """
        try:
            LOG.info(f"Mounting S3 target {target_id} at {mount_path}")
            
            # Validate s3vaultfuse exists
            if not os.path.exists(self.s3vaultfuse_path):
                raise FileNotFoundError(
                    f"s3vaultfuse not found at {self.s3vaultfuse_path}"
                )
            
            # Create mount point if it doesn't exist
            if not os.path.exists(mount_path):
                LOG.info(f"Creating mount directory: {mount_path}")
                os.makedirs(mount_path, mode=0o755, exist_ok=True)
            
            # Check if already mounted
            if self._is_mounted(mount_path):
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
            
            # Prepare environment variables from credentials
            env_vars = self._prepare_environment(credentials, target_id, mount_path)
            
            # Log environment variables (mask sensitive data)
            LOG.debug("Environment variables for s3vaultfuse:")
            for key, value in env_vars.items():
                if 'KEY' in key or 'SECRET' in key or 'PASSWORD' in key:
                    masked_value = value[:4] + '*' * (len(value) - 8) + value[-4:] if len(value) > 8 else '****'
                    LOG.debug(f"  {key}={masked_value}")
                else:
                    LOG.debug(f"  {key}={value}")
            
            # Spawn s3vaultfuse process
            LOG.info(f"Spawning s3vaultfuse process for {mount_path}")
            process = self._spawn_s3vaultfuse(mount_path, env_vars)
            
            # Store process reference
            self.mount_processes[target_id] = {
                'process': process,
                'mount_path': mount_path,
                'pid': process.pid
            }
            
            # Write PID file if configured
            if self.pidfile_dir:
                self._write_pidfile(target_id, process.pid)
            
            # Wait a bit and verify mount
            LOG.info("Waiting for mount to be ready...")
            time.sleep(2)
            
            # Check if process is still alive
            if process.poll() is not None:
                # Process died
                stdout, stderr = '', ''
                try:
                    stdout, stderr = process.communicate(timeout=1)
                    stdout = stdout.decode() if stdout else ''
                    stderr = stderr.decode() if stderr else ''
                except:
                    pass
                
                LOG.error(f"s3vaultfuse process terminated unexpectedly")
                LOG.error(f"Exit code: {process.returncode}")
                LOG.error(f"stdout: {stdout}")
                LOG.error(f"stderr: {stderr}")
                
                # Clean up
                del self.mount_processes[target_id]
                
                # Remove PID file
                if self.pidfile_dir:
                    self._remove_pidfile(target_id)
                
                raise Exception(
                    f"s3vaultfuse failed: exit code {process.returncode}\n"
                    f"stderr: {stderr}"
                )
            
            if not self._is_mounted(mount_path):
                # Process running but mount not accessible
                LOG.error("s3vaultfuse process running but mount point not accessible")
                
                # Get process output
                try:
                    # Non-blocking read of stderr
                    import select
                    if select.select([process.stderr], [], [], 0)[0]:
                        stderr = process.stderr.read().decode()
                        LOG.error(f"Process stderr: {stderr}")
                except:
                    pass
                
                # Kill the process
                process.kill()
                del self.mount_processes[target_id]
                
                # Remove PID file
                if self.pidfile_dir:
                    self._remove_pidfile(target_id)
                
                raise Exception("Mount point not accessible after s3vaultfuse startup")
            
            LOG.info(f"Successfully mounted S3 target {target_id} at {mount_path} (PID: {process.pid})")
            return True
            
        except Exception as e:
            LOG.error(f"Failed to mount S3 target {target_id}: {e}", exc_info=True)
            return False
    
    def _prepare_environment(self, credentials: Dict, target_id: str, 
                            mount_path: str) -> Dict[str, str]:
        """
        Prepare environment variables from credentials.
        
        Args:
            credentials: Dictionary containing S3 credentials
            target_id: Target ID for generating default values
            mount_path: Mount path from filesystem_export_mount_path (used as vault_data_directory)
            
        Returns:
            Dictionary of environment variables
        """
        env_vars = os.environ.copy()
        
        # Set credentials as environment variables
        for cred_key, value in credentials.items():
            # Skip None or empty values
            if value is None or (isinstance(value, str) and value.strip() == ''):
                continue
            
            # Convert value to string
            str_value = str(value)
            
            # Check if we have a mapping for this key
            if cred_key in self.ENV_VAR_MAPPING:
                env_var_name = self.ENV_VAR_MAPPING[cred_key]
            else:
                # Use the key as-is (for custom parameters)
                env_var_name = cred_key
            
            env_vars[env_var_name] = str_value
            LOG.debug(f"Set environment variable: {env_var_name}")
        
        # IMPORTANT: Use mount_path from database as vault_data_directory
        # This ensures consistency between what's in DB and what s3vaultfuse uses
        if 'vault_data_directory' not in env_vars:
            # If not provided in credentials, use the mount_path from DB
            env_vars['vault_data_directory'] = mount_path
            LOG.info(f"Using mount_path as vault_data_directory: {mount_path}")
        else:
            # If provided in credentials, verify it matches mount_path
            if env_vars['vault_data_directory'] != mount_path:
                LOG.warning(
                    f"vault_data_directory from credentials ({env_vars['vault_data_directory']}) "
                    f"differs from filesystem_export_mount_path ({mount_path}). "
                    f"Using filesystem_export_mount_path: {mount_path}"
                )
                env_vars['vault_data_directory'] = mount_path
        
        if 'log_config_append' not in env_vars:
            env_vars['log_config_append'] = self.default_log_config
            LOG.debug(f"Set default log_config_append: {self.default_log_config}")
        
        # Ensure vault_data_directory (mount_path) exists
        vault_data_dir = env_vars.get('vault_data_directory')
        if vault_data_dir and not os.path.exists(vault_data_dir):
            LOG.info(f"Creating mount directory: {vault_data_dir}")
            os.makedirs(vault_data_dir, mode=0o755, exist_ok=True)
        
        return env_vars
    
    def _spawn_s3vaultfuse(self, mount_path: str, env_vars: Dict[str, str]) -> subprocess.Popen:
        """
        Spawn s3vaultfuse process.
        
        Args:
            mount_path: Directory where S3 bucket should be mounted
            env_vars: Environment variables for the process
            
        Returns:
            Popen process object
        """
        # Build command - just the executable and mount path
        # All configuration comes from environment variables
        cmd = [self.s3vaultfuse_path]
        
        LOG.info(f"Executing: {' '.join(cmd)}")
        
        # Spawn process with environment variables
        # Use Popen to get a handle to the process without waiting
        process = subprocess.Popen(
            cmd,
            env=env_vars,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,  # Close stdin
            start_new_session=True,  # Detach from parent process group
            preexec_fn=os.setpgrp  # Create new process group
        )
        
        LOG.info(f"s3vaultfuse process started with PID: {process.pid}")
        
        # Give it a moment to start
        time.sleep(0.5)
        
        # Check if process is still alive (didn't crash immediately)
        poll_result = process.poll()
        if poll_result is not None:
            # Process already exited
            stdout, stderr = process.communicate(timeout=1)
            LOG.error(f"s3vaultfuse exited immediately with code {poll_result}")
            LOG.error(f"stdout: {stdout.decode() if stdout else '(empty)'}")
            LOG.error(f"stderr: {stderr.decode() if stderr else '(empty)'}")
            raise Exception(f"s3vaultfuse failed to start (exit code {poll_result})")
        
        return process
    
    def unmount(self, target_id: str, mount_path: str) -> bool:
        """
        Unmount S3 bucket.
        
        Args:
            target_id: Target ID for process lookup
            mount_path: Directory to unmount
            
        Returns:
            True if unmount successful, False otherwise
        """
        try:
            LOG.info(f"Unmounting S3 from {mount_path}")
            
            # Check if mounted
            if not self._is_mounted(mount_path):
                LOG.warning(f"{mount_path} is not mounted")
                return True
            
            # Find and terminate s3vaultfuse process
            if target_id and target_id in self.mount_processes:
                process_info = self.mount_processes[target_id]
                process = process_info['process']
                
                LOG.info(f"Terminating s3vaultfuse process (PID: {process.pid})")
                
                # Try graceful termination first
                process.terminate()
                
                try:
                    # Wait up to 5 seconds for graceful shutdown
                    process.wait(timeout=5)
                    LOG.info("s3vaultfuse process terminated gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill if still running
                    LOG.warning("s3vaultfuse didn't terminate gracefully, forcing kill")
                    process.kill()
                    process.wait()
                    LOG.info("s3vaultfuse process killed")
                
                # Remove from tracking
                del self.mount_processes[target_id]
                
                # Remove PID file
                if self.pidfile_dir:
                    self._remove_pidfile(target_id)
            else:
                # Process not tracked, try fusermount
                LOG.info("Process not tracked, attempting fusermount -u")
                result = subprocess.run(
                    ['fusermount', '-u', mount_path],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    LOG.error(f"fusermount failed: {result.stderr}")
                    return False
            
            # Verify unmounted
            time.sleep(1)
            if self._is_mounted(mount_path):
                LOG.error(f"Mount point {mount_path} still appears to be mounted")
                return False
            
            LOG.info(f"Successfully unmounted {mount_path}")
            return True
            
        except Exception as e:
            LOG.error(f"Failed to unmount {mount_path}: {e}", exc_info=True)
            return False
    
    def _is_mounted(self, mount_path: str) -> bool:
        """
        Check if a path is mounted and accessible.
        
        For FUSE mounts, we need to verify:
        1. Entry exists in /proc/mounts
        2. Directory is actually accessible (not stale)
        3. Process is still running (if tracked)
        
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
            # Try to stat the mount point - this will hang on stale mounts
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
            except TimeoutError:
                LOG.warning(f"Mount point {mount_path} appears stale (timeout)")
                return False
            except (OSError, PermissionError) as e:
                LOG.warning(f"Mount point {mount_path} not accessible: {e}")
                signal.alarm(0)  # Cancel alarm
                return False
            finally:
                signal.signal(signal.SIGALRM, old_handler)
            
            # Additional check: if we're tracking this mount, verify process is running
            for target_id, info in self.mount_processes.items():
                if info['mount_path'] == mount_path:
                    process = info['process']
                    # Check if process is still alive
                    if hasattr(process, 'poll'):
                        if process.poll() is not None:
                            LOG.warning(f"Mount at {mount_path} has terminated process (PID {info['pid']})")
                            return False
                    break
            
            return True
            
        except Exception as e:
            LOG.error(f"Error checking mount status for {mount_path}: {e}")
            return False
    
    def _find_target_by_mount_path(self, mount_path: str) -> Optional[str]:
        """
        Find target ID by mount path.
        
        Args:
            mount_path: Mount path to search for
            
        Returns:
            Target ID if found, None otherwise
        """
        for target_id, info in self.mount_processes.items():
            if info['mount_path'] == mount_path:
                return target_id
        return None
    
    def get_mount_info(self, target_id: str) -> Optional[Dict]:
        """
        Get information about a mounted target.
        
        Args:
            target_id: Target ID
            
        Returns:
            Dictionary with mount information or None if not mounted
        """
        if target_id in self.mount_processes:
            info = self.mount_processes[target_id]
            process = info['process']
            
            # Check if process is still running
            if process.poll() is None:
                return {
                    'target_id': target_id,
                    'mount_path': info['mount_path'],
                    'pid': info['pid'],
                    'status': 'running'
                }
            else:
                return {
                    'target_id': target_id,
                    'mount_path': info['mount_path'],
                    'pid': info['pid'],
                    'status': 'terminated',
                    'exit_code': process.returncode
                }
        
        return None
    
    def list_mounts(self) -> Dict[str, Dict]:
        """
        List all active mounts.
        
        Returns:
            Dictionary of target_id -> mount_info
        """
        return {
            target_id: self.get_mount_info(target_id)
            for target_id in self.mount_processes.keys()
        }
    
    def cleanup_stale_mount(self, mount_path: str) -> bool:
        """
        Clean up a stale mount entry.
        
        This handles cases where:
        - Entry exists in /proc/mounts but mount is not accessible
        - s3vaultfuse process has died
        - Mount is hung or in a bad state
        
        Args:
            mount_path: Path to clean up
            
        Returns:
            True if cleanup successful, False otherwise
        """
        try:
            LOG.info(f"Attempting to clean up stale mount: {mount_path}")
            
            # First, try to find and kill any associated process
            target_id = self._find_target_by_mount_path(mount_path)
            if target_id and target_id in self.mount_processes:
                process_info = self.mount_processes[target_id]
                process = process_info['process']
                
                LOG.info(f"Killing stale process PID {process_info['pid']}")
                try:
                    process.kill()
                    process.wait(timeout=5)
                except:
                    pass
                
                del self.mount_processes[target_id]
            
            # Try fusermount -uz (lazy unmount) for stale mounts
            LOG.info(f"Attempting fusermount -uz {mount_path}")
            result = subprocess.run(
                ['fusermount', '-uz', mount_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                LOG.info(f"Successfully cleaned up stale mount: {mount_path}")
                return True
            else:
                LOG.warning(f"fusermount failed: {result.stderr}")
            
            # If fusermount failed, try umount -l (lazy unmount)
            LOG.info(f"Attempting umount -l {mount_path}")
            result = subprocess.run(
                ['umount', '-l', mount_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                LOG.info(f"Successfully cleaned up stale mount with umount -l: {mount_path}")
                return True
            else:
                LOG.error(f"umount -l failed: {result.stderr}")
                return False
            
        except subprocess.TimeoutExpired:
            LOG.error(f"Timeout while cleaning up {mount_path}")
            return False
        except Exception as e:
            LOG.error(f"Error cleaning up stale mount {mount_path}: {e}", exc_info=True)
            return False
    
    def _reap_zombies(self):
        """
        Background thread to reap zombie processes.
        
        Periodically checks tracked processes and calls wait() on terminated ones
        to prevent zombie processes from accumulating.
        """
        while self._reaper_running:
            try:
                time.sleep(5)  # Check every 5 seconds
                
                # Make a copy of keys to avoid dictionary size change during iteration
                target_ids = list(self.mount_processes.keys())
                
                for target_id in target_ids:
                    if target_id not in self.mount_processes:
                        continue
                    
                    process_info = self.mount_processes[target_id]
                    process = process_info['process']
                    
                    # Check if process has terminated
                    poll_result = process.poll()
                    if poll_result is not None:
                        # Process has terminated, reap it
                        try:
                            process.wait(timeout=1)
                            LOG.warning(
                                f"s3vaultfuse process for {target_id} terminated "
                                f"(PID {process_info['pid']}, exit code {poll_result})"
                            )
                            
                            # Remove PID file for terminated process
                            if self.pidfile_dir:
                                self._remove_pidfile(target_id)
                        except:
                            pass
                
            except Exception as e:
                LOG.error(f"Error in zombie reaper: {e}", exc_info=True)
    
    def _write_pidfile(self, target_id: str, pid: int):
        """
        Write PID file for a mount.
        
        Args:
            target_id: Target identifier
            pid: Process ID
        """
        if not self.pidfile_dir:
            return
        
        try:
            pidfile_path = os.path.join(self.pidfile_dir, f"{target_id}.pid")
            with open(pidfile_path, 'w') as f:
                f.write(str(pid))
            LOG.debug(f"Wrote PID file: {pidfile_path}")
        except Exception as e:
            LOG.warning(f"Could not write PID file for {target_id}: {e}")
    
    def _remove_pidfile(self, target_id: str):
        """
        Remove PID file for a mount.
        
        Args:
            target_id: Target identifier
        """
        if not self.pidfile_dir:
            return
        
        try:
            pidfile_path = os.path.join(self.pidfile_dir, f"{target_id}.pid")
            if os.path.exists(pidfile_path):
                os.remove(pidfile_path)
                LOG.debug(f"Removed PID file: {pidfile_path}")
        except Exception as e:
            LOG.warning(f"Could not remove PID file for {target_id}: {e}")
    
    def _read_pidfile(self, target_id: str) -> Optional[int]:
        """
        Read PID from PID file.
        
        Args:
            target_id: Target identifier
            
        Returns:
            PID if file exists and is valid, None otherwise
        """
        if not self.pidfile_dir:
            return None
        
        try:
            pidfile_path = os.path.join(self.pidfile_dir, f"{target_id}.pid")
            if os.path.exists(pidfile_path):
                with open(pidfile_path, 'r') as f:
                    return int(f.read().strip())
        except Exception as e:
            LOG.warning(f"Could not read PID file for {target_id}: {e}")
        
        return None
