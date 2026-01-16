"""
Unit tests for DMS Server
"""

import unittest
import json
from unittest.mock import Mock, patch, MagicMock, mock_open
from trilio_dms.server import DMSServer
from trilio_dms.utils import create_response


class TestDMSServer(unittest.TestCase):
    """Test cases for DMSServer"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.rabbitmq_url = 'amqp://guest:guest@localhost:5672'
        self.node_id = 'test-node'
        self.auth_url = 'http://keystone:5000/v3'
        self.mount_base = '/tmp/test-mounts'
        
        self.sample_mount_request = {
            'context': {'user_id': 'user123'},
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
                'secret_ref': 'http://barbican:9311/v1/secrets/abc'
            }
        }
    
    @patch('trilio_dms.server.ensure_directory')
    def test_server_initialization(self, mock_ensure_dir):
        """Test server initialization"""
        mock_ensure_dir.return_value = True
        
        server = DMSServer(
            rabbitmq_url=self.rabbitmq_url,
            node_id=self.node_id,
            auth_url=self.auth_url,
            mount_base_path=self.mount_base
        )
        
        self.assertEqual(server.node_id, self.node_id)
        self.assertEqual(server.mount_base_path, self.mount_base)
        mock_ensure_dir.assert_called_once()
    
    @patch('trilio_dms.server.ensure_directory')
    @patch('trilio_dms.server.run_command')
    @patch('trilio_dms.server.is_mounted')
    @patch('trilio_dms.server.DMSServer._fetch_secret')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.chmod')
    def test_mount_s3_success(self, mock_chmod, mock_file, mock_fetch, 
                              mock_is_mounted, mock_run_cmd, mock_ensure_dir):
        """Test successful S3 mount"""
        mock_ensure_dir.return_value = True
        mock_is_mounted.return_value = False
        mock_fetch.return_value = {
            'aws_access_key_id': 'test-key',
            'aws_secret_access_key': 'test-secret',
            'bucket': 'test-bucket'
        }
        mock_run_cmd.return_value = (0, '', '')  # Success
        
        server = DMSServer(
            rabbitmq_url=self.rabbitmq_url,
            node_id=self.node_id,
            mount_base_path=self.mount_base
        )
        
        response = server._handle_mount(self.sample_mount_request)
        
        self.assertEqual(response['status'], 'success')
        self.assertIsNone(response['error_msg'])
        self.assertIsNotNone(response['success_msg'])
    
    @patch('trilio_dms.server.ensure_directory')
    @patch('trilio_dms.server.is_mounted')
    def test_mount_already_mounted(self, mock_is_mounted, mock_ensure_dir):
        """Test mount when already mounted"""
        mock_ensure_dir.return_value = True
        mock_is_mounted.return_value = True
        
        server = DMSServer(
            rabbitmq_url=self.rabbitmq_url,
            node_id=self.node_id,
            mount_base_path=self.mount_base
        )
        
        response = server._handle_mount(self.sample_mount_request)
        
        self.assertEqual(response['status'], 'success')
        self.assertIn('Already mounted', response['success_msg'])
    
    @patch('trilio_dms.server.ensure_directory')
    @patch('trilio_dms.server.run_command')
    @patch('trilio_dms.server.is_mounted')
    def test_mount_nfs_success(self, mock_is_mounted, mock_run_cmd, mock_ensure_dir):
        """Test successful NFS mount"""
        mock_ensure_dir.return_value = True
        mock_is_mounted.return_value = False
        mock_run_cmd.return_value = (0, '', '')
        
        nfs_request = self.sample_mount_request.copy()
        nfs_request['backup_target']['type'] = 'nfs'
        nfs_request['backup_target']['filesystem_export'] = '192.168.1.100:/export'
        nfs_request['backup_target']['nfs_mount_opts'] = 'rw,sync'
        
        server = DMSServer(
            rabbitmq_url=self.rabbitmq_url,
            node_id=self.node_id,
            mount_base_path=self.mount_base
        )
        
        response = server._handle_mount(nfs_request)
        
        self.assertEqual(response['status'], 'success')
        mock_run_cmd.assert_called_once()
    
    @patch('trilio_dms.server.ensure_directory')
    @patch('trilio_dms.server.run_command')
    @patch('trilio_dms.server.is_mounted')
    @patch('os.rmdir')
    def test_unmount_success(self, mock_rmdir, mock_is_mounted, 
                            mock_run_cmd, mock_ensure_dir):
        """Test successful unmount"""
        mock_ensure_dir.return_value = True
        mock_is_mounted.return_value = True
        mock_run_cmd.return_value = (0, '', '')
        
        server = DMSServer(
            rabbitmq_url=self.rabbitmq_url,
            node_id=self.node_id,
            mount_base_path=self.mount_base
        )
        
        unmount_request = self.sample_mount_request.copy()
        unmount_request['action'] = 'unmount'
        
        response = server._handle_unmount(unmount_request)
        
        self.assertEqual(response['status'], 'success')
        mock_run_cmd.assert_called()
    
    @patch('trilio_dms.server.ensure_directory')
    @patch('trilio_dms.server.is_mounted')
    def test_unmount_not_mounted(self, mock_is_mounted, mock_ensure_dir):
        """Test unmount when not mounted"""
        mock_ensure_dir.return_value = True
        mock_is_mounted.return_value = False
        
        server = DMSServer(
            rabbitmq_url=self.rabbitmq_url,
            node_id=self.node_id,
            mount_base_path=self.mount_base
        )
        
        unmount_request = self.sample_mount_request.copy()
        unmount_request['action'] = 'unmount'
        
        response = server._handle_unmount(unmount_request)
        
        self.assertEqual(response['status'], 'success')
        self.assertIn('not mounted', response['success_msg'])
    
    @patch('trilio_dms.server.ensure_directory')
    @patch('trilio_dms.server.requests.get')
    def test_fetch_secret_success(self, mock_get, mock_ensure_dir):
        """Test successful secret fetch from Barbican"""
        mock_ensure_dir.return_value = True
        mock_response = Mock()
        mock_response.json.return_value = {
            'aws_access_key_id': 'test-key',
            'aws_secret_access_key': 'test-secret'
        }
        mock_response.headers = {'content-type': 'application/json'}
        mock_get.return_value = mock_response
        
        server = DMSServer(
            rabbitmq_url=self.rabbitmq_url,
            node_id=self.node_id,
            mount_base_path=self.mount_base
        )
        
        secret = server._fetch_secret('http://barbican/secret', 'token')
        
        self.assertIn('aws_access_key_id', secret)
        self.assertEqual(secret['aws_access_key_id'], 'test-key')
    
    @patch('trilio_dms.server.ensure_directory')
    def test_invalid_action(self, mock_ensure_dir):
        """Test handling of invalid action"""
        mock_ensure_dir.return_value = True
        
        server = DMSServer(
            rabbitmq_url=self.rabbitmq_url,
            node_id=self.node_id,
            mount_base_path=self.mount_base
        )
        
        invalid_request = self.sample_mount_request.copy()
        invalid_request['action'] = 'invalid'
        
        # Simulate request handling
        ch = Mock()
        method = Mock()
        properties = Mock()
        properties.reply_to = 'callback_queue'
        properties.correlation_id = 'test-id'
        
        body = json.dumps(invalid_request)
        
        server._handle_request(ch, method, properties, body.encode())
        
        # Verify error response was sent
        ch.basic_publish.assert_called()


class TestServerUtils(unittest.TestCase):
    """Test utility functions used by server"""
    
    def test_create_response(self):
        """Test response creation"""
        response = create_response('success', success_msg='Operation successful')
        
        self.assertEqual(response['status'], 'success')
        self.assertIsNone(response['error_msg'])
        self.assertEqual(response['success_msg'], 'Operation successful')
    
    def test_create_error_response(self):
        """Test error response creation"""
        response = create_response('error', error_msg='Operation failed')
        
        self.assertEqual(response['status'], 'error')
        self.assertEqual(response['error_msg'], 'Operation failed')
        self.assertIsNone(response['success_msg'])


if __name__ == '__main__':
    unittest.main()
