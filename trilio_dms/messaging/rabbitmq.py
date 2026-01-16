"""RabbitMQ messaging with improved error handling"""

import json
import socket
from typing import Callable
import pika

from trilio_dms.config import DMSConfig
from trilio_dms.utils.logger import get_logger
from trilio_dms.utils.exceptions import MessagingException
from trilio_dms.utils.validators import validate_and_fix_rabbitmq_url

LOG = get_logger(__name__)


class RabbitMQServer:
    """RabbitMQ server with better error handling"""
    
    def __init__(self, config: DMSConfig, handler: Callable):
        self.config = config
        self.handler = handler
        self.connection = None
        self.channel = None
        self.consuming = False
        
        # Determine node ID
        self.node_id = config.node_id
        if not self.node_id or self.node_id == 'localhost':
            self.node_id = socket.gethostname()
        
        # Node-specific queue name
        self.queue_name = f"{config.rabbitmq_queue}_{self.node_id}"
        
        LOG.info(f"DMS Server initialized for node: {self.node_id}")
        LOG.info(f"Will consume from queue: {self.queue_name}")
    
    def connect(self):
        """Connect to RabbitMQ with better error messages"""
        try:
            # Get validated URL
            rabbitmq_url = self.config.rabbitmq_url
            
            LOG.info(f"Connecting to RabbitMQ: {self._safe_url(rabbitmq_url)}")
            
            params = pika.URLParameters(rabbitmq_url)
            params.heartbeat = self.config.rabbitmq_heartbeat
            
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
            
            # Declare node-specific queue
            self.channel.queue_declare(
                queue=self.queue_name,
                durable=True,
                arguments={
                    'x-message-ttl': 3600000,  # 1 hour TTL
                }
            )
            
            LOG.info(f"Connected to RabbitMQ, listening on queue: {self.queue_name}")
            
        except ValueError as e:
            # URL validation error
            raise MessagingException(
                f"Invalid RabbitMQ URL: {e}\n"
                f"Expected format: amqp://user:pass@host:port or amqps://user:pass@host:port\n"
                f"Common fixes:\n"
                f"  - Change 'rabbit://' to 'amqp://'\n"
                f"  - Change 'rabbitmq://' to 'amqp://'\n"
                f"  - Add port ':5672' if missing"
            )
        except pika.exceptions.AMQPConnectionError as e:
            raise MessagingException(
                f"Failed to connect to RabbitMQ: {e}\n"
                f"Check:\n"
                f"  - RabbitMQ service is running: systemctl status rabbitmq-server\n"
                f"  - Host and port are correct\n"
                f"  - Credentials are valid\n"
                f"  - Firewall allows connection"
            )
        except Exception as e:
            raise MessagingException(
                f"Failed to connect to RabbitMQ: {e}\n"
                f"URL format: {self._safe_url(self.config._rabbitmq_url)}"
            )
    
    def _safe_url(self, url: str) -> str:
        """Return URL with password masked"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.password:
                netloc = parsed.netloc.replace(f":{parsed.password}@", ":****@")
                return f"{parsed.scheme}://{netloc}{parsed.path}"
        except:
            pass
        return url
    
    def start_consuming(self):
        """Start consuming messages"""
        if not self.connection:
            self.connect()
        
        self.consuming = True
        self.channel.basic_qos(prefetch_count=self.config.rabbitmq_prefetch)
        self.channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=self._on_request
        )
        
        LOG.info(f"Started consuming from {self.queue_name} (node: {self.node_id})")
        
        try:
            while self.consuming:
                self.connection.process_data_events(time_limit=1)
        except KeyboardInterrupt:
            LOG.info("Interrupted, stopping...")
        finally:
            self.stop()
    
    def _on_request(self, ch, method, props, body):
        """Handle incoming request"""
        try:
            request = json.loads(body)
            request_node = request.get('node_id')
            
            # Validate node_id
            if request_node != self.node_id:
                error_msg = (f"Node mismatch: request for node '{request_node}' "
                           f"received by node '{self.node_id}'")
                LOG.error(error_msg)
                
                response = {
                    'success': False,
                    'message': error_msg,
                    'server_node_id': self.node_id,
                    'request_node_id': request_node
                }
                
                if props.reply_to:
                    ch.basic_publish(
                        exchange='',
                        routing_key=props.reply_to,
                        properties=pika.BasicProperties(
                            correlation_id=props.correlation_id
                        ),
                        body=json.dumps(response)
                    )
                
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                return
            
            # Process request
            LOG.info(f"Processing {request.get('operation')} for job {request.get('job_id')}")
            
            response = self.handler(request)
            response['server_node_id'] = self.node_id
            
            if props.reply_to:
                ch.basic_publish(
                    exchange='',
                    routing_key=props.reply_to,
                    properties=pika.BasicProperties(
                        correlation_id=props.correlation_id
                    ),
                    body=json.dumps(response)
                )
            
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            LOG.error(f"Error handling request: {e}")
            
            if props.reply_to:
                error_response = {
                    'success': False,
                    'message': f'Server error: {str(e)}',
                    'server_node_id': self.node_id
                }
                try:
                    ch.basic_publish(
                        exchange='',
                        routing_key=props.reply_to,
                        properties=pika.BasicProperties(
                            correlation_id=props.correlation_id
                        ),
                        body=json.dumps(error_response)
                    )
                except:
                    pass
            
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    def stop(self):
        """Stop consuming"""
        self.consuming = False
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            LOG.info(f"Closed RabbitMQ connection (node: {self.node_id})")

