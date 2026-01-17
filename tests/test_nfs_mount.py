#!/usr/bin/env python3
"""
Test script for real NFS mount with proper error handling and diagnostics
"""

import logging
import sys
import traceback

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("="*70)
print("DMS Client NFS Mount Test")
print("="*70)

# Step 1: Load configuration
print("\n1. Loading configuration...")
try:
    from trilio_dms.config import DMSConfig
    DMSConfig.load_config(config_type='client')
    
    print(f"   ✓ Config loaded")
    print(f"   - DB_URL: {DMSConfig._mask_password(DMSConfig.DB_URL)}")
    print(f"   - RABBITMQ_URL: {DMSConfig._mask_password(DMSConfig.RABBITMQ_URL)}")
    print(f"   - NODE_ID: {DMSConfig.NODE_ID}")
except Exception as e:
    print(f"   ✗ Config loading failed: {e}")
    sys.exit(1)

# Step 2: Initialize client
print("\n2. Initializing DMS Client...")
try:
    from trilio_dms.client import DMSClient
    client = DMSClient()
    print(f"   ✓ Client initialized")
    print(f"   - Using DB: {DMSConfig._mask_password(client.db_url)}")
    print(f"   - Using RabbitMQ: {DMSConfig._mask_password(client.rabbitmq_url)}")
except Exception as e:
    print(f"   ✗ Client initialization failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 3: Prepare request
print("\n3. Preparing mount request...")
request = {
    'keystone_token': 'gAAAAABpai8dVCu3F-nAlje4V1-IAyvTecF_zMYBkOgJ-ie0IUBiMr6spj6nU4VYvXix8QffXjqfnMSoNAuc4brYNNGiXhD4glZR4SkBkm9ney-5Jc2_YdlZ9iF3VIVlmSe3JTBnblo_zsRDD9u0p3ufpNB5V3G-qZlUrr04Ry-otE6ETUOsGOA',
    'context': {'tenant_id': '12345'},
    'job': {
        'jobid': 1,
        'progress': 'progress',
        'status': 'active',
        'action': 'backup',
        'parent_jobid': None,
        'job_details': [{
             'id': 123,
             'data': 'data'

        }]
    },

    'status': 'running',
    'host': 'controller',
    'backup_target': {
        'id': '20272009-8408-4f3f-97eb-bff61c3c5712',
        'type': 'nfs',
        'filesystem_export': '192.168.0.51:/home/kolla/',
        'filesystem_export_mount_path': '/var/trilio/triliovault-mounts/L2hvbWUva29sbGEv',
        'nfs_mount_opts': 'nolock,soft,timeo=600,intr,lookupcache=none,nfsvers=3,retrans=10',
        'status': 'available'
    }
}

print(f"   ✓ Request prepared")
print(f"   - Job ID: {request['job']['jobid']}")
print(f"   - Target ID: {request['backup_target']['id']}")
print(f"   - Host: {request['host']}")
print(f"   - Type: {request['backup_target']['type']}")
print(f"   - NFS Export: {request['backup_target']['filesystem_export']}")
print(f"   - Mount Path: {request['backup_target']['filesystem_export_mount_path']}")

# Step 4: Check if already mounted
print("\n4. Checking existing mount status...")
try:
    ledger = client.get_mount_status(
        job_id=request['job']['jobid'],
        backup_target_id=request['backup_target']['id']
    )
    
    if ledger:
        print(f"   ⚠ Ledger entry already exists:")
        print(f"     - Mounted: {ledger.mounted}")
        print(f"     - Host: {ledger.host}")
        
        if ledger.mounted:
            print(f"   ⚠ Target already mounted for this job")
            unmount_first = input("   Unmount first? (yes/no): ")
            if unmount_first.lower() == 'yes':
                print("   Unmounting...")
                unmount_response = client.unmount(request)
                print(f"   Unmount status: {unmount_response['status']}")
    else:
        print(f"   ✓ No existing mount found")
except Exception as e:
    print(f"   ✗ Error checking mount status: {e}")
    traceback.print_exc()

# Step 5: Check active mounts for this target
print("\n5. Checking other active mounts for this target...")
try:
    active_mounts = client.get_active_mounts(
        backup_target_id=request['backup_target']['id']
    )
    
    if active_mounts:
        print(f"   ⚠ Found {len(active_mounts)} active mount(s):")
        for mount in active_mounts:
            print(f"     - Job {mount.jobid} on {mount.host}")
    else:
        print(f"   ✓ No other active mounts")
except Exception as e:
    print(f"   ✗ Error checking active mounts: {e}")

# Step 6: Execute mount
print("\n6. Executing mount request...")
print("   (This will acquire global lock and send request to DMS Server)")

try:
    response = client.mount(request)
    
    print(f"\n   Mount Response:")
    print(f"   - Status: {response['status']}")
    
    if response['status'] == 'success':
        print(f"   ✓ SUCCESS")
        print(f"   - Message: {response.get('success_msg')}")
        print(f"   - Mount Path: {response.get('mount_path')}")
        print(f"   - Reused Existing: {response.get('reused_existing', False)}")
        print(f"   - Physically Mounted: {response.get('physically_mounted', False)}")
    else:
        print(f"   ✗ FAILED")
        print(f"   - Error: {response.get('error_msg')}")
        
        # Check if it's a validation error
        if 'Missing required field' in response.get('error_msg', ''):
            print(f"\n   Troubleshooting:")
            print(f"   - Check that all required fields are in request")
            print(f"   - Verify utils.validate_request_structure() expectations")
        
        # Check if it's a RabbitMQ error
        if 'timeout' in response.get('error_msg', '').lower():
            print(f"\n   Troubleshooting:")
            print(f"   - Is DMS Server running? (trilio-dms-server)")
            print(f"   - Check queue: dms.{request['host']}")
            print(f"   - Verify RabbitMQ connectivity")
        
        # Check if it's a lock error
        if 'lock' in response.get('error_msg', '').lower():
            print(f"\n   Troubleshooting:")
            print(f"   - Another process may be holding the lock")
            print(f"   - Check /var/lock/trilio-dms/")
            
except Exception as e:
    print(f"   ✗ Exception during mount: {e}")
    traceback.print_exc()

# Step 7: Verify ledger updated
print("\n7. Verifying ledger entry...")
try:
    ledger = client.get_mount_status(
        job_id=request['job']['jobid'],
        backup_target_id=request['backup_target']['id']
    )
    
    if ledger:
        print(f"   ✓ Ledger entry found:")
        print(f"     - Job ID: {ledger.jobid}")
        print(f"     - Target ID: {ledger.backup_target_id}")
        print(f"     - Host: {ledger.host}")
        print(f"     - Mounted: {ledger.mounted}")
    else:
        print(f"   ✗ No ledger entry found")
except Exception as e:
    print(f"   ✗ Error checking ledger: {e}")

# Step 8: Cleanup
print("\n8. Cleanup...")
try:
    client.close()
    print(f"   ✓ Client closed")
except Exception as e:
    print(f"   ✗ Error closing client: {e}")

print("\n" + "="*70)
print("Test Complete")
print("="*70)

# Prompt for unmount
unmount = input("\nDo you want to unmount? (yes/no): ")
if unmount.lower() == 'yes':
    print("\nUnmounting...")
    try:
        client = DMSClient()
        response = client.unmount(request)
        
        print(f"Unmount Response:")
        print(f"  Status: {response['status']}")
        
        if response['status'] == 'success':
            print(f"  ✓ {response.get('success_msg')}")
            print(f"  - Physically Unmounted: {response.get('unmounted')}")
            print(f"  - Remaining Mounts: {response.get('active_mounts_remaining')}")
        else:
            print(f"  ✗ {response.get('error_msg')}")
        
        client.close()
    except Exception as e:
        print(f"  ✗ Unmount failed: {e}")
        traceback.print_exc()
