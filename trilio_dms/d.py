#!/usr/bin/env python3
"""
Test script for debugging Barbican secret retrieval.
Usage: python test_secret_retrieval.py
"""

import sys
import json
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from trilio_dms.services.secret_manager import SecretManager
from trilio_dms.utils.exceptions import AuthenticationException


def test_secret_retrieval():
    """Test secret retrieval with your token and secret_ref."""
    
    # YOUR VALUES HERE
    secret_ref = "https://kolla-external-rockycaracaldev3.triliodata.demo:9311/v1/secrets/5ae52989-3aff-4f0e-85f5-03d23a866277"
    keystone_token = "gAAAAABpZk5pOAG2-4EC3MP3pQWTskajZlTxIX5wyZ9qnZOJTmZrY8VtzE9ZfDf9Arfh55Zrsl0mtYcCyxwhjscsNCXBc9u1zKArlEXroG7gxT_WDq7EDfS_wuT8MrW-qjdyGHRef-xjTzMhYqxPf0l98A2UBr34_M99q7lrFsxzxFGvF5Zrzbk"
    
    print("=" * 80)
    print("Testing Barbican Secret Retrieval")
    print("=" * 80)
    print(f"Secret Ref: {secret_ref}")
    print(f"Token (first 20 chars): {keystone_token[:20]}...")
    print()
    
    # Initialize SecretManager
    config = {
        'verify_ssl': False  # Disable SSL verification
    }
    
    secret_manager = SecretManager(config)
    
    # Test 1: Test access (metadata and payload)
    print("Test 1: Testing secret access...")
    print("-" * 80)
    try:
        test_result = secret_manager.test_secret_access(secret_ref, keystone_token)
        print(json.dumps(test_result, indent=2))
        
        if not test_result['metadata_accessible']:
            print("\n❌ FAILED: Cannot access secret metadata")
            print("Possible causes:")
            print("  - Token is invalid or expired")
            print("  - Token is not project-scoped")
            print("  - Secret ref URL is incorrect")
            print("  - Token doesn't have permission to access this secret")
            return False
        
        if not test_result['payload_accessible']:
            print("\n❌ FAILED: Can access metadata but not payload")
            print("Possible causes:")
            print("  - Secret has no payload")
            print("  - Permission issue with payload access")
            return False
        
        print("\n✓ Access test passed!")
        
    except Exception as e:
        print(f"\n❌ Access test failed with exception: {e}")
        return False
    
    print()
    
    # Test 2: Retrieve actual credentials
    print("Test 2: Retrieving credentials...")
    print("-" * 80)
    try:
        credentials = secret_manager.retrieve_credentials(secret_ref, keystone_token)
        
        print("✓ Successfully retrieved credentials!")
        print(f"Credential keys: {list(credentials.keys())}")
        
        # Print credentials (mask sensitive data)
        print("\nCredentials (sensitive data masked):")
        for key, value in credentials.items():
            if key in ['access_key', 'secret_key', 'password', 'token']:
                # Mask sensitive data
                if isinstance(value, str) and len(value) > 8:
                    masked_value = value[:4] + '*' * (len(value) - 8) + value[-4:]
                else:
                    masked_value = '****'
                print(f"  {key}: {masked_value}")
            else:
                print(f"  {key}: {value}")
        
        # Validate S3 credentials
        print("\nValidating S3 credentials...")
        required_keys = ['access_key', 'secret_key']
        missing_keys = [key for key in required_keys if key not in credentials]
        
        if missing_keys:
            print(f"⚠ Warning: Missing required S3 keys: {missing_keys}")
        else:
            print("✓ All required S3 credentials present")
        
        return True
        
    except AuthenticationException as e:
        print(f"\n❌ Failed to retrieve credentials: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_with_different_endpoints():
    """Test with both internal and external endpoints."""
    
    secret_uuid = "5ae52989-3aff-4f0e-85f5-03d23a866277"
    keystone_token = "gAAAAABpZk5pOAG2-4EC3MP3pQWTskajZlTxIX5wyZ9qnZOJTmZrY8VtzE9ZfDf9Arfh55Zrsl0mtYcCyxwhjscsNCXBc9u1zKArlEXroG7gxT_WDq7EDfS_wuT8MrW-qjdyGHRef-xjTzMhYqxPf0l98A2UBr34_M99q7lrFsxzxFGvF5Zrzbk"
    
    endpoints = [
        f"https://kolla-external-rockycaracaldev3.triliodata.demo:9311/v1/secrets/{secret_uuid}",
        f"https://kolla-internal-rockycaracaldev3.triliodata.demo:9311/v1/secrets/{secret_uuid}",
    ]
    
    config = {'verify_ssl': False}
    secret_manager = SecretManager(config)
    
    print("\n" + "=" * 80)
    print("Testing Different Endpoints")
    print("=" * 80)
    
    for endpoint in endpoints:
        print(f"\nTrying: {endpoint}")
        print("-" * 80)
        try:
            result = secret_manager.test_secret_access(endpoint, keystone_token)
            if result['metadata_accessible'] and result['payload_accessible']:
                print(f"✓ SUCCESS with {endpoint}")
                return endpoint
            else:
                print(f"❌ Failed: {result.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"❌ Exception: {e}")
    
    return None


if __name__ == "__main__":
    print("\nStarting secret retrieval tests...\n")
    
    # Run main test
    success = test_secret_retrieval()
    
    if not success:
        print("\n" + "=" * 80)
        print("Main test failed. Trying different endpoints...")
        print("=" * 80)
        working_endpoint = test_with_different_endpoints()
        
        if working_endpoint:
            print(f"\n✓ Found working endpoint: {working_endpoint}")
            print("Update your secret_ref to use this endpoint.")
        else:
            print("\n❌ No working endpoint found.")
            print("\nTroubleshooting steps:")
            print("1. Verify your token is valid and project-scoped")
            print("2. Check if the secret UUID is correct")
            print("3. Verify network connectivity to Barbican endpoint")
            print("4. Check Barbican logs for permission errors")
    else:
        print("\n" + "=" * 80)
        print("✓ All tests passed!")
        print("=" * 80)
        print("\nYour secret retrieval is working correctly.")
        print("You can now use this in your mount_service.py")
    
    sys.exit(0 if success else 1)
