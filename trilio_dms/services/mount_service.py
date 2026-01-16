"""Mount service - Updated with s3vaultfuse integration"""

import json
from datetime import datetime
from typing import Dict, Optional
from sqlalchemy import and_, func

from trilio_dms.config import DMSConfig
from trilio_dms.models import BackupTarget, BackupTargetMountLedger, Job, session_scope
from trilio_dms.drivers import NFSDriver, S3Driver
from trilio_dms.utils.logger import get_logger
from trilio_dms.utils.exceptions import (
    MountException, UnmountException, TargetNotFoundException, AuthenticationException
)
from trilio_dms.services.secret_manager import SecretManager


LOG = get_logger(__name__)


class MountService:
    """Core mount/unmount service with NFS and S3 support"""

    def __init__(self, config: DMSConfig):
        self.config = config
        self.nfs_driver = NFSDriver()
        
        # Initialize S3 driver with s3vaultfuse configuration
        s3_config = {
            's3vaultfuse_path': config.s3_vaultfuse_path if hasattr(config, 's3_vaultfuse_path') else '/usr/bin/s3vaultfuse.py',
            'default_log_config': config.s3_log_config if hasattr(config, 's3_log_config') else '/etc/triliovault-object-store/object_store_logging.conf',
            'default_data_directory': config.s3_data_directory if hasattr(config, 's3_data_directory') else '/var/lib/trilio/triliovault-mounts',
            'pidfile_dir': config.s3_pidfile_dir if hasattr(config, 's3_pidfile_dir') else '/run/dms/s3'
        }
        self.s3_driver = S3Driver(s3_config)
        
        # Initialize secret manager (only needs SSL config)
        secret_config = {
            'verify_ssl': config.verify_ssl if hasattr(config, 'verify_ssl') else False
        }
        self.secret_manager = SecretManager(secret_config)

    def mount(self, job_id: int, target_id: str, keystone_token: str) -> Dict:
        """Handle mount request"""
        with session_scope() as session:
            try:
                # Load target
                target = session.query(BackupTarget).filter_by(
                    id=target_id, deleted=False
                ).first()

                if not target:
                    raise TargetNotFoundException(f"Target {target_id} not found")

                # Check target status
                if target.status != 'available':
                    LOG.warning(f"Target {target_id} status is {target.status}")

                # Check if ledger entry already exists
                existing_ledger = session.query(BackupTargetMountLedger).filter_by(
                    backup_target_id=target_id,
                    jobid=job_id,
                    host=self.config.node_id,
                    deleted=False
                ).first()

                if existing_ledger:
                    LOG.info(f"Ledger entry already exists for job {job_id}")
                    return {
                        'success': True,
                        'message': f'Mount already exists for job {job_id}',
                        'mount_path': target.filesystem_export_mount_path
                    }

                # Create new ledger entry
                ledger = BackupTargetMountLedger(
                    backup_target_id=target_id,
                    jobid=job_id,
                    host=self.config.node_id,
                    mounted=False
                )
                session.add(ledger)
                session.commit()

                LOG.info(f"Created ledger entry: id={ledger.id}, job={job_id}, target={target_id}")

                # Compute active count
                active_count = self._compute_active_count(session, target_id)
                LOG.info(f"Active count for {target_id}: {active_count}")

                # Mount if first active job
                if active_count == 1 and not self._is_mounted(target):
                    LOG.info(f"First active job, mounting {target_id}")
                    self._perform_mount(target, keystone_token)

                    # Update all ledger entries
                    session.query(BackupTargetMountLedger).filter_by(
                        backup_target_id=target_id,
                        host=self.config.node_id,
                        deleted=False
                    ).update({'mounted': True})
                    session.commit()
                elif active_count > 1:
                    ledger.mounted = True
                    session.commit()
                    LOG.info(f"Reusing existing mount for {target_id}")

                return {
                    'success': True,
                    'message': f'Mount ready for job {job_id}',
                    'mount_path': target.filesystem_export_mount_path
                }

            except AuthenticationException as e:
                LOG.error(f"Authentication failed for target {target_id}: {e}")
                session.rollback()
                return {
                    'success': False,
                    'message': f'Authentication failed: {str(e)}'
                }
            except Exception as e:
                LOG.error(f"Mount failed: {e}", exc_info=True)
                session.rollback()
                return {
                    'success': False,
                    'message': str(e)
                }

    def unmount(self, job_id: int, target_id: str) -> Dict:
        """Handle unmount request"""
        with session_scope() as session:
            try:
                # Mark ledger entry as deleted
                ledger = session.query(BackupTargetMountLedger).filter_by(
                    backup_target_id=target_id,
                    jobid=job_id,
                    host=self.config.node_id,
                    deleted=False
                ).first()

                if ledger:
                    ledger.deleted = True
                    ledger.deleted_at = datetime.utcnow()
                    session.commit()
                    LOG.info(f"Marked ledger entry as deleted: job={job_id}")

                # Compute active count
                active_count = self._compute_active_count(session, target_id)
                LOG.info(f"Active count after unmount: {active_count}")

                # Unmount if no active jobs
                if active_count == 0:
                    target = session.query(BackupTarget).filter_by(id=target_id).first()
                    if target and self._is_mounted(target):
                        LOG.info(f"No active jobs, unmounting {target_id}")
                        self._perform_unmount(target)

                        # Update mounted flag
                        session.query(BackupTargetMountLedger).filter_by(
                            backup_target_id=target_id,
                            host=self.config.node_id
                        ).update({'mounted': False})
                        session.commit()

                return {
                    'success': True,
                    'message': f'Unmount processed for job {job_id}'
                }

            except Exception as e:
                LOG.error(f"Unmount failed: {e}", exc_info=True)
                session.rollback()
                return {
                    'success': False,
                    'message': str(e)
                }

    def _compute_active_count(self, session, target_id: str) -> int:
        """Compute active job count"""
        ledger_entries = session.query(BackupTargetMountLedger).filter_by(
            backup_target_id=target_id,
            host=self.config.node_id,
            deleted=False
        ).all()

        if not ledger_entries:
            return 0

        job_ids = [entry.jobid for entry in ledger_entries]

        return session.query(Job).filter(
            Job.jobid.in_(job_ids),
            Job.status.in_(['STARTING', 'RUNNING']),
            Job.deleted == False
        ).count()

    def _is_mounted(self, target: BackupTarget) -> bool:
        """Check if target is mounted"""
        if target.type == 'nfs':
            return self.nfs_driver.is_mounted(target.filesystem_export_mount_path)
        elif target.type == 's3':
            return self.s3_driver.is_mounted(target.filesystem_export_mount_path)
        return False

    def _perform_mount(self, target: BackupTarget, keystone_token: str):
        """Perform actual mount operation"""
        if target.type == 'nfs':
            # Use nfs_mount_opts column (with fallback to 'defaults')
            mount_options = target.get_nfs_mount_options()

            LOG.info(f"Mounting NFS {target.filesystem_export} with options: {mount_options}")

            success = self.nfs_driver.mount(
                target_id=target.id,
                mount_path=target.filesystem_export_mount_path,
                share=target.filesystem_export,
                options=mount_options  # Use from nfs_mount_opts column
            )
            
        elif target.type == 's3':
            # Validate required parameters
            if not target.secret_ref:
                raise MountException(f"Target {target.id} has no secret_ref configured")
            
            if not keystone_token:
                raise MountException("keystone_token is required for S3 mount")
            
            LOG.info(f"Retrieving S3 credentials from Barbican for target {target.id}")
            LOG.debug(f"Secret ref: {target.secret_ref}")
            
            # Retrieve credentials from Barbican
            # All s3vaultfuse parameters will be in the secret payload
            try:
                credentials = self.secret_manager.retrieve_credentials(
                    target.secret_ref,
                    keystone_token
                )
                
                LOG.info("Successfully retrieved credentials from Barbican")
                LOG.debug(f"Credential keys: {list(credentials.keys())}")
                
            except AuthenticationException as e:
                LOG.error(f"Failed to retrieve credentials: {e}")
                raise MountException(f"Failed to retrieve S3 credentials: {e}")
            
            # Mount using s3vaultfuse with credentials as environment variables
            LOG.info(f"Mounting S3 target {target.id} at {target.filesystem_export_mount_path}")
            
            success = self.s3_driver.mount(
                target_id=target.id,
                mount_path=target.filesystem_export_mount_path,
                credentials=credentials
            )
            
        else:
            raise MountException(f"Unknown target type: {target.type}")

        if not success:
            raise MountException(f"Failed to mount {target.id}")

    def _perform_unmount(self, target: BackupTarget):
        """Perform actual unmount operation"""
        if target.type == 'nfs':
            success = self.nfs_driver.unmount(
                target.id,
                target.filesystem_export_mount_path
            )
        elif target.type == 's3':
            success = self.s3_driver.unmount(
                target.id,
                target.filesystem_export_mount_path
            )
        else:
            raise UnmountException(f"Unknown target type: {target.type}")

        if not success:
            raise UnmountException(f"Failed to unmount {target.id}")
