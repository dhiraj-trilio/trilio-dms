"""
Trilio DMS Server - Mount/Unmount Request Handler
Responsibilities:
- Listen to RabbitMQ for mount/unmount requests
- Execute mount/unmount operations using s3vaultfuse for S3
- Return status responses
- NO database access
"""

import json
import logging
import os
import subprocess
from typing import Dict, Any, Optional
import pika
import requests

from trilio_dms.config import DMSConfig
from trilio_dms.s3vaultfuse_manager import S3VaultFuseManager
from trilio_dms.exceptions import (
    DMSServerException, MountException, UnmountException,
    SecretFetchException
)
from trilio_dms.utils import (
    create_response, is_mounted, get_mount_path,
    ensure_directory, run_command, sanitize_mount_options
)

logging.basicConfig(
    level=DMSConfig.LOG_LEVEL,
    format=DMSConfig.LOG_FORMAT
)
logger = logging.getLogger(__name__)


class DMSServer:
    """DMS Server handles mount/unmount operations via RabbitMQ"""

    def __init__(self, rabbitmq_url: Optional[str] = None,
                 node_id: Optional[str] = None,
                 auth_url: Optional[str] = None,
                 mount_base_path: Optional[str] = None,
                 **kwargs):  # Accept extra keyword arguments
        """
        Initialize DMS Server

        Args:
            rabbitmq_url: RabbitMQ URL (uses config default if not provided)
            node_id: Node identifier (uses config default if not provided)
            auth_url: Keystone auth URL (uses config default if not provided)
            mount_base_path: Base path for mounts (uses config default if not provided)
            **kwargs: Additional config parameters (ignored)
        """
        self.rabbitmq_url = rabbitmq_url or DMSConfig.RABBITMQ_URL
        self.node_id = node_id or DMSConfig.NODE_ID
        self.auth_url = auth_url or DMSConfig.AUTH_URL
        self.mount_base_path = mount_base_path or DMSConfig.MOUNT_BASE_PATH

        # Log any extra parameters that were provided but not used
        if kwargs:
            logger.debug(f"Ignoring extra config parameters: {list(kwargs.keys())}")

        # Initialize s3vaultfuse manager
        self.s3vaultfuse_manager = S3VaultFuseManager()

        # Note: Mount base directory creation removed
        # S3 mounts will be created by s3vaultfuse itself
        # NFS mounts will be created on-demand during mount operation

        logger.info(f"Initialized DMS Server on node: {self.node_id}")
        logger.info(f"Mount base path: {self.mount_base_path}")

    def start(self):
        """Start listening to RabbitMQ queue"""
        logger.info(f"Starting DMS Server on node: {self.node_id}")

        try:
            connection = pika.BlockingConnection(
                pika.URLParameters(self.rabbitmq_url)
            )
            channel = connection.channel()

            # Declare queue for this node
            queue_name = f'dms.{self.node_id}'
            channel.queue_declare(queue=queue_name, durable=True)

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=queue_name,
                on_message_callback=self._handle_request
            )

            logger.info(f"Waiting for messages on queue: {queue_name}")
            channel.start_consuming()

        except KeyboardInterrupt:
            logger.info("Shutting down DMS Server...")
            self.s3vaultfuse_manager.cleanup_all()
            if connection and not connection.is_closed:
                connection.close()
        except Exception as e:
            logger.error(f"Failed to start DMS Server: {e}", exc_info=True)
            raise DMSServerException(f"Server startup failed: {e}")

    def _handle_request(self, ch, method, properties, body):
        """Handle incoming mount/unmount requests"""
        try:
            request = json.loads(body)
            action = request.get('action', 'unknown')
            target_id = request.get('backup_target', {}).get('id', 'unknown')

            logger.info(f"Received request: {action} for target {target_id}")

            if action == 'mount':
                response = self._handle_mount(request)
            elif action == 'unmount':
                response = self._handle_unmount(request)
            else:
                response = create_response(
                    'error',
                    f'Unknown action: {action}'
                )

            # Send response back
            if properties.reply_to:
                ch.basic_publish(
                    exchange='',
                    routing_key=properties.reply_to,
                    properties=pika.BasicProperties(
                        correlation_id=properties.correlation_id,
                        content_type='application/json'
                    ),
                    body=json.dumps(response)
                )
                logger.info(f"Sent response for {action} request: {response['status']}")

            ch.basic_ack(delivery_tag=method.delivery_tag)

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request: {e}")
            response = create_response('error', 'Invalid JSON format in request')
            self._send_error_response(ch, properties, response)
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger.error(f"Error handling request: {e}", exc_info=True)
            response = create_response('error', str(e))
            self._send_error_response(ch, properties, response)
            ch.basic_ack(delivery_tag=method.delivery_tag)

    def _send_error_response(self, ch, properties, response):
        """Send error response"""
        if properties.reply_to:
            try:
                ch.basic_publish(
                    exchange='',
                    routing_key=properties.reply_to,
                    properties=pika.BasicProperties(
                        correlation_id=properties.correlation_id,
                        content_type='application/json'
                    ),
                    body=json.dumps(response)
                )
            except Exception as e:
                logger.error(f"Failed to send error response: {e}")

    def _handle_mount(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle mount request"""
        try:
            backup_target = request['backup_target']
            target_type = backup_target['type']
            target_id = backup_target['id']

            # Get mount path from backup_target (required field from client)
            mount_path = backup_target.get('filesystem_export_mount_path')
            if not mount_path:
                return create_response(
                    'error',
                    'Missing filesystem_export_mount_path in backup_target'
                )

            if target_type == 's3':
                return self._mount_s3(request, mount_path)
            elif target_type == 'nfs':
                return self._mount_nfs(request, mount_path)
            else:
                return create_response(
                    'error',
                    f'Unsupported target type: {target_type}'
                )

        except KeyError as e:
            logger.error(f"Missing required field in request: {e}")
            return create_response('error', f'Missing required field: {e}')
        except Exception as e:
            logger.error(f"Mount failed: {e}", exc_info=True)
            return create_response('error', str(e))

    def _mount_s3(self, request: Dict[str, Any], mount_path: str) -> Dict[str, Any]:
        """Mount S3 target using s3vaultfuse"""
        try:
            backup_target = request['backup_target']
            keystone_token = request.get('keystone_token')
            secret_ref = backup_target.get('secret_ref')
            target_id = backup_target['id']

            # Fetch credentials from Barbican if secret_ref provided
            credentials = {}
            if secret_ref and keystone_token:
                credentials = self._fetch_secret(secret_ref, keystone_token)

            # Update credentials with mount path
            backup_target['filesystem_export_mount_path'] = mount_path

            # NOTE: Do NOT create mount directory for S3
            # s3vaultfuse will create it if needed

            # Check if already mounted
            if is_mounted(mount_path):
                logger.info(f"Target {target_id} already mounted at {mount_path}")
                return create_response(
                    'success',
                    success_msg=f'Already mounted at {mount_path}'
                )

            # Prepare environment for s3vaultfuse
            env = self.s3vaultfuse_manager.prepare_environment(backup_target, credentials)

            # Spawn s3vaultfuse process
            success = self.s3vaultfuse_manager.spawn_s3vaultfuse(target_id, mount_path, env)

            if not success:
                return create_response('error', 'Failed to spawn s3vaultfuse process')

            # Verify mount
            if not is_mounted(mount_path):
                return create_response('error', 'Mount verification failed')

            logger.info(f"S3 target {target_id} mounted at {mount_path}")

            return create_response(
                'success',
                success_msg=f'S3 target mounted successfully at {mount_path}'
            )

        except SecretFetchException as e:
            logger.error(f"Failed to fetch secret: {e}")
            return create_response('error', f'Failed to fetch credentials: {e}')
        except Exception as e:
            logger.error(f"S3 mount failed: {e}", exc_info=True)
            return create_response('error', f'S3 mount error: {e}')

    def _mount_nfs(self, request: Dict[str, Any], mount_path: str) -> Dict[str, Any]:
        """Mount NFS target"""
        try:
            backup_target = request['backup_target']
            export = backup_target.get('filesystem_export')
            mount_opts = backup_target.get('nfs_mount_opts', 'defaults')
            target_id = backup_target['id']

            if not export:
                return create_response('error', 'Missing filesystem_export for NFS mount')

            # Sanitize mount options
            mount_opts = sanitize_mount_options(mount_opts)

            # Create mount directory
            if not ensure_directory(mount_path):
                return create_response('error', f'Failed to create mount directory: {mount_path}')

            # Check if already mounted
            if is_mounted(mount_path):
                logger.info(f"Target {target_id} already mounted at {mount_path}")
                return create_response(
                    'success',
                    success_msg=f'Already mounted at {mount_path}'
                )

            # Build mount command
            # dhiraj added filter file in command here
            cmd = ['sudo', '/usr/bin/workloadmgr-rootwrap', '/etc/triliovault-wlm/rootwrap.conf', 'mount', '-t', 'nfs', '-o', mount_opts, export, mount_path]
            #cmd = ['mount', '-t', 'nfs', '-o', mount_opts, export, mount_path]

            # Execute mount
            returncode, stdout, stderr = run_command(cmd, timeout=60)

            if returncode != 0:
                return create_response('error', f'NFS mount failed: {stderr}')

            logger.info(f"NFS target {target_id} mounted at {mount_path}")

            return create_response(
                'success',
                success_msg=f'NFS target mounted successfully at {mount_path}'
            )

        except Exception as e:
            logger.error(f"NFS mount failed: {e}", exc_info=True)
            return create_response('error', f'NFS mount error: {e}')

    def _handle_unmount(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle unmount request"""
        try:
            backup_target = request['backup_target']
            target_id = backup_target['id']
            target_type = backup_target['type']

            # Get mount path from backup_target (required field from client)
            mount_path = backup_target.get('filesystem_export_mount_path')
            if not mount_path:
                return create_response(
                    'error',
                    'Missing filesystem_export_mount_path in backup_target'
                )

            # Check if mounted
            if not is_mounted(mount_path):
                logger.info(f"Target {target_id} not mounted at {mount_path}")

                # Still try to kill s3vaultfuse process if S3
                if target_type == 's3':
                    self.s3vaultfuse_manager.kill_s3vaultfuse(target_id)

                return create_response(
                    'success',
                    success_msg=f'Target not mounted at {mount_path}'
                )

            # For S3, kill s3vaultfuse process first
            if target_type == 's3':
                logger.info(f"Killing s3vaultfuse process for target {target_id}")
                if not self.s3vaultfuse_manager.kill_s3vaultfuse(target_id):
                    logger.warning(f"Failed to kill s3vaultfuse process for {target_id}")

            # Try regular unmount
            returncode, stdout, stderr = run_command(['umount', mount_path], timeout=30)

            if returncode != 0:
                # Try force unmount
                logger.warning(f"Regular unmount failed, trying force unmount: {stderr}")
                returncode, stdout, stderr = run_command(['umount', '-f', mount_path], timeout=30)

                if returncode != 0:
                    # Try lazy unmount as last resort
                    logger.warning(f"Force unmount failed, trying lazy unmount: {stderr}")
                    returncode, stdout, stderr = run_command(['umount', '-l', mount_path], timeout=30)

                    if returncode != 0:
                        return create_response('error', f'Unmount failed: {stderr}')

            # Remove mount directory
            try:
                os.rmdir(mount_path)
            except OSError as e:
                logger.warning(f"Failed to remove mount directory {mount_path}: {e}")

            logger.info(f"Target {target_id} unmounted from {mount_path}")

            return create_response(
                'success',
                success_msg=f'Target unmounted successfully from {mount_path}'
            )

        except Exception as e:
            logger.error(f"Unmount failed: {e}", exc_info=True)
            return create_response('error', f'Unmount error: {e}')

    def _fetch_secret(self, secret_ref: str, token: str) -> Dict[str, Any]:
        """
        Fetch secret from Barbican

        Args:
            secret_ref: Barbican secret reference URL
            token: Keystone authentication token

        Returns:
            Secret payload as dictionary

        Raises:
            SecretFetchException if fetch fails
        """
        try:
            headers = {
                'X-Auth-Token': token,
                'Accept': 'application/json'
            }

            # Fetch secret payload
            payload_url = f"{secret_ref}/payload"
            response = requests.get(payload_url, headers=headers, timeout=30)
            response.raise_for_status()

            # Parse response
            if response.headers.get('content-type') == 'application/json':
                return response.json()
            else:
                # Try to parse as JSON anyway
                return json.loads(response.text)

        except requests.exceptions.RequestException as e:
            raise SecretFetchException(f"Failed to fetch secret from Barbican: {e}")
        except json.JSONDecodeError as e:
            raise SecretFetchException(f"Failed to parse secret payload: {e}")


def main():
    """Main entry point for DMS Server"""
    try:
        # Validate configuration
        DMSConfig.validate_server_config()

        # Create and start server
        server_config = DMSConfig.get_server_config()
        server = DMSServer(**server_config)
        server.start()

    except Exception as e:
        logger.error(f"Failed to start DMS Server: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    main()
