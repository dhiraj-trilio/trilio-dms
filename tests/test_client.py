"""
Unit tests for DMS Client
"""

import unittest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from trilio_dms.client import DMSClient, MountContext
from trilio_dms.models import BackupTargetMountLedger
from trilio_dms.exceptions import DMSClientException


class TestDMSClient(unittest.TestCase):
    """Test cases for DMSClient"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.db_url = 'sqlite:///:memory:'
        self.rabbitmq_url = 'amqp://guest:guest@localhost:5672'
        
        self.sample_request = {
            'context': {'user_id': 'user123', 'tenant_id': 'tenant123'},
            'keystone_token': 'test-token',
            'job': {
                'jobid': 'job-123',
                'progress': 0,
                'status': 'running',
                'completed_at': None,
                'action': 'backup',
                'parent_jobid': None,
                'job_details': [{'id': 'detail-1', 'data': {}}]
            },
            'host': 'compute-01',
            'action': 'mount',
            'backup_target': {
                'id': 'target-123',
                'deleted': False,
                'type': 's3',
                'filesystem_export': None,
                'filesystem_export_mount_path': None,
                'status': 'available',
                'secret_ref': 'http://barbican:9311/v1/secrets/abc',
                'nfs_mount_opts': None
            }
        }
    
    @patch('trilio_dms.client.pika.BlockingConnection')
    def test_client_initialization(self, mock_connection):
        """Test client initialization"""
        client = DMSClient(db_url=self.db_url, rabbitmq_url=self.rabbitmq_url)
        
        self.assertIsNotNone(client.engine)
        self.assertIsNotNone(client.SessionLocal)
        mock_connection.assert_called_once()
    
    @patch('trilio_dms.client.pika.BlockingConnection')
    def test_mount_request(self, mock_connection):
        """Test mount request"""
        # Setup mock
        mock_channel = MagicMock()
        mock_connection.return_value.channel.return_value = mock_channel
        
        client = DMSClient(db_url=self.db_url, rabbitmq_url=self.rabbitmq_url)
        
        # Mock response
        client.response = {
            'status': 'success',
            'error_msg': None,
            'success_msg': 'Mount successful'
        }
        
        response = client.mount(self.sample_request)
        
        self.assertEqual(response['status'], 'success')
        self.assertIsNone(response['error_msg'])
        self.assertIsNotNone(response['success_msg'])
    
    @patch('trilio_dms.client.pika.BlockingConnection')
    def test_unmount_request(self, mock_connection):
        """Test unmount request"""
        mock_channel = MagicMock()
        mock_connection.return_value.channel.return_value = mock_channel
        
        client = DMSClient(db_url=self.db_url, rabbitmq_url=self.rabbitmq_url)
        
        # Mock response
        client.response = {
            'status': 'success',
            'error_msg': None,
            'success_msg': 'Unmount successful'
        }
        
        response = client.unmount(self.sample_request)
        
        self.assertEqual(response['status'], 'success')
    
    @patch('trilio_dms.client.pika.BlockingConnection')
    def test_get_mount_status(self, mock_connection):
        """Test get mount status"""
        client = DMSClient(db_url=self.db_url, rabbitmq_url=self.rabbitmq_url)
        
        # Create a ledger entry
        session = client.SessionLocal()
        ledger = BackupTargetMountLedger(
            id='ledger-123',
            backup_target_id='target-123',
            job_id='job-123',
            host='compute-01',
            action='mount',
            status='success',
            mount_path='/mnt/target-123'
        )
        session.add(ledger)
        session.commit()
        session.close()
        
        # Query status
        status = client.get_mount_status('job-123', 'target-123')
        
        self.assertIsNotNone(status)
        self.assertEqual(status.id, 'ledger-123')
        self.assertEqual(status.status, 'success')
    
    @patch('trilio_dms.client.pika.BlockingConnection')
    def test_cleanup_stale_entries(self, mock_connection):
        """Test cleanup of stale entries"""
        client = DMSClient(db_url=self.db_url, rabbitmq_url=self.rabbitmq_url)
        
        # Create a stale entry
        session = client.SessionLocal()
        ledger = BackupTargetMountLedger(
            id='stale-123',
            backup_target_id='target-123',
            job_id='job-123',
            host='compute-01',
            action='mount',
            status='pending',
            created_at=datetime(2020, 1, 1)
        )
        session.add(ledger)
        session.commit()
        session.close()
        
        # Cleanup
        count = client.cleanup_stale_entries(hours=1)
        
        self.assertEqual(count, 1)
        
        # Verify it was updated
        session = client.SessionLocal()
        updated = session.query(BackupTargetMountLedger).filter_by(id='stale-123').first()
        self.assertEqual(updated.status, 'error')
        session.close()


class TestMountContext(unittest.TestCase):
    """Test cases for MountContext"""
    
    @patch('trilio_dms.client.pika.BlockingConnection')
    def test_context_manager_success(self, mock_connection):
        """Test context manager with successful mount/unmount"""
        client = DMSClient(
            db_url='sqlite:///:memory:',
            rabbitmq_url='amqp://guest:guest@localhost:5672'
        )
        
        request = {
            'context': {},
            'keystone_token': 'test-token',
            'job': {
                'jobid': 'job-123',
                'progress': 0,
                'status': 'running',
                'action': 'backup',
                'job_details': []
            },
            'host': 'compute-01',
            'action': 'mount',
            'backup_target': {
                'id': 'target-123',
                'type': 's3',
                'status': 'available',
                'secret_ref': 'http://test'
            }
        }
        
        # Mock responses
        client.response = {
            'status': 'success',
            'error_msg': None,
            'success_msg': 'Mount successful'
        }
        
        with patch.object(client, 'mount', return_value=client.response):
            with patch.object(client, 'unmount', return_value=client.response):
                with MountContext(client, request) as ctx:
                    self.assertIsNotNone(ctx.mount_path)
                    self.assertIn('target-123', ctx.mount_path)
    
    @patch('trilio_dms.client.pika.BlockingConnection')
    def test_context_manager_mount_failure(self, mock_connection):
        """Test context manager with mount failure"""
        client = DMSClient(
            db_url='sqlite:///:memory:',
            rabbitmq_url='amqp://guest:guest@localhost:5672'
        )
        
        request = {
            'context': {},
            'keystone_token': 'test-token',
            'job': {
                'jobid': 'job-123',
                'progress': 0,
                'status': 'running',
                'action': 'backup',
                'job_details': []
            },
            'host': 'compute-01',
            'action': 'mount',
            'backup_target': {
                'id': 'target-123',
                'type': 's3',
                'status': 'available',
                'secret_ref': 'http://test'
            }
        }
        
        # Mock mount failure
        client.response = {
            'status': 'error',
            'error_msg': 'Mount failed',
            'success_msg': None
        }
        
        with patch.object(client, 'mount', return_value=client.response):
            with self.assertRaises(DMSClientException):
                with MountContext(client, request):
                    pass


if __name__ == '__main__':
    unittest.main()
