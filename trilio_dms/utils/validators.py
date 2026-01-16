"""Validation utilities - Added RabbitMQ URL validation"""

import re
from typing import Optional
from urllib.parse import urlparse


def validate_target_id(target_id: str) -> bool:
    """Validate target ID format"""
    uuid_pattern = r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
    return bool(re.match(uuid_pattern, target_id))


def validate_mount_path(path: str) -> bool:
    """Validate mount path"""
    return path.startswith('/') and not '..' in path


def validate_nfs_share(share: str) -> bool:
    """Validate NFS share format (server:/path)"""
    pattern = r'^[^:]+:.+$'
    return bool(re.match(pattern, share))


def validate_s3_bucket(bucket: str) -> bool:
    """Validate S3 bucket name"""
    pattern = r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$'
    return bool(re.match(pattern, bucket)) and 3 <= len(bucket) <= 63


def validate_endpoint_url(url: str) -> bool:
    """Validate endpoint URL"""
    return url.startswith('http://') or url.startswith('https://')


def validate_and_fix_rabbitmq_url(url: str) -> str:
    """
    Validate and fix RabbitMQ URL.
    
    Converts common incorrect formats:
    - rabbit:// → amqp://
    - rabbitmq:// → amqp://
    - Adds default port if missing
    
    Args:
        url: RabbitMQ URL
        
    Returns:
        Corrected URL
        
    Raises:
        ValueError: If URL is invalid after fixes
    """
    if not url:
        raise ValueError("RabbitMQ URL cannot be empty")
    
    # Auto-fix common mistakes
    original_url = url
    
    # Fix scheme
    if url.startswith('rabbit://'):
        url = url.replace('rabbit://', 'amqp://', 1)
    elif url.startswith('rabbitmq://'):
        url = url.replace('rabbitmq://', 'amqp://', 1)
    elif url.startswith('rabbits://'):
        url = url.replace('rabbits://', 'amqps://', 1)
    
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid RabbitMQ URL format: {e}")
    
    # Validate scheme
    if parsed.scheme not in ['amqp', 'amqps']:
        raise ValueError(
            f"Invalid RabbitMQ URL scheme: '{parsed.scheme}'. "
            f"Must be 'amqp://' or 'amqps://'. "
            f"Original URL: {original_url}"
        )
    
    # Add default port if missing
    if not parsed.port:
        if parsed.scheme == 'amqp':
            default_port = 5672
        else:  # amqps
            default_port = 5671
        
        # Reconstruct URL with port
        netloc = parsed.netloc
        if '@' in netloc:
            # Has credentials
            auth, host = netloc.rsplit('@', 1)
            netloc = f"{auth}@{host}:{default_port}"
        else:
            netloc = f"{netloc}:{default_port}"
        
        url = f"{parsed.scheme}://{netloc}{parsed.path}"
        if parsed.query:
            url += f"?{parsed.query}"
    
    return url


def get_rabbitmq_url_from_oslo(oslo_url: str) -> str:
    """
    Convert Oslo messaging URL to RabbitMQ URL.
    
    Oslo format: rabbit://user:pass@host:port/vhost
    Pika format: amqp://user:pass@host:port/vhost
    
    Args:
        oslo_url: Oslo messaging transport URL
        
    Returns:
        Pika-compatible RabbitMQ URL
    """
    return validate_and_fix_rabbitmq_url(oslo_url)
