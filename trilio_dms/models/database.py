"""Database models - Updated with nfs_mount_opts column"""

from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from contextlib import contextmanager
from typing import Generator

from trilio_dms.config import DMSConfig
from trilio_dms.utils.logger import get_logger

LOG = get_logger(__name__)
Base = declarative_base()


class BackupTarget(Base):
    """Backup target metadata with NFS mount options"""
    __tablename__ = 'backup_targets'
    
    id = Column(String(255), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    deleted = Column(Boolean, default=False)
    type = Column(String(50), nullable=False)  # 's3' or 'nfs'
    filesystem_export = Column(String(255), nullable=False)  # NFS share or S3 bucket
    filesystem_export_mount_path = Column(String(255), nullable=False)  # Mount path
    status = Column(String(32), nullable=False)  # e.g., 'available', 'error'
    secret_ref = Column(String(512), nullable=True)  # Barbican secret reference for S3
    nfs_mount_opts = Column(String(255), nullable=True)  # NFS mount options (e.g., 'vers=4.1,rw')
    
    def __repr__(self):
        return f"<BackupTarget(id={self.id}, type={self.type}, export={self.filesystem_export})>"
    
    def get_display_name(self) -> str:
        """Get display name from filesystem_export"""
        return self.filesystem_export.replace('/', '_').replace(':', '_')
    
    def get_nfs_mount_options(self) -> str:
        """Get NFS mount options with fallback to defaults"""
        if self.type == 'nfs':
            return self.nfs_mount_opts or 'defaults'
        return ''


class BackupTargetMountLedger(Base):
    """Job-driven mount bindings ledger"""
    __tablename__ = 'backup_target_mount_ledger'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    deleted = Column(Boolean, default=False)
    version = Column(String(32))
    backup_target_id = Column(String(255), nullable=False, index=True)
    jobid = Column(Integer, nullable=False, index=True)
    host = Column(String(255), nullable=False)
    mounted = Column(Boolean, default=False, nullable=False)
    
    def __repr__(self):
        return f"<BackupTargetMountLedger(id={self.id}, target={self.backup_target_id}, job={self.jobid})>"


class Job(Base):
    """Authoritative job table"""
    __tablename__ = 'job'
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    deleted = Column(Boolean, default=False)
    version = Column(String(255))
    jobid = Column(Integer, primary_key=True, autoincrement=True)
    progress = Column(Integer, default=0)
    status = Column(String(255))
    completed_at = Column(DateTime, nullable=True)
    action = Column(String(255))
    parent_jobid = Column(Integer, nullable=True)
    
    def __repr__(self):
        return f"<Job(jobid={self.jobid}, status={self.status})>"


class JobDetails(Base):
    """Job details with host and target information"""
    __tablename__ = 'job_details'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    jobid = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    deleted = Column(Boolean, default=False)
    version = Column(String(32))
    data = Column(Text)
    
    def __repr__(self):
        return f"<JobDetails(id={self.id}, jobid={self.jobid})>"

class DatabaseManager:
    """Database connection and session management"""
    
    def __init__(self, config: DMSConfig):
        self.config = config
        self.engine = None
        self.session_factory = None
        self.Session = None
        
    def initialize(self):
        """Initialize database connection"""
        LOG.info(f"Initializing database connection: {self.config.db_url}")
        self.engine = create_engine(
            self.config.db_url,
            pool_size=self.config.db_pool_size,
            pool_recycle=self.config.db_pool_recycle,
            echo=False
        )
        
        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)
        
        # Create session factory
        self.session_factory = sessionmaker(bind=self.engine)
        self.Session = scoped_session(self.session_factory)
        
        LOG.info("Database initialized successfully")
    
    def get_session(self) -> Session:
        """Get database session"""
        if not self.Session:
            self.initialize()
        return self.Session()
    
    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Provide transactional scope for database operations"""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def close(self):
        """Close database connections"""
        if self.Session:
            self.Session.remove()
        if self.engine:
            self.engine.dispose()


# Global database manager instance
_db_manager = None


def initialize_database(config: DMSConfig):
    """Initialize global database manager"""
    global _db_manager
    _db_manager = DatabaseManager(config)
    _db_manager.initialize()


def get_session() -> Session:
    """Get database session"""
    if not _db_manager:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    return _db_manager.get_session()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide transactional scope"""
    if not _db_manager:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    with _db_manager.session_scope() as session:
        yield session
