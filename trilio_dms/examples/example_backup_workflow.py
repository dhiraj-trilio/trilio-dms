"""
Complete Example: Using Trilio DMS Client
This example demonstrates how to integrate DMS into your backup workflow
"""

import os
import logging
import time
from datetime import datetime
from trilio_dms.client import DMSClient, MountContext
from trilio_dms.exceptions import DMSClientException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BackupWorkflow:
    """Example backup workflow using DMS"""
    
    def __init__(self):
        """Initialize backup workflow with DMS client"""
        self.dms_client = DMSClient(
            db_url=os.getenv('DMS_DB_URL'),
            rabbitmq_url=os.getenv('DMS_RABBITMQ_URL'),
            timeout=300
        )
        logger.info("Backup workflow initialized")
    
    def create_request(self, vm_id: str, backup_target_config: dict, 
                      job_info: dict, action: str = 'mount') -> dict:
        """
        Create DMS request from parameters
        
        Args:
            vm_id: Virtual machine ID
            backup_target_config: Backup target configuration
            job_info: Job information
            action: 'mount' or 'unmount'
            
        Returns:
            Complete DMS request dictionary
        """
        return {
            'context': {
                'user_id': job_info.get('user_id', 'unknown'),
                'tenant_id': job_info.get('tenant_id', 'unknown'),
                'project_id': job_info.get('project_id', 'unknown'),
                'request_id': job_info.get('request_id', 'unknown')
            },
            'keystone_token': self._get_keystone_token(),
            'job': {
                'jobid': job_info['job_id'],
                'progress': job_info.get('progress', 0),
                'status': job_info.get('status', 'running'),
                'completed_at': job_info.get('completed_at'),
                'action': job_info.get('action', 'backup'),
                'parent_jobid': job_info.get('parent_job_id'),
                'job_details': [
                    {
                        'id': f'vm-{vm_id}',
                        'data': {
                            'vm_id': vm_id,
                            'vm_name': job_info.get('vm_name', f'VM-{vm_id}'),
                            'backup_type': job_info.get('backup_type', 'full'),
                            'snapshot_id': job_info.get('snapshot_id')
                        }
                    }
                ]
            },
            'host': os.getenv('DMS_NODE_ID', os.uname().nodename),
            'action': action,
            'backup_target': backup_target_config
        }
    
    def perform_backup_with_context(self, vm_id: str, backup_target_config: dict, 
                                   job_info: dict):
        """
        Perform backup using context manager (recommended)
        
        Args:
            vm_id: Virtual machine ID to backup
            backup_target_config: Backup target configuration
            job_info: Job information
        """
        logger.info(f"Starting backup for VM: {vm_id}")
        
        request = self.create_request(vm_id, backup_target_config, job_info)
        
        try:
            # Use context manager for automatic mount/unmount
            with MountContext(self.dms_client, request) as mount:
                logger.info(f"Backup target mounted at: {mount.get_mount_path()}")
                
                # Perform actual backup operations
                self._execute_backup(vm_id, mount.get_mount_path(), job_info)
                
                logger.info(f"Backup completed successfully for VM: {vm_id}")
            
            # Unmount happens automatically on context exit
            logger.info("Backup target unmounted successfully")
            
        except DMSClientException as e:
            logger.error(f"DMS error during backup: {e}")
            raise
        except Exception as e:
            logger.error(f"Backup failed: {e}", exc_info=True)
            raise
    
    def perform_backup_manual(self, vm_id: str, backup_target_config: dict, 
                            job_info: dict):
        """
        Perform backup with manual mount/unmount control
        
        Args:
            vm_id: Virtual machine ID to backup
            backup_target_config: Backup target configuration
            job_info: Job information
        """
        logger.info(f"Starting backup for VM: {vm_id}")
        
        request = self.create_request(vm_id, backup_target_config, job_info)
        
        try:
            # Mount
            mount_response = self.dms_client.mount(request)
            
            if mount_response['status'] != 'success':
                raise Exception(f"Mount failed: {mount_response.get('error_msg')}")
            
            logger.info(f"Mount successful: {mount_response.get('success_msg')}")
            
            # Perform backup
            mount_path = f"/var/lib/trilio/mounts/{backup_target_config['id']}"
            self._execute_backup(vm_id, mount_path, job_info)
            
            logger.info(f"Backup completed successfully for VM: {vm_id}")
            
        except Exception as e:
            logger.error(f"Backup failed: {e}", exc_info=True)
            raise
        
        finally:
            # Always unmount, even if backup fails
            try:
                request['action'] = 'unmount'
                unmount_response = self.dms_client.unmount(request)
                
                if unmount_response['status'] == 'success':
                    logger.info("Unmount successful")
                else:
                    logger.error(f"Unmount failed: {unmount_response.get('error_msg')}")
            except Exception as e:
                logger.error(f"Error during unmount: {e}")
    
    def perform_restore(self, vm_id: str, backup_target_config: dict, 
                       job_info: dict, restore_point: str):
        """
        Perform restore operation
        
        Args:
            vm_id: Virtual machine ID to restore
            backup_target_config: Backup target configuration
            job_info: Job information
            restore_point: Restore point identifier
        """
        logger.info(f"Starting restore for VM: {vm_id} from point: {restore_point}")
        
        request = self.create_request(vm_id, backup_target_config, job_info)
        
        try:
            with MountContext(self.dms_client, request) as mount:
                logger.info(f"Backup target mounted at: {mount.get_mount_path()}")
                
                # Perform restore
                self._execute_restore(vm_id, mount.get_mount_path(), restore_point)
                
                logger.info(f"Restore completed successfully for VM: {vm_id}")
            
        except Exception as e:
            logger.error(f"Restore failed: {e}", exc_info=True)
            raise
    
    def _execute_backup(self, vm_id: str, mount_path: str, job_info: dict):
        """
        Execute actual backup logic
        
        Args:
            vm_id: VM ID
            mount_path: Mount path
            job_info: Job information
        """
        import json
        import shutil
        
        logger.info(f"Executing backup for VM {vm_id} to {mount_path}")
        
        # Create backup directory
        backup_id = f"backup-{vm_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        backup_dir = os.path.join(mount_path, backup_id)
        os.makedirs(backup_dir, exist_ok=True)
        
        # Simulate backup process
        # In real implementation, you would:
        # 1. Snapshot VM disks
        # 2. Export VM configuration
        # 3. Copy data to backup target
        # 4. Verify backup integrity
        
        logger.info("Snapshotting VM disks...")
        time.sleep(1)  # Simulate disk snapshot
        
        logger.info("Exporting VM configuration...")
        time.sleep(0.5)  # Simulate config export
        
        logger.info("Copying data to backup target...")
        time.sleep(2)  # Simulate data copy
        
        # Write backup metadata
        metadata = {
            'vm_id': vm_id,
            'vm_name': job_info.get('vm_name'),
            'backup_id': backup_id,
            'backup_type': job_info.get('backup_type', 'full'),
            'backup_time': datetime.now().isoformat(),
            'job_id': job_info['job_id'],
            'status': 'completed',
            'size_bytes': 10737418240,  # Example: 10GB
            'snapshot_id': job_info.get('snapshot_id')
        }
        
        metadata_file = os.path.join(backup_dir, 'metadata.json')
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Backup metadata written to {metadata_file}")
        logger.info(f"Backup completed: {backup_id}")
    
    def _execute_restore(self, vm_id: str, mount_path: str, restore_point: str):
        """
        Execute actual restore logic
        
        Args:
            vm_id: VM ID
            mount_path: Mount path
            restore_point: Restore point ID
        """
        import json
        
        logger.info(f"Executing restore for VM {vm_id} from {mount_path}")
        
        # Find backup
        backup_dir = os.path.join(mount_path, restore_point)
        
        if not os.path.exists(backup_dir):
            raise Exception(f"Backup not found at {backup_dir}")
        
        # Read metadata
        metadata_file = os.path.join(backup_dir, 'metadata.json')
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        logger.info(f"Found backup: {metadata['backup_id']}")
        logger.info(f"Backup time: {metadata['backup_time']}")
        
        # Simulate restore process
        logger.info("Restoring VM disks...")
        time.sleep(2)  # Simulate disk restore
        
        logger.info("Restoring VM configuration...")
        time.sleep(0.5)  # Simulate config restore
        
        logger.info("Verifying restored VM...")
        time.sleep(1)  # Simulate verification
        
        logger.info(f"VM {vm_id} restored successfully from {restore_point}")
    
    def check_mount_status(self, job_id: str, backup_target_id: str):
        """Check mount status from ledger"""
        logger.info(f"Checking mount status for job {job_id}, target {backup_target_id}")
        
        status = self.dms_client.get_mount_status(job_id, backup_target_id)
        
        if status:
            logger.info(f"Mount Status:")
            logger.info(f"  ID: {status.id}")
            logger.info(f"  Action: {status.action}")
            logger.info(f"  Status: {status.status}")
            logger.info(f"  Mount Path: {status.mount_path}")
            logger.info(f"  Host: {status.host}")
            logger.info(f"  Created: {status.created_at}")
            logger.info(f"  Completed: {status.completed_at}")
            
            if status.error_msg:
                logger.error(f"  Error: {status.error_msg}")
            if status.success_msg:
                logger.info(f"  Message: {status.success_msg}")
            
            return status
        else:
            logger.info("No mount status found")
            return None
    
    def list_active_mounts(self, host: str = None):
        """List all active mounts"""
        logger.info(f"Listing active mounts{' for host: ' + host if host else ''}")
        
        active_mounts = self.dms_client.get_active_mounts(host)
        
        logger.info(f"Found {len(active_mounts)} active mounts:")
        for mount in active_mounts:
            logger.info(f"  Target: {mount.backup_target_id}")
            logger.info(f"    Job: {mount.job_id}")
            logger.info(f"    Host: {mount.host}")
            logger.info(f"    Path: {mount.mount_path}")
            logger.info(f"    Mounted: {mount.created_at}")
            logger.info("  ---")
        
        return active_mounts
    
    def cleanup_stale_mounts(self, hours: int = 24):
        """Cleanup stale mount entries"""
        logger.info(f"Cleaning up stale mount entries older than {hours} hours...")
        count = self.dms_client.cleanup_stale_entries(hours)
        logger.info(f"Cleaned up {count} stale entries")
        return count
    
    def get_backup_history(self, backup_target_id: str, limit: int = 10):
        """Get backup history for a target"""
        logger.info(f"Getting backup history for target: {backup_target_id}")
        
        history = self.dms_client.get_ledger_history(backup_target_id, limit)
        
        logger.info(f"Found {len(history)} entries:")
        for entry in history:
            logger.info(f"  {entry.created_at}: {entry.action} - {entry.status}")
            if entry.job_id:
                logger.info(f"    Job: {entry.job_id}")
        
        return history
    
    def _get_keystone_token(self) -> str:
        """Get Keystone authentication token"""
        # In real implementation, authenticate with Keystone
        # For example purposes, return from environment
        token = os.getenv('KEYSTONE_TOKEN')
        if not token:
            logger.warning("No KEYSTONE_TOKEN found, using dummy token")
            token = 'dummy-token-for-testing'
        return token
    
    def close(self):
        """Cleanup resources"""
        self.dms_client.close()
        logger.info("Workflow closed")


def main():
    """Example usage"""
    # Initialize workflow
    workflow = BackupWorkflow()
    
    # Example S3 backup target
    s3_backup_target = {
        'id': 'target-s3-prod-001',
        'deleted': False,
        'type': 's3',
        'filesystem_export': None,
        'filesystem_export_mount_path': None,
        'status': 'available',
        'secret_ref': 'http://barbican:9311/v1/secrets/s3-credentials-uuid',
        'nfs_mount_opts': None
    }
    
    # Example NFS backup target
    nfs_backup_target = {
        'id': 'target-nfs-prod-001',
        'deleted': False,
        'type': 'nfs',
        'filesystem_export': '192.168.1.100:/backups',
        'filesystem_export_mount_path': None,
        'status': 'available',
        'secret_ref': None,
        'nfs_mount_opts': 'rw,sync,hard,intr,nfsvers=4'
    }
    
    # Example job information
    backup_job = {
        'job_id': f'backup-job-{datetime.now().strftime("%Y%m%d%H%M%S")}',
        'user_id': 'user-001',
        'tenant_id': 'tenant-001',
        'project_id': 'project-001',
        'vm_name': 'web-server-prod-01',
        'backup_type': 'full',
        'status': 'running',
        'progress': 0
    }
    
    try:
        print("\n" + "="*60)
        print("Example 1: Backup using context manager (recommended)")
        print("="*60)
        workflow.perform_backup_with_context(
            vm_id='vm-001',
            backup_target_config=nfs_backup_target,
            job_info=backup_job
        )
        
        print("\n" + "="*60)
        print("Example 2: Check mount status")
        print("="*60)
        workflow.check_mount_status(
            backup_job['job_id'],
            nfs_backup_target['id']
        )
        
        print("\n" + "="*60)
        print("Example 3: List active mounts")
        print("="*60)
        workflow.list_active_mounts()
        
        print("\n" + "="*60)
        print("Example 4: Get backup history")
        print("="*60)
        workflow.get_backup_history(nfs_backup_target['id'])
        
        print("\n" + "="*60)
        print("Example 5: Cleanup stale entries")
        print("="*60)
        workflow.cleanup_stale_mounts(hours=24)
        
        print("\n" + "="*60)
        print("All examples completed successfully!")
        print("="*60)
        
    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)
    
    finally:
        workflow.close()


if __name__ == '__main__':
    main()
