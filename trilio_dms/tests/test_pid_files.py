"""
Test PID file functionality for S3VaultFuseManager
"""

import os
import time
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock
from trilio_dms.s3vaultfuse_manager import S3VaultFuseManager


class TestPIDFiles(unittest.TestCase):
    """Test PID file tracking"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Use temporary directory for PID files
        self.temp_dir = tempfile.mkdtemp()
        self.manager = S3VaultFuseManager(pid_dir=self.temp_dir)
    
    def tearDown(self):
        """Clean up"""
        # Cleanup manager
        try:
            self.manager.cleanup_all(force=True)
        except:
            pass
        
        # Remove temp directory
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass
    
    def test_pid_directory_creation(self):
        """Test PID directory is created"""
        self.assertTrue(os.path.exists(self.temp_dir))
        self.assertTrue(os.path.isdir(self.temp_dir))
    
    def test_pid_file_path(self):
        """Test PID file path generation"""
        path = self.manager._get_pid_file_path('target-123')
        expected = os.path.join(self.temp_dir, 'target-123.pid')
        self.assertEqual(path, expected)
    
    def test_write_and_read_pid_file(self):
        """Test writing and reading PID files"""
        target_id = 'target-123'
        pid = 12345
        
        # Write PID file
        success = self.manager._write_pid_file(target_id, pid)
        self.assertTrue(success)
        
        # Check file exists
        pid_file = self.manager._get_pid_file_path(target_id)
        self.assertTrue(os.path.exists(pid_file))
        
        # Read PID file
        read_pid = self.manager._read_pid_file(target_id)
        self.assertEqual(read_pid, pid)
    
    def test_delete_pid_file(self):
        """Test deleting PID files"""
        target_id = 'target-123'
        pid = 12345
        
        # Write PID file
        self.manager._write_pid_file(target_id, pid)
        pid_file = self.manager._get_pid_file_path(target_id)
        self.assertTrue(os.path.exists(pid_file))
        
        # Delete PID file
        success = self.manager._delete_pid_file(target_id)
        self.assertTrue(success)
        self.assertFalse(os.path.exists(pid_file))
    
    def test_read_nonexistent_pid_file(self):
        """Test reading nonexistent PID file"""
        pid = self.manager._read_pid_file('nonexistent')
        self.assertIsNone(pid)
    
    def test_pid_file_with_invalid_content(self):
        """Test PID file with invalid content"""
        target_id = 'target-123'
        pid_file = self.manager._get_pid_file_path(target_id)
        
        # Write invalid content
        with open(pid_file, 'w') as f:
            f.write('not-a-number')
        
        # Should return None
        pid = self.manager._read_pid_file(target_id)
        self.assertIsNone(pid)
    
    @patch('trilio_dms.s3vaultfuse_manager.subprocess.Popen')
    @patch('trilio_dms.s3vaultfuse_manager.os.makedirs')
    def test_spawn_creates_pid_file(self, mock_makedirs, mock_popen):
        """Test that spawning creates PID file"""
        # Mock process
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Process is running
        mock_popen.return_value = mock_process
        
        target_id = 'target-123'
        mount_path = '/tmp/mount'
        env = {'TEST': 'value'}
        
        # Spawn process
        success = self.manager.spawn_s3vaultfuse(target_id, mount_path, env)
        self.assertTrue(success)
        
        # Check PID file was created
        pid_file = self.manager._get_pid_file_path(target_id)
        self.assertTrue(os.path.exists(pid_file))
        
        # Check PID file content
        with open(pid_file, 'r') as f:
            content = f.read().strip()
        self.assertEqual(content, '12345')
        
        # Check in-memory tracking
        self.assertIn(target_id, self.manager.processes)
        self.assertEqual(self.manager.processes[target_id]['pid'], 12345)
    
    def test_kill_removes_pid_file(self):
        """Test that killing removes PID file"""
        target_id = 'target-123'
        pid = os.getpid()  # Use current process for testing
        
        # Manually create entry
        self.manager._write_pid_file(target_id, pid)
        self.manager.processes[target_id] = {
            'pid': pid,
            'process': None,
            'target_id': target_id,
            'mount_path': '/tmp/test',
            'start_time': None,
            'env_keys': [],
            'status': 'running'
        }
        
        # Verify PID file exists
        pid_file = self.manager._get_pid_file_path(target_id)
        self.assertTrue(os.path.exists(pid_file))
        
        # Kill (will fail to kill current process, but should still cleanup)
        try:
            self.manager.kill_s3vaultfuse(target_id, force=True)
        except:
            pass
        
        # PID file should be deleted
        self.assertFalse(os.path.exists(pid_file))
    
    def test_load_existing_pids_on_startup(self):
        """Test loading existing PID files on startup"""
        # Create some PID files manually
        target_ids = ['target-1', 'target-2', 'target-3']
        current_pid = os.getpid()
        
        for target_id in target_ids:
            self.manager._write_pid_file(target_id, current_pid)
        
        # Create new manager (should load existing PIDs)
        new_manager = S3VaultFuseManager(pid_dir=self.temp_dir)
        
        # Should have loaded the processes
        self.assertGreater(len(new_manager.processes), 0)
        
        # At least one should be loaded (current process)
        loaded = [t for t in target_ids if t in new_manager.processes]
        self.assertGreater(len(loaded), 0)
    
    def test_cleanup_stale_pid_files(self):
        """Test cleanup of stale PID files"""
        # Create PID file with non-existent PID
        target_id = 'target-stale'
        fake_pid = 999999  # Unlikely to exist
        self.manager._write_pid_file(target_id, fake_pid)
        
        # Create new manager (should cleanup stale PID)
        new_manager = S3VaultFuseManager(pid_dir=self.temp_dir)
        
        # PID file should be deleted
        pid_file = new_manager._get_pid_file_path(target_id)
        self.assertFalse(os.path.exists(pid_file))
    
    def test_get_stats_includes_pid_files(self):
        """Test that stats include PID file count"""
        # Create some PID files
        for i in range(3):
            target_id = f'target-{i}'
            pid = 10000 + i
            self.manager._write_pid_file(target_id, pid)
        
        # Get stats
        stats = self.manager.get_stats()
        
        # Should include PID file count
        self.assertIn('pid_files_on_disk', stats)
        self.assertEqual(stats['pid_files_on_disk'], 3)
        self.assertEqual(stats['pid_directory'], self.temp_dir)
    
    def test_process_info_includes_pid_file(self):
        """Test that process info includes PID file information"""
        target_id = 'target-123'
        pid = os.getpid()
        
        # Create entry with PID file
        self.manager._write_pid_file(target_id, pid)
        self.manager.processes[target_id] = {
            'pid': pid,
            'process': None,
            'target_id': target_id,
            'mount_path': '/tmp/test',
            'start_time': None,
            'env_keys': [],
            'status': 'running'
        }
        
        # Get process info
        info = self.manager.get_process_info(target_id)
        
        # Should include PID file info
        self.assertIn('pid_file', info)
        self.assertIn('pid_file_exists', info)
        self.assertTrue(info['pid_file_exists'])
    
    def test_is_running_checks_pid_file(self):
        """Test that is_running checks PID file if not in memory"""
        target_id = 'target-123'
        current_pid = os.getpid()
        
        # Only create PID file, not in-memory entry
        self.manager._write_pid_file(target_id, current_pid)
        
        # Should find it from PID file
        is_running = self.manager.is_running(target_id)
        self.assertTrue(is_running)
        
        # Should now be loaded into memory
        self.assertIn(target_id, self.manager.processes)


class TestPIDFilePermissions(unittest.TestCase):
    """Test PID file permissions and security"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = S3VaultFuseManager(pid_dir=self.temp_dir)
    
    def tearDown(self):
        """Clean up"""
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass
    
    def test_pid_directory_permissions(self):
        """Test PID directory has correct permissions"""
        mode = os.stat(self.temp_dir).st_mode
        # Should be readable by all (0o755)
        self.assertTrue(mode & 0o444)  # Readable
    
    def test_pid_file_readable(self):
        """Test PID file is readable"""
        target_id = 'target-123'
        pid = 12345
        
        self.manager._write_pid_file(target_id, pid)
        pid_file = self.manager._get_pid_file_path(target_id)
        
        # Should be able to read
        with open(pid_file, 'r') as f:
            content = f.read()
        self.assertEqual(content.strip(), '12345')


if __name__ == '__main__':
    unittest.main()
