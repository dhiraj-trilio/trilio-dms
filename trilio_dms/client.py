"""
Trilio DMS Client - Database and RabbitMQ Client with Global Locking
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
from trilio_dms.lock_manager import get_lock_manager, DMSLockManager

logging.basicConfig(
    level=DMSConfig.LOG_LEVEL,
    format=DMSConfig.LOG_FORMAT
)
logger = logging.getLogger(__name__)


# Exception classes for DMS Client
class DMSClientError(Exception):
    """Base exception for DMS Client errors."""
    pass


class DMSMountError(DMSClientError):
    """Exception raised when mount operation fails."""
    pass


class DMSUnmountError(DMSClientError):
    """Exception raised when unmount operation fails."""
    pass


class DMSLockTimeoutError(DMSClientError):
    """Exception raised when lock acquisition times out."""
    pass


class DMSClient:
    """DMS Client for managing mount operations with global locking"""

    def __init__(self, db_url: Optional[str] = None,
                 rabbitmq_url: Optional[str] = None,
                 timeout: Optional[int] = None,
                 lock_timeout: Optional[int] = None,
                 lock_dir: Optional[str] = None):
        """Initialize DMS Client"""
        
        # Ensure client config is loaded
        from trilio_dms.config import DMSConfig
        if not DMSConfig._loaded:
            DMSConfig.load_config(config_type='client')
        
        self.db_url = db_url or DMSConfig.DB_URL
        self.rabbitmq_url = rabbitmq_url or DMSConfig.RABBITMQ_URL
        self.timeout = timeout or DMSConfig.REQUEST_TIMEOUT

        # Setup lock manager
        self.lock_manager = get_lock_manager(
            lock_dir=lock_dir,
            timeout=lock_timeout or 300
        )
        logger.info("Lock manager initialized")

        # Setup database
        try:
            self.engine = create_engine(self.db_url, pool_pre_ping=True)
            Base.metadata.create_all(self.engine)
            self.SessionLocal = sessionmaker(bind=self.engine)
            logger.info("Database connection established")
        except Exception as e:
            raise DatabaseException(f"Failed to initialize database: {e}")

        # Setup RabbitMQ
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
        """Mount with global locking"""
        request['action'] = 'mount'
        try:
            with self.lock_manager.acquire_lock("mount_unmount"):
                return self._execute_mount_request(request)
        except TimeoutError as e:
            logger.error(f"Lock timeout for mount: {e}")
            return create_response('error', f'Could not acquire lock: {e}')

    def unmount(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Unmount with smart logic and global locking"""
        request['action'] = 'unmount'
        try:
            with self.lock_manager.acquire_lock("mount_unmount"):
                return self._execute_unmount_request(request)
        except TimeoutError as e:
            logger.error(f"Lock timeout for unmount: {e}")
            return create_response('error', f'Could not acquire lock: {e}')

    def _execute_mount_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute mount with lock held"""
        session = self.SessionLocal()
        
        try:
            validate_request_structure(request)

            job_id = int(request['job']['jobid'])
            backup_target_id = request['backup_target']['id']
            host = request['host']

            logger.info(f"Mount - jobid={job_id}, target={backup_target_id}, host={host}")

            # Check if already mounted for this job
            existing = session.query(BackupTargetMountLedger).filter(
                and_(
                    BackupTargetMountLedger.jobid == job_id,
                    BackupTargetMountLedger.backup_target_id == backup_target_id,
                    BackupTargetMountLedger.host == host
                )
            ).first()

            if existing and existing.mounted:
                logger.info(f"Already mounted for jobid={job_id}, reusing")
                # Get mount path from request body
                mount_path = request['backup_target'].get('filesystem_export_mount_path')
                
                response = create_response(
                    'success',
                    success_msg='Target already mounted (reused existing)'
                )
                response['mount_path'] = mount_path
                response['reused_existing'] = True
                
                return response

            # Check if mounted by other jobs
            other_mounts = session.query(BackupTargetMountLedger).filter(
                and_(
                    BackupTargetMountLedger.backup_target_id == backup_target_id,
                    BackupTargetMountLedger.host == host,
                    BackupTargetMountLedger.mounted == True
                )
            ).first()

            physically_mounted = False
            
            if not other_mounts:
                # Need to physically mount
                logger.info("No existing mount. Sending mount request to DMS server")
                response = self._send_request(request)
                
                if response['status'] != 'success':
                    logger.error(f"Mount failed: {response.get('error_msg')}")
                    return response
                
                physically_mounted = True
                logger.info(f"Successfully mounted {backup_target_id} on {host}")
            else:
                logger.info("Reusing existing mount from another job")

            # Create or update ledger
            if existing:
                existing.mounted = True
                logger.debug(f"Updated ledger for jobid={job_id}")
            else:
                ledger = BackupTargetMountLedger(
                    jobid=job_id,
                    backup_target_id=backup_target_id,
                    host=host,
                    mounted=True
                )
                session.add(ledger)
                logger.debug(f"Created ledger for jobid={job_id}")

            try:
                session.commit()
                logger.info(f"Ledger updated: jobid={job_id}, mounted=True")
            except Exception as e:
                session.rollback()
                error_msg = str(e)
                
                # Handle foreign key constraint errors
                if 'foreign key constraint' in error_msg.lower():
                    if 'jobid' in error_msg.lower():
                        logger.error(f"Job {job_id} does not exist in job table")
                        return create_response(
                            'error',
                            f'Job {job_id} not found. Please ensure job exists before mounting.'
                        )
                    elif 'backup_target' in error_msg.lower():
                        logger.error(f"Backup target {backup_target_id} does not exist")
                        return create_response(
                            'error',
                            f'Backup target {backup_target_id} not found.'
                        )
                
                # Re-raise for other errors
                raise

            # Get mount path from request body
            mount_path = request['backup_target'].get('filesystem_export_mount_path')
            
            response = create_response(
                'success',
                success_msg='Mount successful'
            )
            # Add additional fields to response
            response['mount_path'] = mount_path
            response['reused_existing'] = not physically_mounted
            response['physically_mounted'] = physically_mounted
            
            return response

        except RequestValidationException as e:
            logger.error(f"Validation failed: {e}")
            return create_response('error', str(e))
        except Exception as e:
            logger.error(f"Mount failed: {e}", exc_info=True)
            session.rollback()
            return create_response('error', str(e))
        finally:
            session.close()

    def _execute_unmount_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute unmount with smart logic"""
        session = self.SessionLocal()
        
        try:
            validate_request_structure(request)

            job_id = int(request['job']['jobid'])
            backup_target_id = request['backup_target']['id']
            host = request['host']

            logger.info(f"Unmount - jobid={job_id}, target={backup_target_id}, host={host}")

            # Query active mounts
            active_mounts = session.query(BackupTargetMountLedger).filter(
                and_(
                    BackupTargetMountLedger.backup_target_id == backup_target_id,
                    BackupTargetMountLedger.host == host,
                    BackupTargetMountLedger.mounted == True
                )
            ).all()

            mount_count = len(active_mounts)
            logger.info(f"Found {mount_count} active mount(s)")

            # Find current job's entry
            current_job_entry = None
            for mount in active_mounts:
                if mount.jobid == job_id:
                    current_job_entry = mount
                    break

            if not current_job_entry:
                logger.warning(f"No active mount found for jobid={job_id}")
                return create_response(
                    'error',
                    error_msg='No active mount found for this job',
                    unmounted=False,
                    active_mounts_remaining=mount_count
                )

            physically_unmounted = False

            # Check if should physically unmount
            if mount_count == 1:
                # Last mount - safe to unmount
                logger.info("Single active mount. Sending unmount to DMS server")
                
                response = self._send_request(request)
                
                if response['status'] != 'success':
                    logger.error(f"Unmount failed: {response.get('error_msg')}")
                    return response
                
                physically_unmounted = True
                logger.info(f"Successfully unmounted {backup_target_id} on {host}")
            else:
                # Multiple mounts - skip physical unmount
                logger.info(f"Multiple mounts ({mount_count}). Skipping physical unmount")

            # Update ledger
            current_job_entry.mounted = False
            session.commit()
            logger.info(f"Ledger updated: jobid={job_id}, mounted=False")

            return create_response(
                'success',
                success_msg=(
                    'Successfully unmounted' if physically_unmounted
                    else 'Ledger updated, physical mount retained for other jobs'
                ),
                unmounted=physically_unmounted,
                active_mounts_remaining=mount_count - 1
            )

        except RequestValidationException as e:
            logger.error(f"Validation failed: {e}")
            return create_response('error', str(e))
        except Exception as e:
            logger.error(f"Unmount failed: {e}", exc_info=True)
            session.rollback()
            return create_response('error', str(e))
        finally:
            session.close()

    def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send request to DMS Server via RabbitMQ"""
        self.response = None
        self.corr_id = str(uuid.uuid4())
        queue_name = f"dms.{request['host']}"

        try:
            self.channel.queue_declare(queue=queue_name, durable=True)
            
            self.channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                properties=pika.BasicProperties(
                    reply_to=self.callback_queue,
                    correlation_id=self.corr_id,
                    delivery_mode=2,
                    content_type='application/json'
                ),
                body=json.dumps(request)
            )

            logger.info(f"Sent {request.get('action')} to {queue_name}, corr_id={self.corr_id}")

            # Wait for response
            timeout_counter = 0
            while self.response is None:
                self.connection.process_data_events(time_limit=1)
                timeout_counter += 1
                if timeout_counter > self.timeout:
                    raise RequestTimeoutException(f"Timeout after {self.timeout}s")

            logger.info(f"Received response: {self.response.get('status')}")
            return self.response

        except RequestTimeoutException:
            raise
        except Exception as e:
            raise RabbitMQException(f"Failed to send request: {e}")

    def get_mount_status(self, job_id: int, backup_target_id: str) -> Optional[BackupTargetMountLedger]:
        """Get mount status"""
        session = self.SessionLocal()
        try:
            return session.query(BackupTargetMountLedger).filter(
                and_(
                    BackupTargetMountLedger.jobid == job_id,
                    BackupTargetMountLedger.backup_target_id == backup_target_id
                )
            ).first()
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return None
        finally:
            session.close()

    def get_active_mounts(self, host: Optional[str] = None,
                         backup_target_id: Optional[str] = None) -> List[BackupTargetMountLedger]:
        """Get all active mounts"""
        session = self.SessionLocal()
        try:
            query = session.query(BackupTargetMountLedger).filter(
                BackupTargetMountLedger.mounted == True
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

    def close(self):
        """Close connections"""
        if self.connection and not self.connection.is_closed:
            try:
                self.connection.close()
                logger.info("RabbitMQ closed")
            except Exception as e:
                logger.warning(f"Error closing RabbitMQ: {e}")
        if self.engine:
            try:
                self.engine.dispose()
                logger.info("Database closed")
            except Exception as e:
                logger.warning(f"Error closing database: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class MountContext:
    """Context manager for automatic mount/unmount"""

    def __init__(self, client: DMSClient, request: Dict[str, Any]):
        self.client = client
        self.request = request
        self.mount_response = None
        self.mount_path = None

    def __enter__(self):
        self.request['action'] = 'mount'
        self.mount_response = self.client.mount(self.request)

        if self.mount_response['status'] != 'success':
            raise DMSClientException(
                f"Mount failed: {self.mount_response.get('error_msg')}"
            )

        # Get mount path from response (which comes from request body)
        self.mount_path = self.mount_response.get('mount_path')
        
        if not self.mount_path:
            # Fallback to backup_target fields
            self.mount_path = self.request['backup_target'].get('filesystem_export_mount_path')
        
        logger.info(f"Mount successful: {self.mount_path}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.request['action'] = 'unmount'
            response = self.client.unmount(self.request)
            
            if response['status'] == 'success':
                if response.get('unmounted'):
                    logger.info("Unmount successful (physically unmounted)")
                else:
                    logger.info(
                        f"Unmount successful (ledger updated, "
                        f"{response.get('active_mounts_remaining', 0)} jobs still using)"
                    )
            else:
                logger.warning(f"Unmount failed: {response.get('error_msg')}")
        except Exception as e:
            logger.error(f"Error during unmount: {e}")

    def get_mount_path(self) -> str:
        return self.mount_path
