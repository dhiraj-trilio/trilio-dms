"""DMS Server with node-specific queue consumption"""

import signal
import sys
import socket
from trilio_dms.config import DMSConfig
from trilio_dms.models import initialize_database
from trilio_dms.services.mount_service import MountService
from trilio_dms.services.reconciliation import ReconciliationService
from trilio_dms.messaging.rabbitmq import RabbitMQServer
from trilio_dms.utils.logger import get_logger

LOG = get_logger(__name__)


class DMSServer:
    """Main DMS Server - Node-Specific"""
    
    def __init__(self, config: DMSConfig):
        self.config = config
        self.shutdown_requested = False
        
        # Ensure node_id is set
        if not config.node_id or config.node_id == 'localhost':
            config.node_id = socket.gethostname()
            LOG.info(f"Node ID not configured, using hostname: {config.node_id}")
        
        # Initialize database
        initialize_database(config)
        
        # Initialize services
        self.mount_service = MountService(config)
        self.reconciliation_service = ReconciliationService(
            config, self.mount_service
        )
        
        # Initialize messaging (node-specific queue)
        self.mq_server = RabbitMQServer(config, self._handle_request)
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        LOG.info(f"Received signal {signum}, initiating shutdown...")
        self.shutdown_requested = True
        self.mq_server.stop()
    
    def _handle_request(self, request: dict) -> dict:
        """Handle incoming requests (already validated by RabbitMQServer)"""
        operation = request.get('operation')
        
        if operation == 'mount':
            return self.mount_service.mount(
                job_id=request.get('job_id'),
                target_id=request.get('target_id'),
                keystone_token=request.get('token')
            )
        elif operation == 'unmount':
            return self.mount_service.unmount(
                job_id=request.get('job_id'),
                target_id=request.get('target_id')
            )
        else:
            return {
                'success': False,
                'message': f'Unknown operation: {operation}'
            }
    
    def start(self):
        """Start the server"""
        LOG.info("="*80)
        LOG.info(f"Starting Trilio DMS Server")
        LOG.info("="*80)
        LOG.info(f"Node ID:       {self.config.node_id}")
        LOG.info(f"Queue:         {self.config.rabbitmq_queue}_{self.config.node_id}")
        LOG.info(f"Database:      {self.config.db_url}")
        LOG.info(f"RabbitMQ:      {self.config.rabbitmq_url}")
        LOG.info("="*80)
        
        # Reconcile on startup
        LOG.info("Running startup reconciliation...")
        self.reconciliation_service.reconcile_on_startup()
        
        # Start consuming
        LOG.info("Starting message consumer...")
        self.mq_server.start_consuming()
        
        LOG.info("DMS server stopped")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Trilio Dynamic Mount Service')
    parser.add_argument('--config', help='Configuration file')
    parser.add_argument('--db-url', help='Database URL')
    parser.add_argument('--rabbitmq-url', help='RabbitMQ URL')
    parser.add_argument('--auth-url', help='Keystone auth URL')
    parser.add_argument('--node-id', help='Node ID (defaults to hostname)')
    parser.add_argument('--log-level', help='Log level')
    
    args = parser.parse_args()
    
    # Load configuration
    if args.config:
        config = DMSConfig.from_file(args.config)
    else:
        config = DMSConfig()
    
    # Override with command line args
    if args.db_url:
        config.db_url = args.db_url
    if args.rabbitmq_url:
        config.rabbitmq_url = args.rabbitmq_url
    if args.auth_url:
        config.auth_url = args.auth_url
    if args.node_id:
        config.node_id = args.node_id
    if args.log_level:
        config.log_level = args.log_level

    # Start server
    server = DMSServer(config)
    server.start()


if __name__ == '__main__':
    main()
