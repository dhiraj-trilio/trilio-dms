"""
Utility functions for Trilio DMS
"""

import json
import logging
import os
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def validate_request_structure(request: Dict[str, Any]) -> bool:
    """
    Validate request structure
    
    Args:
        request: Request dictionary
        
    Returns:
        True if valid
        
    Raises:
        ValueError if invalid
    """
    required_fields = ['context', 'keystone_token', 'job', 'host', 'action', 'backup_target']
    
    for field in required_fields:
        if field not in request:
            raise ValueError(f"Missing required field: {field}")
    
    # Validate job structure
    job_fields = ['jobid', 'progress', 'status', 'action']
    for field in job_fields:
        if field not in request['job']:
            raise ValueError(f"Missing required job field: {field}")
    
    # Validate backup_target structure
    target_fields = ['id', 'type', 'status']
    for field in target_fields:
        if field not in request['backup_target']:
            raise ValueError(f"Missing required backup_target field: {field}")
    
    # Validate action
    if request['action'] not in ['mount', 'unmount']:
        raise ValueError(f"Invalid action: {request['action']}. Must be 'mount' or 'unmount'")
    
    # Validate backup target type
    if request['backup_target']['type'] not in ['s3', 'nfs']:
        raise ValueError(f"Invalid backup target type: {request['backup_target']['type']}")
    
    return True


def create_response(status: str, error_msg: Optional[str] = None, 
                   success_msg: Optional[str] = None) -> Dict[str, Any]:
    """
    Create standardized response
    
    Args:
        status: 'success' or 'error'
        error_msg: Error message if failed
        success_msg: Success message if succeeded
        
    Returns:
        Response dictionary
    """
    return {
        'status': status,
        'error_msg': error_msg,
        'success_msg': success_msg
    }


def is_mounted(mount_path: str) -> bool:
    """
    Check if a path is mounted
    
    Args:
        mount_path: Path to check
        
    Returns:
        True if mounted, False otherwise
    """
    if not os.path.exists(mount_path):
        return False
    
    result = subprocess.run(
        ['mountpoint', '-q', mount_path],
        capture_output=True
    )
    return result.returncode == 0


def get_mount_path(mount_base: str, target_id: str) -> str:
    """
    Get mount path for a backup target
    
    Args:
        mount_base: Base mount directory
        target_id: Backup target ID
        
    Returns:
        Full mount path
    """
    return os.path.join(mount_base, target_id)


def safe_json_loads(json_str: Optional[str], default: Any = None) -> Any:
    """
    Safely load JSON string
    
    Args:
        json_str: JSON string to load
        default: Default value if loading fails
        
    Returns:
        Parsed JSON or default value
    """
    if not json_str:
        return default
    
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse JSON: {e}")
        return default


def safe_json_dumps(obj: Any, default: str = '{}') -> str:
    """
    Safely dump object to JSON string
    
    Args:
        obj: Object to dump
        default: Default value if dumping fails
        
    Returns:
        JSON string or default value
    """
    if obj is None:
        return default
    
    try:
        return json.dumps(obj)
    except (TypeError, ValueError) as e:
        logger.warning(f"Failed to dump JSON: {e}")
        return default


def ensure_directory(path: str, mode: int = 0o755) -> bool:
    """
    Ensure directory exists
    
    Args:
        path: Directory path
        mode: Directory permissions
        
    Returns:
        True if created or exists
    """
    try:
        os.makedirs(path, mode=mode, exist_ok=True)
        return True
    except OSError as e:
        logger.error(f"Failed to create directory {path}: {e}")
        return False


def run_command(cmd: list, timeout: int = 30) -> tuple:
    """
    Run shell command
    
    Args:
        cmd: Command as list of strings
        timeout: Command timeout in seconds
        
    Returns:
        Tuple of (returncode, stdout, stderr)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, '', f'Command timeout after {timeout} seconds'
    except Exception as e:
        return -1, '', str(e)


def sanitize_mount_options(options: Optional[str]) -> str:
    """
    Sanitize mount options
    
    Args:
        options: Mount options string
        
    Returns:
        Sanitized options or default
    """
    if not options:
        return 'defaults'
    
    # Remove potentially dangerous options
    dangerous = ['exec', 'suid', 'dev']
    opts = options.split(',')
    safe_opts = [opt for opt in opts if opt.strip() not in dangerous]
    
    return ','.join(safe_opts) if safe_opts else 'defaults'


def format_bytes(size: int) -> str:
    """
    Format bytes to human-readable string
    
    Args:
        size: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"
