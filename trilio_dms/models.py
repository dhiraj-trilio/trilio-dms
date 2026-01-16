"""
Database models for DMS mount ledger.
"""

from sqlalchemy import Column, Integer, String, Boolean, Index, PrimaryKeyConstraint
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class BackupTargetMountLedger(Base):
    """
    Ledger to track mount/unmount operations for backup targets.
    Supports concurrent job access tracking.
    
    Note: Foreign key constraints are defined at database level.
    This model does not enforce them to allow flexibility.
    """
    __tablename__ = 'backup_target_mount_ledger'
    
    # Composite primary key columns
    jobid = Column(Integer, nullable=False)
    backup_target_id = Column(String(255), nullable=False)
    host = Column(String(255), nullable=False)
    
    # Mount status
    mounted = Column(Boolean, default=False, nullable=False)
    
    # Define composite primary key and indexes
    # Note: Foreign key constraints exist at DB level but not defined here
    __table_args__ = (
        PrimaryKeyConstraint('jobid', 'backup_target_id', 'host', name='pk_mount_ledger'),
        Index('idx_target_host_mounted', 'backup_target_id', 'host', 'mounted'),
        Index('idx_jobid', 'jobid'),
    )
    
    def __repr__(self):
        return (
            f"<BackupTargetMountLedger("
            f"jobid={self.jobid}, "
            f"backup_target_id='{self.backup_target_id}', "
            f"host='{self.host}', "
            f"mounted={self.mounted})>"
        )

