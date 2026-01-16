"""
Trilio DMS Client - Database and RabbitMQ Client
Responsibilities:
- Manage backup_target_mount_ledger table
- Send mount/unmount requests to DMS Server via RabbitMQ
- Track mount/unmount operations in database
"""

import json
import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import pika
from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from trilio_dms.models import BackupTargetMountLedger, Base
from trilio_dms.config import DMSConfig
from trilio_dms.exceptions import (
    DMSClientException, RequestValidationException, 
    RequestTimeoutException, DatabaseException, RabbitMQException
)
from trilio_dms.utils import (
    validate_request_structure, create_response, 
    safe_json_dumps, safe_json_loads
)

logging.basicConfig(
    level=DMSConfig.LOG_LEVEL,
    format=DMSConfig.LOG_FORMAT
)
logger = logging.getLogger(__name__)


class DMSClient:
    """DMS Client for managing mount operations and database"""
    
    def __init__(self, db_url: Optional[str] = None, 
                 rabbitmq_url: Optional[str] = None, 
                 timeout: Optional[int] = None):
        """
        Initialize DMS Client
        
        Args:
            db_url: Database URL (uses config default if not provided)
            rabbitmq_url: RabbitMQ URL (uses config default if not provided)
            timeout: Request timeout in seconds (uses config default if not provided)
        """
        self.db_url = db_url or DMSConfig.DB_URL
        self.rabbitmq_url = rabbitmq_url or DMSConfig.RABBITMQ_URL
        self.timeout = timeout or DMSConfig.REQUEST_TIMEOUT
        
        # Setup database
        try:
            self.engine = create_engine(self.db_url, pool_pre_ping=True)
            Base.metadata.create_all(self.engine)
            self.SessionLocal = sessionmaker(bind=self.engine)
            logger.info("Database connection established")
        except Exception as e:
            raise DatabaseException(f"Failed to initialize database: {e}")
        
        # Setup RabbitMQ connection
        self.connection = None
        self.channel = None
        self.callback_queue = None
        self.response = None
        self.corr_id = None
        self._setup_rabbitmq()
    
    def _setup_rabbitmq(self):
        """Setup RabbitMQ connection"""
        try:
            self.connection = pika.BlockingConnection(
                pika.URLParameters(self.rabbitmq_url)
            )
            self.channel = self.connection.channel()
            
            # Declare callback queue for responses
            result = self.channel.queue_declare(queue='', exclusive=True)
            self.callback_queue = result.method.queue
            
            self.channel.basic_consume(
                queue=self.callback_queue,
                on_message_callback=self._on_response,
                auto_ack=True
            )
            
            logger.info("RabbitMQ connection established")
        except Exception as e:
            raise RabbitMQException(f"Failed to setup RabbitMQ: {e}")
    
    def _on_response(self, ch, method, props, body):
        """Handle response from DMS Server"""
        if self.corr_id == props.correlation_id:
            try:
                self.response = json.loads(body)
            except json.JSONDecodeError:
                self.response = create_response('error', 'Invalid response format')
    
    def mount(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send mount request to DMS Server and track in database
        
        Args:
            request: Mount request containing all required fields
        
        Returns:
            Response dict with status, error_msg, success_msg
        """
        request['action'] = 'mount'
        return self._execute_request(request)
    
    def unmount(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send unmount request to DMS Server and track in database
        
        Args:
            request: Unmount request containing all required fields
        
        Returns:
            Response dict with status, error_msg, success_msg
        """
        request['action'] = 'unmount'
        return self._execute_request(request)
    
    def _execute_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute mount/unmount request and track in database"""
        session = self.SessionLocal()
        ledger = None
        action = request.get('action', 'unknown')
        
        try:
            # Validate request
            validate_request_structure(request)
            
            job_id = int(request['job']['jobid'])
            backup_target_id = request['backup_target']['id']
            host = request['host']
            
            # Check if ledger entry exists
            ledger = session.query(BackupTargetMountLedger).filter(
                and_(
                    BackupTargetMountLedger.jobid == job_id,
                    BackupTargetMountLedger.backup_target_id == backup_target_id,
                    BackupTargetMountLedger.deleted == False
                )
            ).first()
            
            if action == 'mount':
                if not ledger:
                    # Create new ledger entry
                    ledger = BackupTargetMountLedger(
                        backup_target_id=backup_target_id,
                        jobid=job_id,
                        host=host,
                        mounted=False,
                        deleted=False,
                        version='1.0',
                        created_at=datetime.utcnow()
                    )
                    session.add(ledger)
                    session.commit()
                    logger.info(f"Created ledger entry {ledger.id} for mount request")
                else:
                    logger.info(f"Using existing ledger entry {ledger.id}")
            
            elif action == 'unmount':
                if not ledger:
                    logger.warning(f"No ledger entry found for unmount: job={job_id}, target={backup_target_id}")
                    # Still send unmount request to server
            
            # Send request to DMS Server
            response = self._send_request(request)
            
            # Update ledger based on response
            if ledger:
                if action == 'mount' and response['status'] == 'success':
                    ledger.mounted = True
                    ledger.updated_at = datetime.utcnow()
                    session.commit()
                    logger.info(f"Updated ledger {ledger.id}: mounted=True")
                
                elif action == 'unmount' and response['status'] == 'success':
                    ledger.mounted = False
                    ledger.updated_at = datetime.utcnow()
                    session.commit()
                    logger.info(f"Updated ledger {ledger.id}: mounted=False")
            
            return response
            
        except RequestValidationException as e:
            logger.error(f"Request validation failed: {e}")
            return create_response('error', str(e))
            
        except Exception as e:
            logger.error(f"Request execution failed: {e}", exc_info=True)
            return create_response('error', str(e))
        
        finally:
            session.close()
    
    def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send request to DMS Server via RabbitMQ and wait for response"""
        self.response = None
        self.corr_id = str(uuid.uuid4())
        
        # Determine target queue based on host
        queue_name = f"dms.{request['host']}"
        
        try:
            # Declare queue if it doesn't exist
            self.channel.queue_declare(queue=queue_name, durable=True)
            
            # Send request
            self.channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                properties=pika.BasicProperties(
                    reply_to=self.callback_queue,
                    correlation_id=self.corr_id,
                    delivery_mode=2,  # persistent
                    content_type='application/json'
                ),
                body=json.dumps(request)
            )
            
            logger.info(f"Sent request to queue: {queue_name}, correlation_id: {self.corr_id}")
            
            # Wait for response
            timeout_counter = 0
            while self.response is None:
                self.connection.process_data_events(time_limit=1)
                timeout_counter += 1
                
                if timeout_counter > self.timeout:
                    raise RequestTimeoutException(
                        f"Request timeout after {self.timeout} seconds"
                    )
            
            return self.response
            
        except RequestTimeoutException:
            raise
        except Exception as e:
            raise RabbitMQException(f"Failed to send request: {e}")
    
    def get_mount_status(self, job_id: int, backup_target_id: str) -> Optional[BackupTargetMountLedger]:
        """
        Get mount status from ledger
        
        Args:
            job_id: Job ID
            backup_target_id: Backup target ID
            
        Returns:
            Ledger entry or None
        """
        session = self.SessionLocal()
        try:
            ledger = session.query(BackupTargetMountLedger).filter(
                and_(
                    BackupTargetMountLedger.jobid == job_id,
                    BackupTargetMountLedger.backup_target_id == backup_target_id,
                    BackupTargetMountLedger.deleted == False
                )
            ).first()
            
            return ledger
        except Exception as e:
            logger.error(f"Failed to get mount status: {e}")
            return None
        finally:
            session.close()
    
    def get_active_mounts(self, host: Optional[str] = None, 
                         backup_target_id: Optional[str] = None) -> List[BackupTargetMountLedger]:
        """
        Get all active mounts
        
        Args:
            host: Filter by host (optional)
            backup_target_id: Filter by backup target ID (optional)
            
        Returns:
            List of active mount ledger entries
        """
        session = self.SessionLocal()
        try:
            query = session.query(BackupTargetMountLedger).filter(
                and_(
                    BackupTargetMountLedger.mounted == True,
                    BackupTargetMountLedger.deleted == False
                )
            )
            
            if host:
                query = query.filter(BackupTargetMountLedger.host == host)
            
            if backup_target_id:
                query = query.filter(BackupTargetMountLedger.backup_target_id == backup_target_id)
            
            return query.all()
            
        except Exception as e:
            logger.error(f"Failed to get active mounts: {e}")
            return []
        finally:
            session.close()
    
    def get_ledger_history(self, backup_target_id: str, limit: int = 100) -> List[BackupTargetMountLedger]:
        """
        Get ledger history for a backup target
        
        Args:
            backup_target_id: Backup target ID
            limit: Maximum number of entries to return
            
        Returns:
            List of ledger entries
        """
        session = self.SessionLocal()
        try:
            entries = session.query(BackupTargetMountLedger).filter(
                and_(
                    BackupTargetMountLedger.backup_target_id == backup_target_id,
                    BackupTargetMountLedger.deleted == False
                )
            ).order_by(
                BackupTargetMountLedger.created_at.desc()
            ).limit(limit).all()
            
            return entries
        except Exception as e:
            logger.error(f"Failed to get ledger history: {e}")
            return []
        finally:
            session.close()
    
    def soft_delete_entry(self, job_id: int, backup_target_id: str) -> bool:
        """
        Soft delete a ledger entry
        
        Args:
            job_id: Job ID
            backup_target_id: Backup target ID
            
        Returns:
            True if successful
        """
        session = self.SessionLocal()
        try:
            ledger = session.query(BackupTargetMountLedger).filter(
                and_(
                    BackupTargetMountLedger.jobid == job_id,
                    BackupTargetMountLedger.backup_target_id == backup_target_id,
                    BackupTargetMountLedger.deleted == False
                )
            ).first()
            
            if ledger:
                ledger.deleted = True
                ledger.deleted_at = datetime.utcnow()
                ledger.updated_at = datetime.utcnow()
                session.commit()
                logger.info(f"Soft deleted ledger entry {ledger.id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to soft delete entry: {e}")
            session.rollback()
            return False
        finally:
            session.close()
    
    def close(self):
        """Close connections"""
        if self.connection and not self.connection.is_closed:
            try:
                self.connection.close()
                logger.info("RabbitMQ connection closed")
            except Exception as e:
                logger.warning(f"Error closing RabbitMQ connection: {e}")
        
        if self.engine:
            try:
                self.engine.dispose()
                logger.info("Database connection closed")
            except Exception as e:
                logger.warning(f"Error closing database connection: {e}")


class MountContext:
    """Context manager for automatic mount/unmount"""
    
    def __init__(self, client: DMSClient, request: Dict[str, Any]):
        """
        Initialize mount context
        
        Args:
            client: DMSClient instance
            request: Mount request dictionary
        """
        self.client = client
        self.request = request
        self.mount_response = None
        self.mount_path = None
    
    def __enter__(self):
        """Mount on enter"""
        self.request['action'] = 'mount'
        self.mount_response = self.client.mount(self.request)
        
        if self.mount_response['status'] != 'success':
            raise DMSClientException(
                f"Mount failed: {self.mount_response.get('error_msg')}"
            )
        
        # Get mount path from backup_target
        self.mount_path = self.request['backup_target'].get(
            'filesystem_export_mount_path',
            f"{DMSConfig.MOUNT_BASE_PATH}/{self.request['backup_target']['id']}"
        )
        logger.info(f"Mount successful: {self.mount_path}")
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Unmount on exit"""
        try:
            self.request['action'] = 'unmount'
            unmount_response = self.client.unmount(self.request)
            
            if unmount_response['status'] == 'success':
                logger.info("Unmount successful")
            else:
                logger.warning(f"Unmount failed: {unmount_response.get('error_msg')}")
        except Exception as e:
            logger.error(f"Error during unmount: {e}")
    
    def get_mount_path(self) -> str:
        """Get mount path"""
        return self.mount_path
