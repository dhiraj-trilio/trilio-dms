from datetime import datetime
from typing import List

from trilio_dms.config import DMSConfig
from trilio_dms.models import (
    BackupTarget, BackupTargetMountLedger, Job, session_scope
)
from trilio_dms.drivers import NFSDriver, S3Driver
from trilio_dms.utils.logger import get_logger

LOG = get_logger(__name__)


class ReconciliationService:
    """Service for reconciling mount state"""

    def __init__(self, config: DMSConfig, mount_service):
        self.config = config
        self.mount_service = mount_service
        self.nfs_driver = NFSDriver()
        
        # Initialize S3 driver with s3vaultfuse configuration
        # Use same config as mount_service
        s3_config = {
            's3vaultfuse_path': config.s3_vaultfuse_path if hasattr(config, 's3_vaultfuse_path') else '/usr/bin/s3vaultfuse.py',
            'default_log_config': config.s3_log_config if hasattr(config, 's3_log_config') else '/etc/triliovault-object-store/object_store_logging.conf',
            'default_data_directory': config.s3_data_directory if hasattr(config, 's3_data_directory') else '/var/lib/trilio/triliovault-mounts'
        }
        self.s3_driver = S3Driver(s3_config)

    def reconcile_on_startup(self):
        """Reconcile all mounts on startup"""
        LOG.info("Starting reconciliation on startup...")

        # Reconcile S3 mounts first (adopt existing s3vaultfuse processes)
        self._reconcile_s3_processes()

        with session_scope() as session:
            # Get all unique target IDs for this host
            target_ids = session.query(BackupTargetMountLedger.backup_target_id).filter_by(
                host=self.config.node_id,
                deleted=False
            ).distinct().all()

            for (target_id,) in target_ids:
                try:
                    self._reconcile_target(session, target_id)
                except Exception as e:
                    LOG.error(f"Failed to reconcile target {target_id}: {e}", exc_info=True)

        LOG.info("Reconciliation complete")

    def _reconcile_s3_processes(self):
        """
        Reconcile S3 mounts by discovering existing s3vaultfuse processes.
        
        This finds any s3vaultfuse.py processes that are already running
        (e.g., from a previous instance of the service) and adopts them.
        """
        try:
            import psutil
            import os
            
            LOG.info("Scanning for existing s3vaultfuse processes...")
            
            adopted_count = 0
            
            # Find all s3vaultfuse.py processes
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    if not cmdline:
                        continue
                    
                    # Check if this is an s3vaultfuse.py process
                    if 's3vaultfuse.py' in ' '.join(cmdline):
                        # Extract mount path from command line
                        # Expected: /usr/bin/s3vaultfuse.py <mount_path>
                        if len(cmdline) >= 2:
                            mount_path = cmdline[-1]  # Last argument is mount path
                            
                            # Verify this is a valid mount path and it's actually mounted
                            if os.path.ismount(mount_path):
                                # Try to extract target_id from mount_path
                                # Assuming mount_path contains target info
                                target_id = self._extract_target_id_from_path(mount_path)
                                
                                if target_id:
                                    LOG.info(f"Adopting s3vaultfuse process: PID={proc.pid}, mount_path={mount_path}, target_id={target_id}")
                                    
                                    # Adopt the process
                                    self.s3_driver.mount_processes[target_id] = {
                                        'process': psutil.Process(proc.pid),
                                        'mount_path': mount_path,
                                        'pid': proc.pid
                                    }
                                    adopted_count += 1
                                else:
                                    LOG.warning(f"Found s3vaultfuse process (PID={proc.pid}) but couldn't determine target_id from path: {mount_path}")
                            else:
                                LOG.warning(f"Found s3vaultfuse process (PID={proc.pid}) but mount path not mounted: {mount_path}")
                
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    # Process disappeared or no permission, skip it
                    continue
            
            LOG.info(f"Adopted {adopted_count} existing s3vaultfuse process(es)")
            
        except ImportError:
            LOG.warning("psutil not available, cannot adopt existing s3vaultfuse processes")
        except Exception as e:
            LOG.error(f"Error during s3vaultfuse process reconciliation: {e}", exc_info=True)

    def _extract_target_id_from_path(self, mount_path: str) -> str:
        """
        Extract target_id from mount path by querying the database.
        
        The mount path comes from filesystem_export_mount_path in backup_targets table,
        so we can directly query for it.
        
        Args:
            mount_path: Full mount path from s3vaultfuse command line
            
        Returns:
            Target ID or None if can't be determined
        """
        try:
            # Query database for matching mount path
            with session_scope() as session:
                target = session.query(BackupTarget).filter_by(
                    filesystem_export_mount_path=mount_path,
                    type='s3',
                    deleted=False
                ).first()
                
                if target:
                    LOG.info(f"Found target {target.id} for mount path {mount_path}")
                    return target.id
                else:
                    LOG.warning(f"No target found with mount path: {mount_path}")
                    return None
            
        except Exception as e:
            LOG.error(f"Error extracting target_id from path {mount_path}: {e}")
            return None

    def _reconcile_target(self, session, target_id: str):
        """Reconcile a single target"""
        target = session.query(BackupTarget).filter_by(
            id=target_id, deleted=False
        ).first()

        if not target:
            LOG.warning(f"Target {target_id} not found during reconciliation")
            return

        # Compute desired state (number of active jobs)
        active_count = self._compute_active_count(session, target_id)

        # Check actual state
        if target.type == 'nfs':
            is_mounted = self.nfs_driver.is_mounted(target.filesystem_export_mount_path)
        elif target.type == 's3':
            is_mounted = self.s3_driver.is_mounted(target.filesystem_export_mount_path)
        else:
            LOG.warning(f"Unknown target type {target.type} for target {target_id}")
            return

        LOG.info(f"Reconciling {target.id} (type={target.type}): active_count={active_count}, is_mounted={is_mounted}")

        # Converge to desired state
        if active_count > 0 and not is_mounted:
            LOG.warning(f"Target {target.id} has active jobs but is not mounted")
            LOG.warning(f"Cannot remount during reconciliation (no Keystone token available)")
            LOG.warning(f"Jobs will retry mount requests on next operation")

            # Mark ledger entries as not mounted
            session.query(BackupTargetMountLedger).filter_by(
                backup_target_id=target_id,
                host=self.config.node_id,
                deleted=False
            ).update({'mounted': False})

        elif active_count == 0 and is_mounted:
            LOG.info(f"Unmounting {target.id} (no active jobs)")
            try:
                self.mount_service._perform_unmount(target)
                
                # Mark ledger entries as not mounted
                session.query(BackupTargetMountLedger).filter_by(
                    backup_target_id=target_id,
                    host=self.config.node_id
                ).update({'mounted': False})
                
                LOG.info(f"Successfully unmounted orphaned mount for {target.id}")
                
            except Exception as e:
                LOG.error(f"Failed to unmount {target.id}: {e}", exc_info=True)

        elif is_mounted:
            LOG.info(f"Adopting existing mount for {target.id}")

            # Mark active ledger entries as mounted
            updated = session.query(BackupTargetMountLedger).filter_by(
                backup_target_id=target_id,
                host=self.config.node_id,
                deleted=False
            ).update({'mounted': True})
            
            LOG.info(f"Marked {updated} ledger entries as mounted for {target.id}")
        
        else:
            # Not mounted and no active jobs - consistent state
            LOG.debug(f"Target {target.id} is in consistent state (not mounted, no active jobs)")

        session.commit()

    def _compute_active_count(self, session, target_id: str) -> int:
        """Compute active job count for target on this host"""
        # Get non-deleted ledger entries
        ledger_entries = session.query(BackupTargetMountLedger).filter_by(
            backup_target_id=target_id,
            host=self.config.node_id,
            deleted=False
        ).all()

        if not ledger_entries:
            return 0

        job_ids = [entry.jobid for entry in ledger_entries]

        # Count jobs in STARTING or RUNNING state
        return session.query(Job).filter(
            Job.jobid.in_(job_ids),
            Job.status.in_(['STARTING', 'RUNNING']),
            Job.deleted == False
        ).count()

    def get_reconciliation_status(self) -> dict:
        """
        Get current reconciliation status for monitoring.
        
        Returns:
            Dictionary with status information
        """
        status = {
            'node_id': self.config.node_id,
            'nfs_mounts': [],
            's3_mounts': [],
            'inconsistencies': []
        }
        
        with session_scope() as session:
            # Get all targets with ledger entries
            target_ids = session.query(BackupTargetMountLedger.backup_target_id).filter_by(
                host=self.config.node_id,
                deleted=False
            ).distinct().all()
            
            for (target_id,) in target_ids:
                target = session.query(BackupTarget).filter_by(
                    id=target_id, deleted=False
                ).first()
                
                if not target:
                    continue
                
                active_count = self._compute_active_count(session, target_id)
                
                if target.type == 'nfs':
                    is_mounted = self.nfs_driver.is_mounted(target.filesystem_export_mount_path)
                    mount_info = {
                        'target_id': target_id,
                        'mount_path': target.filesystem_export_mount_path,
                        'active_jobs': active_count,
                        'is_mounted': is_mounted
                    }
                    status['nfs_mounts'].append(mount_info)
                    
                elif target.type == 's3':
                    is_mounted = self.s3_driver.is_mounted(target.filesystem_export_mount_path)
                    process_info = self.s3_driver.get_mount_info(target_id)
                    
                    mount_info = {
                        'target_id': target_id,
                        'mount_path': target.filesystem_export_mount_path,
                        'active_jobs': active_count,
                        'is_mounted': is_mounted,
                        'process_info': process_info
                    }
                    status['s3_mounts'].append(mount_info)
                
                # Check for inconsistencies
                if (active_count > 0 and not is_mounted) or (active_count == 0 and is_mounted):
                    status['inconsistencies'].append({
                        'target_id': target_id,
                        'type': target.type,
                        'active_jobs': active_count,
                        'is_mounted': is_mounted,
                        'issue': 'mounted_without_jobs' if active_count == 0 else 'jobs_without_mount'
                    })
        
        return status
