"""
Database models for Trilio DMS
"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class BackupTargetMountLedger(Base):
    """
    Database model for backup target mount ledger
    Tracks all mount/unmount operations
    """
    __tablename__ = 'backup_target_mount_ledger'
    
    id = Column(String(36), primary_key=True)
    backup_target_id = Column(String(36), nullable=False, index=True)
    job_id = Column(String(36), nullable=False, index=True)
    host = Column(String(255), nullable=False, index=True)
    action = Column(String(20), nullable=False)  # 'mount' or 'unmount'
    status = Column(String(20), nullable=False, index=True)  # 'pending', 'success', 'error'
    mount_path = Column(String(512), nullable=True)
    error_msg = Column(Text, nullable=True)
    success_msg = Column(Text, nullable=True)
    request_data = Column(Text, nullable=True)  # JSON of full request
    response_data = Column(Text, nullable=True)  # JSON of response
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Composite indexes for common queries
    __table_args__ = (
        Index('idx_job_target', 'job_id', 'backup_target_id'),
        Index('idx_status_created', 'status', 'created_at'),
        Index('idx_action_status', 'action', 'status'),
    )
    
    def __repr__(self):
        return (f"<BackupTargetMountLedger(id={self.id}, "
                f"target={self.backup_target_id}, "
                f"job={self.job_id}, "
                f"action={self.action}, "
                f"status={self.status})>")
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'backup_target_id': self.backup_target_id,
            'job_id': self.job_id,
            'host': self.host,
            'action': self.action,
            'status': self.status,
            'mount_path': self.mount_path,
            'error_msg': self.error_msg,
            'success_msg': self.success_msg,
            'request_data': self.request_data,
            'response_data': self.response_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
