"""
S3VaultFuse Manager for Trilio DMS
Manages s3vaultfuse process spawning and lifecycle with comprehensive tracking
Tracks processes in memory AND persists PID files to disk
"""

import os
import logging
import subprocess
import signal
import time
import psutil
from typing import Dict, Any, Optional, List
from datetime import datetime
from threading import Lock
from pathlib import Path

logger = logging.getLogger(__name__)


class S3VaultFuseManager:
    """
    Manager for s3vaultfuse processes with comprehensive tracking
    
    Tracks processes in two ways:
    1. In-memory registry for fast access
    2. PID files on disk for persistence across restarts
    
    PID files stored at: /run/dms/s3/<backup_target_id>.pid
    """
    
    S3VAULTFUSE_BIN = '/usr/bin/s3vaultfuse.py'
    PID_DIR = '/run/dms/s3'
    
    def __init__(self, pid_dir: Optional[str] = None):
        """
        Initialize manager with process tracking
        
        Args:
            pid_dir: Directory for PID files (default: /run/dms/s3)
        """
        # Main process registry: target_id -> process_info
        self.processes = {}  # Dict[str, Dict[str, Any]]
        
        # Lock for thread-safe operations
        self._lock = Lock()
        
        # Track all spawned processes for cleanup
        self._all_pids = set()  # Set[int]
        
        # PID directory
        self.pid_dir = pid_dir or self.PID_DIR
        
        # Ensure PID directory exists
        self._ensure_pid_directory()
        
        # Load existing PID files on startup
        self._load_existing_pids()
        
        logger.info(f"S3VaultFuseManager initialized with PID directory: {self.pid_dir}")
    
    def _ensure_pid_directory(self):
        """Ensure PID directory exists"""
        try:
            os.makedirs(self.pid_dir, mode=0o755, exist_ok=True)
            logger.info(f"PID directory ready: {self.pid_dir}")
        except Exception as e:
            logger.error(f"Failed to create PID directory {self.pid_dir}: {e}")
            raise
    
    def _get_pid_file_path(self, target_id: str) -> str:
        """
        Get PID file path for target
        
        Args:
            target_id: Backup target ID
            
        Returns:
            Full path to PID file: /run/dms/s3/<target_id>.pid
        """
        return os.path.join(self.pid_dir, f"{target_id}.pid")
    
    def _write_pid_file(self, target_id: str, pid: int) -> bool:
        """
        Write PID to file
        
        Args:
            target_id: Backup target ID
            pid: Process ID
            
        Returns:
            True if successful
        """
        pid_file = self._get_pid_file_path(target_id)
        try:
            with open(pid_file, 'w') as f:
                f.write(str(pid))
            logger.info(f"✓ PID file written: {pid_file} (PID: {pid})")
            return True
        except Exception as e:
            logger.error(f"Failed to write PID file {pid_file}: {e}")
            return False
    
    def _read_pid_file(self, target_id: str) -> Optional[int]:
        """
        Read PID from file
        
        Args:
            target_id: Backup target ID
            
        Returns:
            PID if file exists and valid, None otherwise
        """
        pid_file = self._get_pid_file_path(target_id)
        try:
            if not os.path.exists(pid_file):
                return None
            
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            logger.debug(f"Read PID {pid} from file: {pid_file}")
            return pid
        except Exception as e:
            logger.warning(f"Failed to read PID file {pid_file}: {e}")
            return None
    
    def _delete_pid_file(self, target_id: str) -> bool:
        """
        Delete PID file
        
        Args:
            target_id: Backup target ID
            
        Returns:
            True if successful
        """
        pid_file = self._get_pid_file_path(target_id)
        try:
            if os.path.exists(pid_file):
                os.remove(pid_file)
                logger.info(f"✓ PID file deleted: {pid_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete PID file {pid_file}: {e}")
            return False
    
    def _load_existing_pids(self):
        """Load existing PID files on startup"""
        logger.info(f"Loading existing PID files from {self.pid_dir}")
        
        if not os.path.exists(self.pid_dir):
            logger.info("PID directory doesn't exist, nothing to load")
            return
        
        try:
            pid_files = [f for f in os.listdir(self.pid_dir) if f.endswith('.pid')]
            logger.info(f"Found {len(pid_files)} PID files")
            
            loaded = 0
            cleaned = 0
            
            for pid_file in pid_files:
                target_id = pid_file[:-4]  # Remove .pid extension
                pid = self._read_pid_file(target_id)
                
                if pid is None:
                    continue
                
                # Check if process is still alive
                if self._is_process_alive(pid):
                    # Process is alive, load into memory
                    try:
                        process = psutil.Process(pid)
                        cmdline = process.cmdline()
                        
                        # Extract mount path from cmdline if available
                        mount_path = None
                        if len(cmdline) > 1:
                            mount_path = cmdline[1]
                        
                        # Add to tracking
                        self.processes[target_id] = {
                            'pid': pid,
                            'process': None,  # Can't get Popen object for existing process
                            'target_id': target_id,
                            'mount_path': mount_path,
                            'start_time': datetime.fromtimestamp(process.create_time()),
                            'env_keys': [],  # Unknown for existing process
                            'status': 'running',
                            'loaded_from_disk': True
                        }
                        
                        self._all_pids.add(pid)
                        loaded += 1
                        
                        logger.info(f"✓ Loaded existing process: target={target_id}, PID={pid}")
                        
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        logger.warning(f"Process {pid} exists but can't access: {e}")
                        self._delete_pid_file(target_id)
                        cleaned += 1
                else:
                    # Process is dead, clean up PID file
                    logger.info(f"Cleaning up stale PID file: {pid_file} (PID {pid} is dead)")
                    self._delete_pid_file(target_id)
                    cleaned += 1
            
            logger.info(f"PID file loading complete: loaded={loaded}, cleaned={cleaned}")
            
        except Exception as e:
            logger.error(f"Error loading PID files: {e}", exc_info=True)
    
    def prepare_environment(self, backup_target: Dict[str, Any], 
                          credentials: Dict[str, Any]) -> Dict[str, str]:
        """
        Prepare environment variables for s3vaultfuse
        
        Args:
            backup_target: Backup target configuration
            credentials: S3 credentials from Barbican
            
        Returns:
            Dictionary of environment variables
        """
        # Base environment
        env = os.environ.copy()
        
        # Extract values from backup_target and credentials
        bucket = credentials.get('bucket', credentials.get('vault_s3_bucket', ''))
        region = credentials.get('region', credentials.get('vault_s3_region_name', 'us-west-2'))
        endpoint_url = credentials.get('endpoint_url', credentials.get('vault_s3_endpoint_url', ''))
        mount_path = backup_target.get('filesystem_export_mount_path', '')
        
        # S3VaultFuse specific environment variables
        env.update({
            # S3 Configuration
            'vault_s3_bucket': bucket,
            'vault_s3_region_name': region,
            'vault_s3_auth_version': credentials.get('auth_version', 'DEFAULT'),
            'vault_s3_signature_version': credentials.get('signature_version', 'default'),
            'vault_s3_ssl': str(credentials.get('ssl', 'true')).lower(),
            'vault_s3_ssl_verify': str(credentials.get('ssl_verify', 'true')).lower(),
            'vault_storage_nfs_export': credentials.get('nfs_export', bucket),
            'bucket_object_lock': str(credentials.get('object_lock', 'false')).lower(),
            'use_manifest_suffix': str(credentials.get('use_manifest_suffix', 'false')).lower(),
            'vault_s3_ssl_cert': credentials.get('ssl_cert', ''),
            'vault_s3_endpoint_url': endpoint_url,
            'vault_s3_max_pool_connections': str(credentials.get('max_pool_connections', '500')),
            
            # Directory Configuration
            'vault_data_directory_old': '/var/triliovault',
            'vault_data_directory': mount_path,
            
            # AWS Credentials
            'AWS_ACCESS_KEY_ID': credentials.get('aws_access_key_id', ''),
            'AWS_SECRET_ACCESS_KEY': credentials.get('aws_secret_access_key', ''),
            
            # Logging
            'log_config_append': credentials.get('log_config', '/etc/triliovault-object-store/object_store_logging.conf'),
            
            # Helper Command
            'helper_command': 'sudo /usr/bin/workloadmgr-rootwrap /etc/triliovault-wlm/rootwrap.conf privsep-helper',
        })
        
        # Remove empty values
        env = {k: v for k, v in env.items() if v}
        
        return env
    
    def spawn_s3vaultfuse(self, target_id: str, mount_path: str, 
                         env: Dict[str, str]) -> bool:
        """
        Spawn s3vaultfuse process with tracking (memory + disk)
        
        Args:
            target_id: Backup target ID
            mount_path: Mount path
            env: Environment variables
            
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                # Check if process already running (in memory)
                if target_id in self.processes:
                    proc_info = self.processes[target_id]
                    if self._is_process_alive(proc_info['pid']):
                        logger.info(f"s3vaultfuse already running for target {target_id}, PID: {proc_info['pid']}")
                        return True
                    else:
                        # Old process is dead, clean it up
                        logger.warning(f"Cleaning up dead process entry for target {target_id}")
                        self._cleanup_process_entry(target_id)
                
                # Check if PID file exists on disk
                existing_pid = self._read_pid_file(target_id)
                if existing_pid and self._is_process_alive(existing_pid):
                    logger.info(f"Found existing running process from PID file: target={target_id}, PID={existing_pid}")
                    
                    # Load into memory
                    try:
                        process = psutil.Process(existing_pid)
                        self.processes[target_id] = {
                            'pid': existing_pid,
                            'process': None,
                            'target_id': target_id,
                            'mount_path': mount_path,
                            'start_time': datetime.fromtimestamp(process.create_time()),
                            'env_keys': list(env.keys()),
                            'status': 'running',
                            'loaded_from_disk': True
                        }
                        self._all_pids.add(existing_pid)
                        return True
                    except Exception as e:
                        logger.warning(f"Failed to load existing process {existing_pid}: {e}")
                        self._delete_pid_file(target_id)
                
                # Ensure mount directory exists
                os.makedirs(mount_path, exist_ok=True)
                
                # Build command
                cmd = [
                    self.S3VAULTFUSE_BIN,
                    mount_path
                ]
                
                logger.info(f"Spawning s3vaultfuse for target {target_id}: {' '.join(cmd)}")
                logger.debug(f"Mount path: {mount_path}")
                logger.debug(f"Environment variables: {self._sanitize_env_for_log(env)}")
                
                # Spawn process
                process = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    preexec_fn=os.setsid  # Create new process group
                )
                
                # Wait a bit to ensure process starts
                time.sleep(2)
                
                # Check if process is still running
                if process.poll() is not None:
                    # Process died
                    stdout, stderr = process.communicate()
                    logger.error(f"s3vaultfuse failed to start: {stderr}")
                    return False
                
                pid = process.pid
                
                # Write PID file to disk
                if not self._write_pid_file(target_id, pid):
                    logger.warning(f"Failed to write PID file for target {target_id}")
                
                # Store comprehensive process information in memory
                self.processes[target_id] = {
                    'pid': pid,
                    'process': process,
                    'target_id': target_id,
                    'mount_path': mount_path,
                    'start_time': datetime.utcnow(),
                    'env_keys': list(env.keys()),
                    'status': 'running',
                    'loaded_from_disk': False
                }
                
                # Track PID globally
                self._all_pids.add(pid)
                
                logger.info(f"✓ s3vaultfuse spawned successfully for target {target_id}")
                logger.info(f"  PID: {pid}")
                logger.info(f"  Mount path: {mount_path}")
                logger.info(f"  PID file: {self._get_pid_file_path(target_id)}")
                logger.info(f"  Start time: {self.processes[target_id]['start_time']}")
                logger.info(f"  Total tracked processes: {len(self.processes)}")
                
                return True
                
            except Exception as e:
                logger.error(f"Failed to spawn s3vaultfuse: {e}", exc_info=True)
                # Cleanup PID file if spawn failed
                self._delete_pid_file(target_id)
                return False
    
    def kill_s3vaultfuse(self, target_id: str, force: bool = False) -> bool:
        """
        Kill s3vaultfuse process (removes from memory + disk)
        
        Args:
            target_id: Backup target ID
            force: If True, use SIGKILL immediately
            
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                # Get PID from memory or disk
                pid = None
                if target_id in self.processes:
                    pid = self.processes[target_id]['pid']
                else:
                    pid = self._read_pid_file(target_id)
                
                if pid is None:
                    logger.warning(f"No s3vaultfuse process found for target {target_id}")
                    # Still try to cleanup PID file
                    self._delete_pid_file(target_id)
                    return True
                
                # Check if already dead
                if not self._is_process_alive(pid):
                    logger.info(f"s3vaultfuse process already terminated for target {target_id}")
                    self._cleanup_process_entry(target_id)
                    return True
                
                logger.info(f"Killing s3vaultfuse process for target {target_id}")
                logger.info(f"  PID: {pid}")
                if target_id in self.processes:
                    logger.info(f"  Mount path: {self.processes[target_id]['mount_path']}")
                    logger.info(f"  Uptime: {datetime.utcnow() - self.processes[target_id]['start_time']}")
                
                try:
                    if force:
                        # Force kill immediately
                        logger.warning(f"Force killing s3vaultfuse process {pid}")
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                    else:
                        # Try graceful termination first
                        logger.info(f"Sending SIGTERM to process {pid}")
                        os.killpg(os.getpgid(pid), signal.SIGTERM)
                        
                        # Wait for process to terminate
                        if target_id in self.processes and self.processes[target_id]['process']:
                            process = self.processes[target_id]['process']
                            try:
                                process.wait(timeout=10)
                                logger.info(f"Process {pid} terminated gracefully")
                            except subprocess.TimeoutExpired:
                                # Force kill if doesn't terminate
                                logger.warning(f"Process {pid} did not terminate, force killing")
                                os.killpg(os.getpgid(pid), signal.SIGKILL)
                                process.wait(timeout=5)
                                logger.info(f"Process {pid} force killed")
                        else:
                            # No process object, wait manually
                            time.sleep(2)
                            if self._is_process_alive(pid):
                                logger.warning(f"Process {pid} still alive, force killing")
                                os.killpg(os.getpgid(pid), signal.SIGKILL)
                    
                    logger.info(f"✓ s3vaultfuse process killed for target {target_id}")
                    
                except ProcessLookupError:
                    logger.info(f"s3vaultfuse process already gone for target {target_id}")
                
                # Cleanup tracking (memory + disk)
                self._cleanup_process_entry(target_id)
                logger.info(f"  Remaining tracked processes: {len(self.processes)}")
                
                return True
                
            except Exception as e:
                logger.error(f"Failed to kill s3vaultfuse: {e}", exc_info=True)
                # Try to cleanup anyway
                self._cleanup_process_entry(target_id)
                return False
    
    def is_running(self, target_id: str) -> bool:
        """
        Check if s3vaultfuse is running for target (checks memory + disk)
        
        Args:
            target_id: Backup target ID
            
        Returns:
            True if running, False otherwise
        """
        with self._lock:
            # Check memory first
            if target_id in self.processes:
                pid = self.processes[target_id]['pid']
                if self._is_process_alive(pid):
                    return True
            
            # Check disk PID file
            pid = self._read_pid_file(target_id)
            if pid and self._is_process_alive(pid):
                # Process is running but not in memory, load it
                logger.info(f"Found running process from PID file: target={target_id}, PID={pid}")
                try:
                    process = psutil.Process(pid)
                    self.processes[target_id] = {
                        'pid': pid,
                        'process': None,
                        'target_id': target_id,
                        'mount_path': None,
                        'start_time': datetime.fromtimestamp(process.create_time()),
                        'env_keys': [],
                        'status': 'running',
                        'loaded_from_disk': True
                    }
                    self._all_pids.add(pid)
                except:
                    pass
                return True
            
            return False
    
    def get_process_info(self, target_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed process information
        
        Args:
            target_id: Backup target ID
            
        Returns:
            Process information dictionary or None
        """
        with self._lock:
            if target_id not in self.processes:
                return None
            
            proc_info = self.processes[target_id].copy()
            pid = proc_info['pid']
            
            # Add current status
            proc_info['alive'] = self._is_process_alive(pid)
            proc_info['pid_file'] = self._get_pid_file_path(target_id)
            proc_info['pid_file_exists'] = os.path.exists(proc_info['pid_file'])
            
            # Add process stats if available
            try:
                process = psutil.Process(pid)
                proc_info['cpu_percent'] = process.cpu_percent()
                proc_info['memory_mb'] = process.memory_info().rss / 1024 / 1024
                proc_info['num_threads'] = process.num_threads()
                proc_info['uptime_seconds'] = (datetime.utcnow() - proc_info['start_time']).total_seconds()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            
            # Remove process object (not serializable)
            proc_info.pop('process', None)
            
            return proc_info
    
    def list_all_processes(self) -> List[Dict[str, Any]]:
        """
        List all tracked s3vaultfuse processes
        
        Returns:
            List of process information dictionaries
        """
        with self._lock:
            processes = []
            for target_id in list(self.processes.keys()):
                info = self.get_process_info(target_id)
                if info:
                    processes.append(info)
            return processes
    
    def cleanup_dead_processes(self) -> int:
        """
        Cleanup entries for dead processes (memory + disk)
        
        Returns:
            Number of dead processes cleaned up
        """
        with self._lock:
            dead_targets = []
            
            for target_id, proc_info in self.processes.items():
                if not self._is_process_alive(proc_info['pid']):
                    dead_targets.append(target_id)
            
            for target_id in dead_targets:
                logger.info(f"Cleaning up dead process for target {target_id}")
                self._cleanup_process_entry(target_id)
            
            if dead_targets:
                logger.info(f"Cleaned up {len(dead_targets)} dead process entries")
            
            return len(dead_targets)
    
    def cleanup_all(self, force: bool = False):
        """
        Cleanup all s3vaultfuse processes (memory + disk)
        
        Args:
            force: If True, use SIGKILL immediately
        """
        logger.info("Cleaning up all s3vaultfuse processes")
        logger.info(f"Total processes to cleanup: {len(self.processes)}")
        
        # Get list of target IDs to avoid modification during iteration
        target_ids = list(self.processes.keys())
        
        for target_id in target_ids:
            try:
                self.kill_s3vaultfuse(target_id, force=force)
            except Exception as e:
                logger.error(f"Error cleaning up process for target {target_id}: {e}")
        
        logger.info("All s3vaultfuse processes cleaned up")
        logger.info(f"Remaining processes: {len(self.processes)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get overall statistics
        
        Returns:
            Statistics dictionary
        """
        with self._lock:
            total = len(self.processes)
            alive = sum(1 for t in self.processes if self._is_process_alive(self.processes[t]['pid']))
            dead = total - alive
            
            # Count PID files on disk
            pid_files_on_disk = 0
            if os.path.exists(self.pid_dir):
                pid_files_on_disk = len([f for f in os.listdir(self.pid_dir) if f.endswith('.pid')])
            
            stats = {
                'total_tracked': total,
                'alive': alive,
                'dead': dead,
                'all_pids_ever_spawned': len(self._all_pids),
                'pid_files_on_disk': pid_files_on_disk,
                'pid_directory': self.pid_dir,
                'processes': []
            }
            
            # Add per-process stats
            for target_id in self.processes:
                info = self.get_process_info(target_id)
                if info:
                    stats['processes'].append({
                        'target_id': target_id,
                        'pid': info['pid'],
                        'alive': info['alive'],
                        'uptime_seconds': info.get('uptime_seconds', 0),
                        'mount_path': info['mount_path'],
                        'pid_file': info['pid_file'],
                        'pid_file_exists': info['pid_file_exists']
                    })
            
            return stats
    
    def _is_process_alive(self, pid: int) -> bool:
        """
        Check if process is alive
        
        Args:
            pid: Process ID
            
        Returns:
            True if alive, False otherwise
        """
        try:
            process = psutil.Process(pid)
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
    
    def _cleanup_process_entry(self, target_id: str):
        """
        Cleanup process entry from tracking (memory + disk)
        
        Args:
            target_id: Backup target ID
        """
        # Remove from memory
        if target_id in self.processes:
            proc_info = self.processes[target_id]
            proc_info['status'] = 'terminated'
            del self.processes[target_id]
        
        # Remove PID file from disk
        self._delete_pid_file(target_id)
    
    def _sanitize_env_for_log(self, env: Dict[str, str]) -> Dict[str, str]:
        """
        Sanitize environment variables for logging (hide secrets)
        
        Args:
            env: Environment variables
            
        Returns:
            Sanitized environment dictionary
        """
        sanitized = {}
        sensitive_keys = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'aws_secret_access_key']
        
        for key, value in env.items():
            if any(sensitive in key for sensitive in sensitive_keys):
                sanitized[key] = '***REDACTED***'
            else:
                sanitized[key] = value
        
        return sanitized
    
    def __del__(self):
        """Cleanup on deletion"""
        try:
            self.cleanup_all(force=True)
        except:
            pass
