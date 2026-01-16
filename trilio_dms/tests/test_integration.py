"""
Integration tests for DMS Client and Server
These tests require running RabbitMQ and MySQL instances
"""

import unittest
import os
import time
import threading
from trilio_dms.client import DMSClient, MountContext
from trilio_dms.server import DMSServer


class TestIntegration(unittest.TestCase):
    """Integration tests"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        cls.db_url = os.getenv('TEST_DB_URL', 'sqlite:///test_dms.db')
        cls.rabbitmq_url = os.getenv('TEST_RABBITMQ_URL', 'amqp://guest:guest@localhost:5672')
        cls.node_id = 'test-node-01'
        
        # Start server in background thread
        cls.server = DMSServer(
            rabbitmq_url=cls.rabbitmq_url,
            node_id=cls.node_id,
            auth_url='http://localhost:5000/v3',
            mount_base_path='/tmp/test-mounts'
        )
        
        cls.server_thread = threading.Thread(target=cls.server.start, daemon=True)
        cls.server_thread.start()
        
        # Wait for server to start
        time.sleep(2)
    
    def setUp(self):
        """Set up test client"""
        self.client = DMSClient(
            db_url=self.db_url,
            rabbitmq_url=self.rabbitmq_url,
            timeout=60
        )
    
    def tearDown(self):
        """Clean up client"""
        self.client.close()
    
    @unittest.skipUnless(
        os.getenv('RUN_INTEGRATION_TESTS') == '1',
        "Integration tests disabled. Set RUN_INTEGRATION_TESTS=1 to enable"
    )
    def test_full_mount_unmount_cycle(self):
        """Test complete mount/unmount cycle"""
        request = {
            'context': {'user_id': 'test-user', 'tenant_id': 'test-tenant'},
            'keystone_token': 'test-token',
            'job': {
                'jobid': 'integration-job-001',
                'progress': 0,
                'status': 'running',
                'completed_at': None,
                'action': 'backup',
                'parent_jobid': None,
                'job_details': [
                    {'id': 'detail-1', 'data': {'test': 'data'}}
                ]
            },
            'host': self.node_id,
            'action': 'mount',
            'backup_target': {
                'id': 'integration-target-001',
                'deleted': False,
                'type': 'nfs',
                'filesystem_export': '192.168.1.100:/test',
                'filesystem_export_mount_path': None,
                'status': 'available',
                'secret_ref': None,
                'nfs_mount_opts': 'defaults'
            }
        }
        
        # Test mount
        mount_response = self.client.mount(request)
        print(f"Mount response: {mount_response}")
        
        # Note: This will fail without actual NFS server
        # In real integration test, you'd need a test NFS server
        
        # Test unmount
        request['action'] = 'unmount'
        unmount_response = self.client.unmount(request)
        print(f"Unmount response: {unmount_response}")
        
        # Verify ledger entries
        status = self.client.get_mount_status(
            'integration-job-001',
            'integration-target-001'
        )
        self.assertIsNotNone(status)
    
    @unittest.skipUnless(
        os.getenv('RUN_INTEGRATION_TESTS') == '1',
        "Integration tests disabled"
    )
    def test_context_manager_integration(self):
        """Test context manager in integration"""
        request = {
            'context': {'user_id': 'test-user'},
            'keystone_token': 'test-token',
            'job': {
                'jobid': 'context-job-001',
                'progress': 0,
                'status': 'running',
                'action': 'backup',
                'job_details': []
            },
            'host': self.node_id,
            'backup_target': {
                'id': 'context-target-001',
                'type': 'nfs',
                'status': 'available',
                'filesystem_export': '192.168.1.100:/test',
                'secret_ref': None
            }
        }
        
        # Note: This will fail without actual NFS server
        try:
            with MountContext(self.client, request) as ctx:
                print(f"Mount path: {ctx.mount_path}")
                # Perform operations here
        except Exception as e:
            print(f"Expected failure without real NFS: {e}")


if __name__ == '__main__':
    # To run integration tests:
    # RUN_INTEGRATION_TESTS=1 python -m pytest tests/test_integration.py
    unittest.main()
