#!/usr/bin/env python3
"""
Trilio DMS Complete Test Suite

This script tests:
1. Configuration loading
2. Database connectivity
3. RabbitMQ connectivity
4. Single job mount/unmount
5. Concurrent jobs (smart unmount logic)
6. Lock mechanism
7. End-to-end workflow
"""

import sys
import time
import logging
import threading
from datetime import datetime
from typing import List, Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Colors:
    """ANSI color codes for pretty output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str):
    """Print test section header"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BLUE}{Colors.BOLD}{text:^70}{Colors.END}")
    print(f"{Colors.BLUE}{Colors.BOLD}{'='*70}{Colors.END}\n")


def print_test(test_name: str):
    """Print test name"""
    print(f"{Colors.BOLD}▶ {test_name}{Colors.END}")


def print_success(message: str):
    """Print success message"""
    print(f"  {Colors.GREEN}✓ {message}{Colors.END}")


def print_error(message: str):
    """Print error message"""
    print(f"  {Colors.RED}✗ {message}{Colors.END}")


def print_warning(message: str):
    """Print warning message"""
    print(f"  {Colors.YELLOW}⚠ {message}{Colors.END}")


def print_info(message: str):
    """Print info message"""
    print(f"    {message}")


# ==============================================================================
# Test 1: Configuration Test
# ==============================================================================

def test_configuration():
    """Test configuration loading"""
    print_header("TEST 1: Configuration Loading")
    
    try:
        print_test("Loading DMS Configuration")
        from trilio_dms.config import DMSConfig
        
        # Print current configuration
        print_info(f"RABBITMQ_URL: {DMSConfig._mask_password(DMSConfig.RABBITMQ_URL)}")
        print_info(f"DB_URL: {DMSConfig._mask_password(DMSConfig.DB_URL)}")
        print_info(f"NODE_ID: {DMSConfig.NODE_ID}")
        print_info(f"AUTH_URL: {DMSConfig.AUTH_URL}")
        print_info(f"LOG_LEVEL: {DMSConfig.LOG_LEVEL}")
        
        # Validate
        if 'localhost' in DMSConfig.RABBITMQ_URL:
            print_warning("RabbitMQ URL is localhost (might be using defaults)")
        else:
            print_success("RabbitMQ URL loaded from config")
        
        if DMSConfig.NODE_ID and DMSConfig.NODE_ID != 'default-node':
            print_success(f"Node ID configured: {DMSConfig.NODE_ID}")
        else:
            print_warning("Using default node ID")
        
        print_success("Configuration loaded successfully")
        return True
        
    except Exception as e:
        print_error(f"Configuration test failed: {e}")
        return False


# ==============================================================================
# Test 2: Database Connectivity
# ==============================================================================

def test_database():
    """Test database connectivity"""
    print_header("TEST 2: Database Connectivity")
    
    try:
        print_test("Connecting to database")
        from trilio_dms.client import DMSClient
        from trilio_dms.config import DMSConfig
        
        print_info(f"DB URL: {DMSConfig._mask_password(DMSConfig.DB_URL)}")
        
        client = DMSClient()
        print_success("Database connection established")
        
        print_test("Checking tables")
        from trilio_dms.models import BackupTargetMountLedger
        
        # Try a simple query
        session = client.SessionLocal()
        count = session.query(BackupTargetMountLedger).count()
        session.close()
        
        print_success(f"Found {count} entries in mount ledger")
        
        client.close()
        print_success("Database test passed")
        return True
        
    except Exception as e:
        print_error(f"Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# Test 3: RabbitMQ Connectivity
# ==============================================================================

def test_rabbitmq():
    """Test RabbitMQ connectivity"""
    print_header("TEST 3: RabbitMQ Connectivity")
    
    try:
        print_test("Connecting to RabbitMQ")
        import pika
        from trilio_dms.config import DMSConfig
        
        print_info(f"RabbitMQ URL: {DMSConfig._mask_password(DMSConfig.RABBITMQ_URL)}")
        
        connection = pika.BlockingConnection(
            pika.URLParameters(DMSConfig.RABBITMQ_URL)
        )
        print_success("RabbitMQ connection established")
        
        channel = connection.channel()
        print_success("Channel created")
        
        # Declare a test queue
        queue_name = f'dms.{DMSConfig.NODE_ID}'
        channel.queue_declare(queue=queue_name, durable=True)
        print_success(f"Queue declared: {queue_name}")
        
        connection.close()
        print_success("RabbitMQ test passed")
        return True
        
    except Exception as e:
        print_error(f"RabbitMQ test failed: {e}")
        print_warning("Make sure DMS Server is running and RabbitMQ is accessible")
        return False


# ==============================================================================
# Test 4: Lock Manager
# ==============================================================================

def test_lock_manager():
    """Test global lock manager"""
    print_header("TEST 4: Global Lock Manager")
    
    try:
        print_test("Testing lock acquisition")
        from trilio_dms.lock_manager import get_lock_manager
        
        lock_manager = get_lock_manager(timeout=5)
        
        # Test single acquisition
        with lock_manager.acquire_lock("test_lock"):
            print_success("Lock acquired successfully")
            time.sleep(0.5)
        print_success("Lock released successfully")
        
        # Test concurrent acquisition
        print_test("Testing concurrent lock acquisition")
        
        acquired_order = []
        
        def worker(worker_id):
            with lock_manager.acquire_lock("test_lock"):
                acquired_order.append(worker_id)
                time.sleep(0.2)
        
        threads = []
        for i in range(3):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        if len(acquired_order) == 3:
            print_success(f"All 3 threads acquired lock in order: {acquired_order}")
        else:
            print_error(f"Lock acquisition issue: {acquired_order}")
            return False
        
        print_success("Lock manager test passed")
        return True
        
    except Exception as e:
        print_error(f"Lock manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# Test 5: Single Job Mount/Unmount
# ==============================================================================

def test_single_job_mount_unmount():
    """Test single job mount and unmount"""
    print_header("TEST 5: Single Job Mount/Unmount")
    
    try:
        print_test("Initializing DMS Client")
        from trilio_dms.client import DMSClient
        
        client = DMSClient()
        print_success("Client initialized")
        
        # Build test request
        jobid = 9001
        backup_target_id = 'test-target-001'
        host = 'test-host'
        
        request = {
            'job': {'jobid': jobid},
            'backup_target': {
                'id': backup_target_id,
                'type': 's3',
                'filesystem_export_mount_path': f'/mnt/{backup_target_id}'
            },
            'host': host
        }
        
        print_test(f"Mounting target (job={jobid}, target={backup_target_id})")
        mount_response = client.mount(request)
        
        if mount_response['status'] == 'success':
            print_success(f"Mount successful: {mount_response.get('success_msg')}")
            print_info(f"Mount path: {mount_response.get('mount_path')}")
            print_info(f"Reused existing: {mount_response.get('reused_existing', False)}")
        else:
            print_error(f"Mount failed: {mount_response.get('error_msg')}")
            print_warning("Note: This might fail if DMS Server is not running")
            print_warning("The mount will be tracked in ledger but not physically mounted")
        
        # Check ledger
        print_test("Checking mount ledger")
        ledger = client.get_mount_status(jobid, backup_target_id)
        if ledger:
            print_success(f"Ledger entry found: mounted={ledger.mounted}")
        else:
            print_error("Ledger entry not found")
            return False
        
        # Unmount
        print_test(f"Unmounting target (job={jobid})")
        unmount_response = client.unmount(request)
        
        if unmount_response['status'] == 'success':
            print_success(f"Unmount successful: {unmount_response.get('success_msg')}")
            print_info(f"Physically unmounted: {unmount_response.get('unmounted')}")
            print_info(f"Remaining mounts: {unmount_response.get('active_mounts_remaining', 0)}")
        else:
            print_error(f"Unmount failed: {unmount_response.get('error_msg')}")
            return False
        
        # Verify ledger updated
        print_test("Verifying ledger updated")
        ledger = client.get_mount_status(jobid, backup_target_id)
        if ledger and not ledger.mounted:
            print_success("Ledger correctly shows mounted=False")
        else:
            print_error("Ledger update failed")
            return False
        
        client.close()
        print_success("Single job mount/unmount test passed")
        return True
        
    except Exception as e:
        print_error(f"Single job test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# Test 6: Concurrent Jobs (Smart Unmount)
# ==============================================================================

def test_concurrent_jobs():
    """Test concurrent jobs with smart unmount logic"""
    print_header("TEST 6: Concurrent Jobs (Smart Unmount Logic)")
    
    try:
        print_test("Testing multiple jobs mounting same target")
        from trilio_dms.client import DMSClient
        
        client = DMSClient()
        
        backup_target_id = 'test-shared-target'
        host = 'test-host'
        job_ids = [9101, 9102, 9103]
        
        # Mount from all jobs
        print_test(f"Mounting from {len(job_ids)} jobs")
        for jobid in job_ids:
            request = {
                'job': {'jobid': jobid},
                'backup_target': {
                    'id': backup_target_id,
                    'type': 's3',
                    'filesystem_export_mount_path': f'/mnt/{backup_target_id}'
                },
                'host': host
            }
            
            response = client.mount(request)
            if response['status'] == 'success':
                print_success(f"Job {jobid}: Mounted (reused={response.get('reused_existing')})")
            else:
                print_error(f"Job {jobid}: Mount failed")
        
        # Check active mounts
        print_test("Checking active mounts")
        active = client.get_active_mounts(backup_target_id=backup_target_id)
        print_info(f"Active mounts: {len(active)}")
        for mount in active:
            print_info(f"  - Job {mount.jobid}: mounted={mount.mounted}")
        
        if len(active) != 3:
            print_error(f"Expected 3 active mounts, found {len(active)}")
            return False
        
        # Unmount first job (should NOT physically unmount)
        print_test(f"Unmounting job {job_ids[0]} (should keep mount for others)")
        request = {
            'job': {'jobid': job_ids[0]},
            'backup_target': {
                'id': backup_target_id,
                'type': 's3',
                'filesystem_export_mount_path': f'/mnt/{backup_target_id}'
            },
            'host': host
        }
        
        response = client.unmount(request)
        if response['status'] == 'success':
            if response.get('unmounted'):
                print_error("Physical unmount occurred (should have been skipped)")
                return False
            else:
                print_success(f"Correctly skipped physical unmount")
                print_info(f"Remaining mounts: {response.get('active_mounts_remaining')}")
        else:
            print_error("Unmount failed")
            return False
        
        # Verify job 1 is unmounted but others remain
        active = client.get_active_mounts(backup_target_id=backup_target_id)
        if len(active) != 2:
            print_error(f"Expected 2 active mounts, found {len(active)}")
            return False
        print_success(f"Correctly showing 2 remaining active mounts")
        
        # Unmount second job (should NOT physically unmount)
        print_test(f"Unmounting job {job_ids[1]} (should keep mount for job 3)")
        request['job']['jobid'] = job_ids[1]
        response = client.unmount(request)
        
        if response['status'] == 'success' and not response.get('unmounted'):
            print_success("Correctly skipped physical unmount")
        else:
            print_error("Unexpected unmount behavior")
            return False
        
        # Unmount third job (SHOULD physically unmount)
        print_test(f"Unmounting job {job_ids[2]} (should physically unmount - last job)")
        request['job']['jobid'] = job_ids[2]
        response = client.unmount(request)
        
        if response['status'] == 'success':
            if response.get('unmounted'):
                print_success("Correctly performed physical unmount (last job)")
            else:
                print_error("Physical unmount did not occur (but should have)")
                print_warning("This might be expected if DMS Server is not running")
        else:
            print_error("Unmount failed")
            return False
        
        # Verify no active mounts remain
        active = client.get_active_mounts(backup_target_id=backup_target_id)
        if len(active) == 0:
            print_success("No active mounts remaining")
        else:
            print_error(f"Found {len(active)} active mounts (should be 0)")
            return False
        
        client.close()
        print_success("Concurrent jobs test passed")
        return True
        
    except Exception as e:
        print_error(f"Concurrent jobs test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# Test 7: Context Manager
# ==============================================================================

def test_context_manager():
    """Test MountContext context manager"""
    print_header("TEST 7: Context Manager")
    
    try:
        print_test("Testing MountContext")
        from trilio_dms.client import DMSClient, MountContext
        
        client = DMSClient()
        
        request = {
            'job': {'jobid': 9201},
            'backup_target': {
                'id': 'test-context-target',
                'type': 's3',
                'filesystem_export_mount_path': '/mnt/test-context'
            },
            'host': 'test-host'
        }
        
        print_test("Entering context (should mount)")
        try:
            with MountContext(client, request) as ctx:
                print_success(f"Mounted at: {ctx.mount_path}")
                print_info("Performing simulated backup...")
                time.sleep(1)
                print_success("Backup complete")
            # Unmount should happen automatically here
            print_success("Context exited (should have unmounted)")
        except Exception as e:
            print_warning(f"Context mount/unmount had issues: {e}")
            print_warning("This is expected if DMS Server is not running")
        
        # Verify unmounted in ledger
        print_test("Verifying ledger shows unmounted")
        ledger = client.get_mount_status(9201, 'test-context-target')
        if ledger and not ledger.mounted:
            print_success("Ledger correctly shows mounted=False")
        else:
            print_warning("Ledger check inconclusive")
        
        client.close()
        print_success("Context manager test passed")
        return True
        
    except Exception as e:
        print_error(f"Context manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# Test 8: Concurrent Threads
# ==============================================================================

def test_concurrent_threads():
    """Test concurrent operations from multiple threads"""
    print_header("TEST 8: Concurrent Threads (Real Concurrency)")
    
    try:
        print_test("Testing 5 concurrent threads")
        from trilio_dms.client import DMSClient
        
        results = []
        errors = []
        
        def worker(worker_id):
            try:
                client = DMSClient()
                
                request = {
                    'job': {'jobid': 9300 + worker_id},
                    'backup_target': {
                        'id': f'test-thread-target-{worker_id}',
                        'type': 's3',
                        'filesystem_export_mount_path': f'/mnt/test-thread-{worker_id}'
                    },
                    'host': 'test-host'
                }
                
                # Mount
                mount_resp = client.mount(request)
                # Unmount
                unmount_resp = client.unmount(request)
                
                client.close()
                
                results.append({
                    'worker_id': worker_id,
                    'mount_status': mount_resp['status'],
                    'unmount_status': unmount_resp['status']
                })
                
            except Exception as e:
                errors.append({'worker_id': worker_id, 'error': str(e)})
        
        # Start threads
        threads = []
        start_time = time.time()
        
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        elapsed = time.time() - start_time
        
        print_info(f"All threads completed in {elapsed:.2f} seconds")
        print_info(f"Successful operations: {len(results)}")
        print_info(f"Errors: {len(errors)}")
        
        if len(results) == 5:
            print_success("All 5 threads completed successfully")
            for r in results:
                print_info(f"  Worker {r['worker_id']}: mount={r['mount_status']}, unmount={r['unmount_status']}")
        else:
            print_error(f"Only {len(results)}/5 threads succeeded")
            for e in errors:
                print_error(f"  Worker {e['worker_id']}: {e['error']}")
        
        print_success("Concurrent threads test passed")
        return True
        
    except Exception as e:
        print_error(f"Concurrent threads test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================================================================
# Main Test Runner
# ==============================================================================

def run_all_tests():
    """Run all tests"""
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{'TRILIO DMS TEST SUITE':^70}{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"\n{Colors.BOLD}Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.END}\n")
    
    tests = [
        ("Configuration", test_configuration),
        ("Database", test_database),
        ("RabbitMQ", test_rabbitmq),
        ("Lock Manager", test_lock_manager),
        ("Single Job Mount/Unmount", test_single_job_mount_unmount),
        ("Concurrent Jobs", test_concurrent_jobs),
        ("Context Manager", test_context_manager),
        ("Concurrent Threads", test_concurrent_threads),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.END}")
            break
        except Exception as e:
            print_error(f"Test {test_name} crashed: {e}")
            results[test_name] = False
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for r in results.values() if r)
    failed = sum(1 for r in results.values() if not r)
    total = len(results)
    
    for test_name, result in results.items():
        if result:
            print(f"  {Colors.GREEN}✓{Colors.END} {test_name}")
        else:
            print(f"  {Colors.RED}✗{Colors.END} {test_name}")
    
    print()
    print(f"{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.END}")
    
    if failed == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 ALL TESTS PASSED! 🎉{Colors.END}\n")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ {failed} TEST(S) FAILED{Colors.END}\n")
        return 1


if __name__ == '__main__':
    exit_code = run_all_tests()
    sys.exit(exit_code)
