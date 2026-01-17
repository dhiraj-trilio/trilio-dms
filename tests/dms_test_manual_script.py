#!/usr/bin/env python3
"""
Trilio DMS Manual Test Scripts

Individual test scripts for manual testing and validation.
"""

# ==============================================================================
# Script 1: Quick Configuration Check
# ==============================================================================

def test_config_quick():
    """Quick configuration check"""
    print("="*60)
    print("DMS Configuration Quick Check")
    print("="*60)
    
    from trilio_dms.config import DMSConfig
    
    DMSConfig.print_config()
    
    print("\nValidating...")
    try:
        DMSConfig.validate_server_config()
        print("✓ Server configuration is valid")
    except Exception as e:
        print(f"✗ Server configuration error: {e}")
    
    try:
        DMSConfig.validate_client_config()
        print("✓ Client configuration is valid")
    except Exception as e:
        print(f"✗ Client configuration error: {e}")


# ==============================================================================
# Script 2: Test Mount/Unmount Single Target
# ==============================================================================

def test_mount_unmount_single():
    """Test mounting and unmounting a single target"""
    print("="*60)
    print("Testing Single Mount/Unmount")
    print("="*60)
    
    from trilio_dms.client import DMSClient
    import time
    
    client = DMSClient()
    
    # Test parameters
    jobid = int(input("Enter Job ID (e.g., 12345): ") or "12345")
    backup_target_id = input("Enter Backup Target ID (e.g., target-001): ") or "target-001"
    host = input("Enter Host (e.g., compute-01): ") or "compute-01"
    mount_path = input("Enter Mount Path (e.g., /mnt/target-001): ") or f"/mnt/{backup_target_id}"
    
    request = {
        'job': {'jobid': jobid},
        'backup_target': {
            'id': backup_target_id,
            'type': 's3',
            'filesystem_export_mount_path': mount_path
        },
        'host': host
    }
    
    # Mount
    print(f"\n1. Mounting target {backup_target_id}...")
    response = client.mount(request)
    print(f"   Status: {response['status']}")
    print(f"   Message: {response.get('success_msg') or response.get('error_msg')}")
    if response['status'] == 'success':
        print(f"   Mount Path: {response.get('mount_path')}")
        print(f"   Reused Existing: {response.get('reused_existing')}")
    
    # Check ledger
    print(f"\n2. Checking ledger...")
    ledger = client.get_mount_status(jobid, backup_target_id)
    if ledger:
        print(f"   ✓ Ledger entry found")
        print(f"     - Mounted: {ledger.mounted}")
        print(f"     - Host: {ledger.host}")
    else:
        print(f"   ✗ No ledger entry found")
    
    # Wait
    input("\nPress Enter to unmount...")
    
    # Unmount
    print(f"\n3. Unmounting target {backup_target_id}...")
    response = client.unmount(request)
    print(f"   Status: {response['status']}")
    print(f"   Message: {response.get('success_msg') or response.get('error_msg')}")
    if response['status'] == 'success':
        print(f"   Physically Unmounted: {response.get('unmounted')}")
        print(f"   Remaining Mounts: {response.get('active_mounts_remaining')}")
    
    # Check ledger again
    print(f"\n4. Verifying ledger updated...")
    ledger = client.get_mount_status(jobid, backup_target_id)
    if ledger:
        print(f"   Ledger entry:")
        print(f"     - Mounted: {ledger.mounted}")
    else:
        print(f"   No ledger entry found")
    
    client.close()
    print("\n✓ Test complete")


# ==============================================================================
# Script 3: Test Concurrent Jobs
# ==============================================================================

def test_concurrent_jobs_manual():
    """Manually test concurrent jobs"""
    print("="*60)
    print("Testing Concurrent Jobs (Manual)")
    print("="*60)
    
    from trilio_dms.client import DMSClient
    
    client = DMSClient()
    
    backup_target_id = input("Enter Backup Target ID (e.g., shared-target): ") or "shared-target"
    host = input("Enter Host (e.g., compute-01): ") or "compute-01"
    mount_path = f"/mnt/{backup_target_id}"
    
    num_jobs = int(input("How many jobs? (e.g., 3): ") or "3")
    
    job_ids = []
    for i in range(num_jobs):
        jobid = int(input(f"Enter Job ID #{i+1} (e.g., {10001+i}): ") or str(10001+i))
        job_ids.append(jobid)
    
    # Mount from all jobs
    print(f"\n1. Mounting from {num_jobs} jobs...")
    for jobid in job_ids:
        request = {
            'job': {'jobid': jobid},
            'backup_target': {
                'id': backup_target_id,
                'type': 's3',
                'filesystem_export_mount_path': mount_path
            },
            'host': host
        }
        
        response = client.mount(request)
        print(f"   Job {jobid}: {response['status']} (reused={response.get('reused_existing')})")
    
    # Show active mounts
    print(f"\n2. Active mounts:")
    active = client.get_active_mounts(backup_target_id=backup_target_id)
    print(f"   Total: {len(active)}")
    for mount in active:
        print(f"     - Job {mount.jobid}: mounted={mount.mounted}, host={mount.host}")
    
    # Unmount one by one
    for i, jobid in enumerate(job_ids):
        input(f"\nPress Enter to unmount job {jobid} ({i+1}/{num_jobs})...")
        
        request = {
            'job': {'jobid': jobid},
            'backup_target': {
                'id': backup_target_id,
                'type': 's3',
                'filesystem_export_mount_path': mount_path
            },
            'host': host
        }
        
        response = client.unmount(request)
        print(f"   Job {jobid}: {response['status']}")
        print(f"     - Physically unmounted: {response.get('unmounted')}")
        print(f"     - Remaining mounts: {response.get('active_mounts_remaining')}")
        
        # Show remaining active mounts
        active = client.get_active_mounts(backup_target_id=backup_target_id)
        print(f"     - Active mounts now: {len(active)}")
    
    client.close()
    print("\n✓ Test complete")


# ==============================================================================
# Script 4: Stress Test - Many Concurrent Operations
# ==============================================================================

def test_stress():
    """Stress test with many concurrent operations"""
    print("="*60)
    print("Stress Test")
    print("="*60)
    
    import threading
    import time
    from trilio_dms.client import DMSClient
    
    num_threads = int(input("Number of concurrent threads (e.g., 10): ") or "10")
    operations_per_thread = int(input("Operations per thread (e.g., 5): ") or "5")
    
    print(f"\nStarting stress test:")
    print(f"  Threads: {num_threads}")
    print(f"  Operations per thread: {operations_per_thread}")
    print(f"  Total operations: {num_threads * operations_per_thread}")
    
    results = {'success': 0, 'error': 0}
    lock = threading.Lock()
    
    def worker(worker_id):
        client = DMSClient()
        
        for op in range(operations_per_thread):
            try:
                jobid = worker_id * 1000 + op
                
                request = {
                    'job': {'jobid': jobid},
                    'backup_target': {
                        'id': f'stress-target-{worker_id}',
                        'type': 's3',
                        'filesystem_export_mount_path': f'/mnt/stress-{worker_id}'
                    },
                    'host': 'stress-host'
                }
                
                # Mount
                mount_resp = client.mount(request)
                # Small delay
                time.sleep(0.1)
                # Unmount
                unmount_resp = client.unmount(request)
                
                if mount_resp['status'] == 'success' and unmount_resp['status'] == 'success':
                    with lock:
                        results['success'] += 1
                else:
                    with lock:
                        results['error'] += 1
                        
            except Exception as e:
                with lock:
                    results['error'] += 1
                print(f"Worker {worker_id}: Error on op {op}: {e}")
        
        client.close()
    
    # Start test
    start_time = time.time()
    
    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
    
    # Wait for completion
    for t in threads:
        t.join()
    
    elapsed = time.time() - start_time
    
    # Results
    total = results['success'] + results['error']
    print(f"\nStress Test Results:")
    print(f"  Total operations: {total}")
    print(f"  Successful: {results['success']} ({results['success']/total*100:.1f}%)")
    print(f"  Errors: {results['error']} ({results['error']/total*100:.1f}%)")
    print(f"  Time elapsed: {elapsed:.2f} seconds")
    print(f"  Operations/second: {total/elapsed:.2f}")
    
    if results['error'] == 0:
        print("\n✓ All operations successful!")
    else:
        print(f"\n⚠ {results['error']} operations failed")


# ==============================================================================
# Script 5: Check Active Mounts
# ==============================================================================

def check_active_mounts():
    """Check all active mounts"""
    print("="*60)
    print("Active Mounts Report")
    print("="*60)
    
    from trilio_dms.client import DMSClient
    
    client = DMSClient()
    
    # Get all active mounts
    active = client.get_active_mounts()
    
    if not active:
        print("\nNo active mounts found.")
        client.close()
        return
    
    print(f"\nFound {len(active)} active mount(s):\n")
    
    # Group by target
    by_target = {}
    for mount in active:
        target_id = mount.backup_target_id
        if target_id not in by_target:
            by_target[target_id] = []
        by_target[target_id].append(mount)
    
    for target_id, mounts in by_target.items():
        print(f"Target: {target_id}")
        print(f"  Active mounts: {len(mounts)}")
        for mount in mounts:
            print(f"    - Job {mount.jobid} on {mount.host}")
        print()
    
    client.close()


# ==============================================================================
# Script 6: Cleanup Test Data
# ==============================================================================

def cleanup_test_data():
    """Clean up test data from ledger"""
    print("="*60)
    print("Cleanup Test Data")
    print("="*60)
    
    from trilio_dms.client import DMSClient
    from trilio_dms.models import BackupTargetMountLedger
    
    client = DMSClient()
    session = client.SessionLocal()
    
    # Find test entries (jobid > 9000 are test jobs)
    test_entries = session.query(BackupTargetMountLedger).filter(
        BackupTargetMountLedger.jobid >= 9000
    ).all()
    
    if not test_entries:
        print("\nNo test data found (jobid >= 9000)")
        session.close()
        client.close()
        return
    
    print(f"\nFound {len(test_entries)} test entries:")
    for entry in test_entries:
        print(f"  - Job {entry.jobid}: {entry.backup_target_id} on {entry.host}")
    
    confirm = input("\nDelete these entries? (yes/no): ")
    
    if confirm.lower() == 'yes':
        for entry in test_entries:
            session.delete(entry)
        session.commit()
        print(f"\n✓ Deleted {len(test_entries)} test entries")
    else:
        print("\nCancelled")
    
    session.close()
    client.close()


# ==============================================================================
# Main Menu
# ==============================================================================

def main_menu():
    """Show main menu"""
    while True:
        print("\n" + "="*60)
        print("TRILIO DMS MANUAL TEST MENU")
        print("="*60)
        print("\n1. Quick Configuration Check")
        print("2. Test Mount/Unmount (Single Target)")
        print("3. Test Concurrent Jobs")
        print("4. Stress Test")
        print("5. Check Active Mounts")
        print("6. Cleanup Test Data")
        print("0. Exit")
        
        choice = input("\nSelect option: ")
        
        if choice == '1':
            test_config_quick()
        elif choice == '2':
            test_mount_unmount_single()
        elif choice == '3':
            test_concurrent_jobs_manual()
        elif choice == '4':
            test_stress()
        elif choice == '5':
            check_active_mounts()
        elif choice == '6':
            cleanup_test_data()
        elif choice == '0':
            print("\nExiting...")
            break
        else:
            print("\nInvalid option")
        
        input("\nPress Enter to continue...")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        # Run specific test
        test_name = sys.argv[1]
        if test_name == 'config':
            test_config_quick()
        elif test_name == 'mount':
            test_mount_unmount_single()
        elif test_name == 'concurrent':
            test_concurrent_jobs_manual()
        elif test_name == 'stress':
            test_stress()
        elif test_name == 'active':
            check_active_mounts()
        elif test_name == 'cleanup':
            cleanup_test_data()
        else:
            print(f"Unknown test: {test_name}")
            print("Available: config, mount, concurrent, stress, active, cleanup")
    else:
        # Show menu
        main_menu()
