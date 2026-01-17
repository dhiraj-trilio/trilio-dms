# trilio_dms/models.py
"""
Database models for DMS mount ledger.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index, text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class BackupTargetMountLedger(Base):
    """
    Ledger to track mount/unmount operations for backup targets.
    Supports concurrent job access tracking.
    """
    __tablename__ = 'backup_target_mount_ledger'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    
    # Soft delete flag (TINYINT(1) in MySQL)
    deleted = Column(Boolean, nullable=False, server_default=text('0'))
    
    # Version tracking
    version = Column(String(32), nullable=True)
    
    # Foreign key to backup_targets
    backup_target_id = Column(
        String(255), 
        ForeignKey('backup_targets.id', name='backup_target_mount_ledger_backup_target_fk', ondelete='SET NULL'),
        nullable=True
    )
    
    # Foreign key to job (indexed)
    jobid = Column(
        Integer,
        ForeignKey('job.jobid', name='backup_target_mount_ledger_fk', ondelete='CASCADE'),
        index=True,
        nullable=False
    )
    
    # Host information
    host = Column(String(255), nullable=False)
    
    # Mount status
    mounted = Column(Boolean, nullable=False, server_default=text('0'))
    
    # Additional metadata (optional - add if needed)
    mount_path = Column(String(512), nullable=True)
    mount_type = Column(String(50), nullable=True)  # e.g., 'nfs', 's3'
    
    # Composite index for efficient queries
    __table_args__ = (
        Index('idx_target_host_mounted', 'backup_target_id', 'host', 'mounted'),
        Index('idx_jobid_mounted', 'jobid', 'mounted'),
        Index('idx_deleted', 'deleted'),
    )
    
    def __repr__(self):
        return (
            f"<BackupTargetMountLedger("
            f"id={self.id}, "
            f"jobid={self.jobid}, "
            f"backup_target_id='{self.backup_target_id}', "
            f"host='{self.host}', "
            f"mounted={self.mounted}, "
            f"deleted={self.deleted})>"
        )


# tests/test_unmount_with_lock.py
"""
Unit tests for DMS unmount operation with global locking.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from trilio_dms.client import DMSClient
from trilio_dms.models import Base, BackupTargetMountLedger
from trilio_dms.lock_manager import DMSLockManager
import tempfile
import os


@pytest.fixture
def temp_lock_dir():
    """Create temporary directory for lock files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def db_session():
    """Create in-memory database session for testing."""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    
    # Create mock tables for foreign keys
    engine.execute("""
        CREATE TABLE IF NOT EXISTS job (
            jobid INTEGER PRIMARY KEY
        )
    """)
    engine.execute("""
        CREATE TABLE IF NOT EXISTS backup_targets (
            id VARCHAR(255) PRIMARY KEY
        )
    """)
    
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def dms_client(db_session, temp_lock_dir):
    """Create DMS client with test configuration."""
    client = DMSClient(
        rabbitmq_url='amqp://test',
        db_session=db_session
    )
    # Override lock manager with test lock directory
    client.lock_manager = DMSLockManager(lock_dir=temp_lock_dir, timeout=5)
    return client


def create_test_job(db_session, jobid):
    """Helper to create test job."""
    db_session.execute(f"INSERT INTO job (jobid) VALUES ({jobid})")
    db_session.commit()


def create_test_backup_target(db_session, backup_target_id):
    """Helper to create test backup target."""
    db_session.execute(
        f"INSERT INTO backup_targets (id) VALUES ('{backup_target_id}')"
    )
    db_session.commit()


class TestUnmountOperation:
    """Test cases for unmount operation with locking."""
    
    def test_unmount_single_mount(self, dms_client, db_session):
        """Test unmount when only one job has the target mounted."""
        # Setup: Create test data
        create_test_job(db_session, 1001)
        create_test_backup_target(db_session, 'target-001')
        
        # Create single mount ledger entry
        ledger = BackupTargetMountLedger(
            jobid=1001,
            backup_target_id='target-001',
            host='compute-01',
            mounted=True,
            deleted=False,
            mount_path='/mnt/target-001'
        )
        db_session.add(ledger)
        db_session.commit()
        
        # Mock the RPC call
        with patch.object(dms_client, '_send_unmount_request') as mock_unmount:
            result = dms_client.unmount_backup_target(
                jobid=1001,
                backup_target_id='target-001',
                host='compute-01'
            )
        
        # Verify physical unmount was called
        mock_unmount.assert_called_once_with('target-001', 'compute-01')
        
        # Verify result
        assert result['success'] is True
        assert result['unmounted'] is True
        assert result['active_mounts_remaining'] == 0
        
        # Verify ledger updated
        updated_ledger = db_session.query(BackupTargetMountLedger).filter_by(
            jobid=1001,
            deleted=False
        ).first()
        assert updated_ledger.mounted is False
    
    def test_unmount_multiple_mounts(self, dms_client, db_session):
        """Test unmount when multiple jobs have the target mounted."""
        # Setup: Create test data
        for jobid in [1001, 1002, 1003]:
            create_test_job(db_session, jobid)
        create_test_backup_target(db_session, 'target-001')
        
        # Create multiple mount ledger entries
        ledgers = [
            BackupTargetMountLedger(
                jobid=1001,
                backup_target_id='target-001',
                host='compute-01',
                mounted=True,
                deleted=False,
                mount_path='/mnt/target-001'
            ),
            BackupTargetMountLedger(
                jobid=1002,
                backup_target_id='target-001',
                host='compute-01',
                mounted=True,
                deleted=False,
                mount_path='/mnt/target-001'
            ),
            BackupTargetMountLedger(
                jobid=1003,
                backup_target_id='target-001',
                host='compute-01',
                mounted=True,
                deleted=False,
                mount_path='/mnt/target-001'
            )
        ]
        for ledger in ledgers:
            db_session.add(ledger)
        db_session.commit()
        
        # Mock the RPC call
        with patch.object(dms_client, '_send_unmount_request') as mock_unmount:
            result = dms_client.unmount_backup_target(
                jobid=1002,
                backup_target_id='target-001',
                host='compute-01'
            )
        
        # Verify physical unmount was NOT called
        mock_unmount.assert_not_called()
        
        # Verify result
        assert result['success'] is True
        assert result['unmounted'] is False
        assert result['active_mounts_remaining'] == 2
        assert 'physical mount retained' in result['message']
        
        # Verify only job 1002's ledger was updated
        job2_ledger = db_session.query(BackupTargetMountLedger).filter_by(
            jobid=1002,
            deleted=False
        ).first()
        assert job2_ledger.mounted is False
        
        # Verify other jobs still mounted
        for jobid in [1001, 1003]:
            ledger = db_session.query(BackupTargetMountLedger).filter_by(
                jobid=jobid,
                deleted=False
            ).first()
            assert ledger.mounted is True
    
    def test_unmount_last_of_multiple(self, dms_client, db_session):
        """Test unmount of last remaining mount after others unmounted."""
        # Setup: Create test data
        for jobid in [1001, 1002]:
            create_test_job(db_session, jobid)
        create_test_backup_target(db_session, 'target-001')
        
        # Create ledger entries with only one mounted
        ledgers = [
            BackupTargetMountLedger(
                jobid=1001,
                backup_target_id='target-001',
                host='compute-01',
                mounted=True,  # Only this one is mounted
                deleted=False,
                mount_path='/mnt/target-001'
            ),
            BackupTargetMountLedger(
                jobid=1002,
                backup_target_id='target-001',
                host='compute-01',
                mounted=False,  # Already unmounted
                deleted=False,
                mount_path='/mnt/target-001'
            )
        ]
        for ledger in ledgers:
            db_session.add(ledger)
        db_session.commit()
        
        # Mock the RPC call
        with patch.object(dms_client, '_send_unmount_request') as mock_unmount:
            result = dms_client.unmount_backup_target(
                jobid=1001,
                backup_target_id='target-001',
                host='compute-01'
            )
        
        # Verify physical unmount WAS called (last active mount)
        mock_unmount.assert_called_once_with('target-001', 'compute-01')
        
        # Verify result
        assert result['success'] is True
        assert result['unmounted'] is True
    
    def test_unmount_nonexistent_job(self, dms_client, db_session):
        """Test unmount for job that doesn't have an active mount."""
        # Setup: Create test data
        create_test_job(db_session, 1001)
        create_test_backup_target(db_session, 'target-001')
        
        # Create mount for different job
        ledger = BackupTargetMountLedger(
            jobid=1001,
            backup_target_id='target-001',
            host='compute-01',
            mounted=True,
            deleted=False
        )
        db_session.add(ledger)
        db_session.commit()
        
        # Create non-existent job
        create_test_job(db_session, 9999)
        
        # Try to unmount with non-existent mount
        result = dms_client.unmount_backup_target(
            jobid=9999,
            backup_target_id='target-001',
            host='compute-01'
        )
        
        # Verify failure
        assert result['success'] is False
        assert 'No active mount found' in result['message']
    
    def test_unmount_with_soft_deleted_entries(self, dms_client, db_session):
        """Test that soft-deleted entries are excluded from count."""
        # Setup: Create test data
        for jobid in [1001, 1002, 1003]:
            create_test_job(db_session, jobid)
        create_test_backup_target(db_session, 'target-001')
        
        # Create entries: 1 active, 1 mounted, 1 soft-deleted
        ledgers = [
            BackupTargetMountLedger(
                jobid=1001,
                backup_target_id='target-001',
                host='compute-01',
                mounted=True,
                deleted=False  # Active
            ),
            BackupTargetMountLedger(
                jobid=1002,
                backup_target_id='target-001',
                host='compute-01',
                mounted=True,
                deleted=True  # Soft-deleted, should be ignored
            ),
            BackupTargetMountLedger(
                jobid=1003,
                backup_target_id='target-001',
                host='compute-01',
                mounted=False,
                deleted=False  # Not mounted
            )
        ]
        for ledger in ledgers:
            db_session.add(ledger)
        db_session.commit()
        
        # Mock the RPC call
        with patch.object(dms_client, '_send_unmount_request') as mock_unmount:
            result = dms_client.unmount_backup_target(
                jobid=1001,
                backup_target_id='target-001',
                host='compute-01'
            )
        
        # Should perform physical unmount (only 1 active mounted entry)
        mock_unmount.assert_called_once()
        assert result['unmounted'] is True


class TestGlobalLocking:
    """Test cases for global lock mechanism."""
    
    def test_lock_acquisition_basic(self, temp_lock_dir):
        """Test basic lock acquisition and release."""
        lock_manager = DMSLockManager(lock_dir=temp_lock_dir, timeout=5)
        
        with lock_manager.acquire_lock():
            # Lock should be acquired
            lock_file = os.path.join(temp_lock_dir, 'dms_mount_unmount.lock')
            assert os.path.exists(lock_file)
        
        # Lock should be released after context exit
    
    def test_concurrent_lock_blocking(self, temp_lock_dir):
        """Test that concurrent lock attempts block properly."""
        lock_manager = DMSLockManager(lock_dir=temp_lock_dir, timeout=5)
        
        acquired_order = []
        
        def worker(worker_id):
            with lock_manager.acquire_lock():
                acquired_order.append(worker_id)
                time.sleep(0.2)  # Hold lock briefly
        
        # Start multiple threads trying to acquire lock
        threads = []
        for i in range(3):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Verify all workers acquired lock (in some order)
        assert len(acquired_order) == 3
        assert set(acquired_order) == {0, 1, 2}
    
    def test_lock_timeout(self, temp_lock_dir):
        """Test lock acquisition timeout."""
        lock_manager = DMSLockManager(lock_dir=temp_lock_dir, timeout=1)
        
        # Hold lock in one context
        with lock_manager.acquire_lock():
            # Try to acquire in another thread with short timeout
            def try_acquire():
                manager2 = DMSLockManager(lock_dir=temp_lock_dir, timeout=1)
                with manager2.acquire_lock():
                    pass
            
            thread = threading.Thread(target=try_acquire)
            thread.start()
            
            # Give it time to timeout
            time.sleep(1.5)
            thread.join(timeout=2)
            
            # Thread should have completed (with timeout error)
            assert not thread.is_alive()


class TestConcurrentUnmount:
    """Test concurrent unmount scenarios."""
    
    def test_concurrent_unmount_different_targets(self, db_session, temp_lock_dir):
        """Test concurrent unmounts of different targets serialize properly."""
        # Setup: Create test data
        for jobid in [1001, 1002]:
            create_test_job(db_session, jobid)
        for target_id in ['target-001', 'target-002']:
            create_test_backup_target(db_session, target_id)
        
        # Create mounts for different targets
        ledgers = [
            BackupTargetMountLedger(
                jobid=1001,
                backup_target_id='target-001',
                host='compute-01',
                mounted=True,
                deleted=False
            ),
            BackupTargetMountLedger(
                jobid=1002,
                backup_target_id='target-002',
                host='compute-01',
                mounted=True,
                deleted=False
            )
        ]
        for ledger in ledgers:
            db_session.add(ledger)
        db_session.commit()
        
        results = []
        
        def unmount_worker(jobid, target_id):
            client = DMSClient(
                rabbitmq_url='amqp://test',
                db_session=db_session
            )
            client.lock_manager = DMSLockManager(
                lock_dir=temp_lock_dir, 
                timeout=10
            )
            
            with patch.object(client, '_send_unmount_request'):
                result = client.unmount_backup_target(
                    jobid=jobid,
                    backup_target_id=target_id,
                    host='compute-01'
                )
                results.append(result)
        
        # Start concurrent unmount operations
        threads = [
            threading.Thread(
                target=unmount_worker, 
                args=(1001, 'target-001')
            ),
            threading.Thread(
                target=unmount_worker, 
                args=(1002, 'target-002')
            )
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Both should succeed
        assert len(results) == 2
        assert all(r['success'] for r in results)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
