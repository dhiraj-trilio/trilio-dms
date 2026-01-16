"""
Example: Using Trilio DMS with s3vaultfuse
This example demonstrates the correct request format and usage
"""

import os
import logging
from datetime import datetime
from trilio_dms.client import DMSClient, MountContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_s3_backup():
    """Example S3 backup using s3vaultfuse"""
    
    # Initialize DMS Client
    client = DMSClient(
        db_url=os.getenv('DMS_DB_URL'),
        rabbitmq_url=os.getenv('DMS_RABBITMQ_URL')
    )
    
    # Prepare S3 backup target request
    request = {
        'context': {
            'user_id': 'user-12345',
            'tenant_id': 'tenant-67890',
            'project_id': 'project-abc',
            'request_id': f'req-{datetime.now().timestamp()}'
        },
        'keystone_token': os.getenv('KEYSTONE_TOKEN', 'your-token-here'),
        'job': {
            'jobid': 12345,  # Integer job ID
            'progress': 0,
            'status': 'running',
            'completed_at': None,
            'action': 'backup',
            'parent_jobid': None,
            'job_details': [
                {
                    'id': 'vm-detail-1',
                    'data': {
                        'vm_id': 'vm-001',
                        'vm_name': 'production-web-01',
                        'backup_type': 'full'
                    }
                }
            ]
        },
        'host': os.getenv('DMS_NODE_ID', 'compute-01'),
        'action': 'mount',
        'backup_target': {
            'id': 'target-s3-prod-001',
            'deleted': False,
            'type': 's3',
            'filesystem_export': None,
            'filesystem_export_mount_path': '/var/lib/trilio/triliovault-mounts/dHJpbGlvLXFh',
            'status': 'available',
            'secret_ref': 'http://barbican:9311/v1/secrets/s3-credentials-uuid',
            'nfs_mount_opts': None
        }
    }
    
    try:
        logger.info("="*60)
        logger.info("S3 Backup Example using s3vaultfuse")
        logger.info("="*60)
        
        # Method 1: Using context manager (recommended)
        with MountContext(client, request) as mount:
            logger.info(f"S3 mounted at: {mount.get_mount_path()}")
            
            # Perform backup operations
            # The s3vaultfuse process is running in the background
            logger.info("Performing backup operations...")
            # ... your backup logic here ...
            
            logger.info("Backup completed")
        
        # Mount is automatically unmounted when exiting context
        logger.info("S3 unmounted successfully")
        
        # Method 2: Manual mount/unmount
        logger.info("\n" + "="*60)
        logger.info("Manual Mount/Unmount Example")
        logger.info("="*60)
        
        # Update job ID for second example
        request['job']['jobid'] = 12346
        
        # Mount
        response = client.mount(request)
        logger.info(f"Mount response: {response}")
        
        if response['status'] == 'success':
            # Check mount status
            status = client.get_mount_status(12346, 'target-s3-prod-001')
            if status:
                logger.info(f"Mount status: mounted={status.mounted}, host={status.host}")
            
            # Do work here
            logger.info("Performing backup operations...")
            
            # Unmount
            request['action'] = 'unmount'
            response = client.unmount(request)
            logger.info(f"Unmount response: {response}")
        
        # List all active mounts
        logger.info("\n" + "="*60)
        logger.info("Active Mounts")
        logger.info("="*60)
        
        active_mounts = client.get_active_mounts(host=os.getenv('DMS_NODE_ID', 'compute-01'))
        for mount in active_mounts:
            logger.info(f"  Target: {mount.backup_target_id}, Job: {mount.jobid}, Mounted: {mount.mounted}")
        
    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)
    
    finally:
        client.close()


def example_nfs_backup():
    """Example NFS backup"""
    
    client = DMSClient(
        db_url=os.getenv('DMS_DB_URL'),
        rabbitmq_url=os.getenv('DMS_RABBITMQ_URL')
    )
    
    request = {
        'context': {
            'user_id': 'user-12345',
            'tenant_id': 'tenant-67890'
        },
        'keystone_token': os.getenv('KEYSTONE_TOKEN', 'your-token-here'),
        'job': {
            'jobid': 12347,
            'progress': 0,
            'status': 'running',
            'completed_at': None,
            'action': 'backup',
            'parent_jobid': None,
            'job_details': []
        },
        'host': os.getenv('DMS_NODE_ID', 'compute-01'),
        'action': 'mount',
        'backup_target': {
            'id': 'target-nfs-prod-001',
            'deleted': False,
            'type': 'nfs',
            'filesystem_export': '192.168.1.100:/backups',
            'filesystem_export_mount_path': '/var/lib/trilio/triliovault-mounts/nfs-backup',
            'status': 'available',
            'secret_ref': None,
            'nfs_mount_opts': 'rw,sync,hard,intr,nfsvers=4'
        }
    }
    
    try:
        logger.info("\n" + "="*60)
        logger.info("NFS Backup Example")
        logger.info("="*60)
        
        with MountContext(client, request) as mount:
            logger.info(f"NFS mounted at: {mount.get_mount_path()}")
            logger.info("Performing backup operations...")
            logger.info("Backup completed")
        
        logger.info("NFS unmounted successfully")
        
    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)
    
    finally:
        client.close()


def example_s3_credentials():
    """
    Example credentials structure expected in Barbican secret
    """
    credentials_example = {
        # Required S3 credentials
        'aws_access_key_id': 'AKIAIOSFODNN7EXAMPLE',
        'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        'bucket': 'trilio-qa',
        
        # Optional S3 configuration
        'region': 'us-west-2',
        'endpoint_url': '',  # Empty for AWS, or custom endpoint
        'auth_version': 'DEFAULT',
        'signature_version': 'default',
        'ssl': 'true',
        'ssl_verify': 'true',
        'ssl_cert': '',
        'max_pool_connections': '500',
        
        # Trilio specific
        'nfs_export': 'trilio-qa',
        'object_lock': 'false',
        'use_manifest_suffix': 'false',
        
        # Logging
        'log_config': '/etc/triliovault-object-store/object_store_logging.conf'
    }
    
    logger.info("\n" + "="*60)
    logger.info("Example Barbican Secret Structure")
    logger.info("="*60)
    logger.info("Store this JSON in Barbican:")
    import json
    logger.info(json.dumps(credentials_example, indent=2))


if __name__ == '__main__':
    # Run examples
    logger.info("\n" + "="*80)
    logger.info("Trilio DMS Examples with s3vaultfuse")
    logger.info("="*80)
    
    # Show credentials structure
    example_s3_credentials()
    
    # S3 backup example
    example_s3_backup()
    
    # NFS backup example
    # example_nfs_backup()
    
    logger.info("\n" + "="*80)
    logger.info("Examples completed!")
    logger.info("="*80)
