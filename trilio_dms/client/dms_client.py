"""
Trilio DMS - Node-Specific Communication
Client sends to same-node server only, server accepts only same-node requests
"""

# ============================================================================
# FILE: trilio_dms/client/dms_client.py (UPDATED - Node-Specific)
# ============================================================================

"""DMS client library with node-specific communication"""

from datetime import datetime
from typing import Dict, Optional
import pika
import json
import socket

from trilio_dms.config import DMSConfig
from trilio_dms.utils.logger import get_logger

LOG = get_logger(__name__)


class DMSClient:
    """
    High-level DMS client that communicates only with DMS server on same node.
    Uses node-specific RabbitMQ queue: trilio_dms_ops_{node_id}
    """
    
    def __init__(self, config: DMSConfig = None, rabbitmq_url: str = None, 
                 wait_for_response: bool = True, node_id: str = None):
        """
        Initialize DMS client.
        
        Args:
            config: DMS configuration object
            rabbitmq_url: RabbitMQ connection URL
            wait_for_response: If True, wait for response (sync). If False, fire-and-forget (async)
            node_id: Node ID (defaults to hostname or from config)
        """
        if config:
            self.config = config
        else:
            self.config = DMSConfig()
            if rabbitmq_url:
                self.config.rabbitmq_url = rabbitmq_url
        
        # Determine node ID
        self.node_id = node_id or self.config.node_id
        if not self.node_id or self.node_id == 'localhost':
            self.node_id = socket.gethostname()
        
        # Node-specific queue name
        self.queue_name = f"{self.config.rabbitmq_queue}_{self.node_id}"
        
        self.wait_for_response = wait_for_response
        self.connection = None
        self.channel = None
        self.callback_queue = None
        self.response = None
        self.corr_id = None
        
        LOG.info(f"DMS Client initialized for node: {self.node_id}")
        LOG.info(f"Will send requests to queue: {self.queue_name}")
        
        # Connect immediately for async mode
        if not wait_for_response:
            self._connect()
    
    def _connect(self):
        """Establish connection to RabbitMQ"""
        try:
            if self.connection and not self.connection.is_closed:
                return
            
            params = pika.URLParameters(self.config.rabbitmq_url)
            params.heartbeat = self.config.rabbitmq_heartbeat
            
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
            
            # Declare node-specific queue (durable, survives broker restart)
            self.channel.queue_declare(
                queue=self.queue_name,
                durable=True,
                arguments={
                    'x-message-ttl': 3600000,  # 1 hour TTL for messages
                }
            )
            
            # Only setup callback queue for sync mode
            if self.wait_for_response:
                result = self.channel.queue_declare(queue='', exclusive=True)
                self.callback_queue = result.method.queue
                
                self.channel.basic_consume(
                    queue=self.callback_queue,
                    on_message_callback=self._on_response,
                    auto_ack=True
                )
            
            LOG.info(f"Connected to RabbitMQ (node: {self.node_id}, "
                    f"mode: {'sync' if self.wait_for_response else 'async'})")
            
        except Exception as e:
            LOG.error(f"Failed to connect to RabbitMQ: {e}")
            raise
    
    def _on_response(self, ch, method, props, body):
        """Handle RPC response (sync mode only)"""
        if self.corr_id == props.correlation_id:
            self.response = json.loads(body)
    
    def _send_async(self, request: Dict) -> Dict:
        """
        Send request without waiting for response (fire-and-forget).
        
        Args:
            request: Request payload
            
        Returns:
            Immediate acknowledgment
        """
        if not self.connection or self.connection.is_closed:
            self._connect()
        
        try:
            # Ensure node_id is in request
            request['node_id'] = self.node_id
            
            self.channel.basic_publish(
                exchange='',
                routing_key=self.queue_name,  # Node-specific queue
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent
                    headers={'node_id': self.node_id}
                ),
                body=json.dumps(request)
            )
            
            LOG.info(f"Sent async request to {self.queue_name}: "
                    f"{request['operation']} for job {request.get('job_id')}")
            
            return {
                'success': True,
                'message': f'Request sent to node {self.node_id} (async mode)',
                'node_id': self.node_id,
                'queue': self.queue_name,
                'job_id': request.get('job_id'),
                'async': True
            }
            
        except Exception as e:
            LOG.error(f"Failed to send async request: {e}")
            return {
                'success': False,
                'message': f'Failed to send request: {str(e)}',
                'node_id': self.node_id,
                'async': True
            }
    
    def _send_sync(self, request: Dict, timeout: Optional[int] = None) -> Dict:
        """
        Send request and wait for response (RPC style).
        
        Args:
            request: Request payload
            timeout: Timeout in seconds
            
        Returns:
            Response from server
        """
        if not self.connection or self.connection.is_closed:
            self._connect()
        
        timeout = timeout or self.config.operation_timeout
        self.response = None
        self.corr_id = str(__import__('uuid').uuid4())
        
        try:
            # Ensure node_id is in request
            request['node_id'] = self.node_id
            
            self.channel.basic_publish(
                exchange='',
                routing_key=self.queue_name,  # Node-specific queue
                properties=pika.BasicProperties(
                    reply_to=self.callback_queue,
                    correlation_id=self.corr_id,
                    delivery_mode=2,
                    headers={'node_id': self.node_id}
                ),
                body=json.dumps(request)
            )
            
            LOG.info(f"Sent sync request to {self.queue_name}: "
                    f"{request['operation']} for job {request.get('job_id')}")
            
            # Wait for response
            import time
            start_time = time.time()
            while self.response is None:
                self.connection.process_data_events(time_limit=1)
                if time.time() - start_time > timeout:
                    raise TimeoutError(
                        f"Request timed out after {timeout}s (node: {self.node_id})"
                    )
            
            return self.response
            
        except Exception as e:
            LOG.error(f"Failed to send sync request: {e}")
            raise
    
    def mount(self, job_id: int, target_id: str, keystone_token: str) -> Dict:
        """
        Request mount for a job on this node.
        
        Args:
            job_id: Job ID that needs the mount
            target_id: Backup target ID
            keystone_token: Valid Keystone token for authentication
            
        Returns:
            Response dict (immediate if async, actual result if sync)
        """
        request = {
            'operation': 'mount',
            'job_id': job_id,
            'target_id': target_id,
            'token': keystone_token,
            'node_id': self.node_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        LOG.info(f"Requesting mount for job {job_id}, target {target_id} on node {self.node_id}")
        
        if self.wait_for_response:
            response = self._send_sync(request)
            if response.get('success'):
                LOG.info(f"Mount successful: {response.get('mount_path')}")
            else:
                LOG.error(f"Mount failed: {response.get('message')}")
            return response
        else:
            return self._send_async(request)
    
    def unmount(self, job_id: int, target_id: str) -> Dict:
        """
        Request unmount when job completes on this node.
        
        Args:
            job_id: Job ID that completed
            target_id: Backup target ID
            
        Returns:
            Response dict (immediate if async, actual result if sync)
        """
        request = {
            'operation': 'unmount',
            'job_id': job_id,
            'target_id': target_id,
            'node_id': self.node_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        LOG.info(f"Requesting unmount for job {job_id}, target {target_id} on node {self.node_id}")
        
        if self.wait_for_response:
            response = self._send_sync(request)
            return response
        else:
            return self._send_async(request)
    
    def close(self):
        """Close connection to RabbitMQ"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            LOG.info(f"Closed RabbitMQ connection (node: {self.node_id})")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
