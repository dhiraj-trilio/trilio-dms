"""Configuration wizard - Updated to support NFS mount options and new SecretManager"""

import json
import uuid
import sys
from keystoneauth1 import session as ks_session
from keystoneauth1.identity import v3

from trilio_dms.config import DMSConfig
from trilio_dms.models import BackupTarget, initialize_database, get_session
from trilio_dms.services.secret_manager import SecretManager  # Updated import
from trilio_dms.utils.logger import get_logger
from trilio_dms.utils.validators import (
    validate_nfs_share, validate_s3_bucket, validate_mount_path
)

LOG = get_logger(__name__)


class BackupTargetWizard:
    """Interactive wizard for target registration"""

    def __init__(self, config: DMSConfig):
        self.config = config
        initialize_database(config)
        
        # Initialize SecretManager with minimal config
        secret_config = {
            'verify_ssl': getattr(config, 'verify_ssl', False)
        }
        self.secret_manager = SecretManager(secret_config)

    def run(self):
        """Run the interactive wizard"""
        print("\n" + "="*60)
        print("Trilio Backup Target Registration Wizard")
        print("="*60 + "\n")

        # Choose target type
        print("Select backup target type:")
        print("  1. NFS")
        print("  2. S3")
        print()

        choice = input("Enter choice [1-2]: ").strip()

        if choice == '1':
            self._configure_nfs_target()
        elif choice == '2':
            self._configure_s3_target()
        else:
            print("❌ Invalid choice")

    def _configure_nfs_target(self):
        """Configure NFS target with mount options"""
        print("\n" + "="*60)
        print("NFS Target Configuration")
        print("="*60 + "\n")

        # Target name
        target_name = input("Target Name: ").strip()
        if not target_name:
            print("❌ Target name is required")
            return

        # NFS share
        nfs_share = input("NFS Share (server:/export/path): ").strip()

        if not validate_nfs_share(nfs_share):
            print("❌ Invalid NFS share format")
            print("   Expected format: server:/export/path")
            return

        # Mount path
        default_name = nfs_share.replace('/', '_').replace(':', '_')
        default_path = f"{self.config.mount_base_path}/{default_name}"
        mount_path = input(f"Mount Path [{default_path}]: ").strip()
        mount_path = mount_path or default_path

        if not validate_mount_path(mount_path):
            print("❌ Invalid mount path")
            return

        # NFS mount options
        print("\nNFS Mount Options")
        print("-" * 40)
        print("Common options:")
        print("  - defaults          (standard options)")
        print("  - vers=4.1,rw       (NFSv4.1, read-write)")
        print("  - vers=3,rw,nolock  (NFSv3, no locking)")
        print("  - rw,sync,hard      (synchronous, hard mount)")
        print("  - rw,async,soft     (asynchronous, soft mount)")

        mount_opts = input("\nMount Options [defaults]: ").strip() or 'defaults'

        # Confirm
        print("\n" + "="*60)
        print("Review NFS Target Configuration")
        print("="*60)
        print(f"Name:          {target_name}")
        print(f"NFS Share:     {nfs_share}")
        print(f"Mount Path:    {mount_path}")
        print(f"Mount Options: {mount_opts}")
        print()

        confirm = input("Create this target? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("❌ Cancelled")
            return

        # Create target
        session = get_session()
        try:
            target = BackupTarget(
                id=str(uuid.uuid4()),
                type='nfs',
                name=target_name,
                filesystem_export=nfs_share,
                filesystem_export_mount_path=mount_path,
                status='available',
                secret_ref=None,
                nfs_mount_opts=mount_opts
            )

            session.add(target)
            session.commit()

            print(f"\n✅ NFS target registered successfully!")
            print(f"   Target ID:     {target.id}")
            print(f"   Name:          {target_name}")
            print(f"   NFS Share:     {nfs_share}")
            print(f"   Mount Path:    {mount_path}")
            print(f"   Mount Options: {mount_opts}")

        except Exception as e:
            LOG.error(f"Failed to register NFS target: {e}", exc_info=True)
            print(f"❌ Failed to register target: {e}")
            session.rollback()
        finally:
            session.close()

    def _configure_s3_target(self):
        """Configure S3 target with Barbican secret"""
        print("\n" + "="*60)
        print("S3 Target Configuration")
        print("="*60 + "\n")

        # Target name
        target_name = input("Target Name: ").strip()
        if not target_name:
            print("❌ Target name is required")
            return

        # S3 bucket
        s3_bucket = input("S3 Bucket Name: ").strip()

        if not validate_s3_bucket(s3_bucket):
            print("❌ Invalid S3 bucket name")
            return

        # Mount path
        default_path = f"{self.config.mount_base_path}/{s3_bucket}"
        mount_path = input(f"Mount Path [{default_path}]: ").strip()
        mount_path = mount_path or default_path

        if not validate_mount_path(mount_path):
            print("❌ Invalid mount path")
            return

        # Barbican secret reference
        print("\n" + "-"*60)
        print("Barbican Secret Configuration")
        print("-"*60)
        print("You need to provide the Barbican secret reference URL")
        print("that contains the S3 credentials and configuration.")
        print()
        print("Expected secret payload format (JSON):")
        print(json.dumps({
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "vault_s3_bucket": "bucket-name",
            "vault_s3_region_name": "us-west-2",
            "vault_s3_auth_version": "DEFAULT",
            "vault_s3_signature_version": "default",
            "vault_s3_ssl": "true",
            "vault_s3_ssl_verify": "true",
            "vault_storage_nfs_export": "bucket-name",
            "bucket_object_lock": "false",
            "use_manifest_suffix": "false",
            "vault_s3_endpoint_url": "",
            "vault_s3_max_pool_connections": "500",
            "log_config_append": "/etc/triliovault-object-store/object_store_logging.conf"
        }, indent=2))
        print()
        print("Note: vault_data_directory is NOT required in the secret.")
        print("      It will be set from the mount path you specify above.")
        print()

        secret_ref = input("Barbican Secret Reference URL: ").strip()
        if not secret_ref:
            print("❌ Secret reference is required for S3 targets")
            return

        # Validate format
        if not secret_ref.startswith('http'):
            print("❌ Secret reference must be a full URL")
            print("   Example: https://barbican:9311/v1/secrets/uuid")
            return

        # Test secret access
        print("\n" + "-"*60)
        print("Testing Secret Access")
        print("-"*60)
        
        test_secret = input("Test secret access now? (yes/no) [yes]: ").strip().lower()
        test_secret = test_secret if test_secret else 'yes'

        if test_secret == 'yes':
            # Get authentication
            print("\n🔐 Keystone Authentication Required")
            print("-" * 40)
            
            auth_url = getattr(self.config, 'auth_url', None)
            if auth_url:
                print(f"Auth URL: {auth_url}")
            else:
                auth_url = input("Auth URL: ").strip()
                if not auth_url:
                    print("❌ Auth URL is required")
                    return

            username = input("Username: ").strip()
            password = input("Password: ").strip()
            project_name = input("Project [admin]: ").strip() or 'admin'

            try:
                # Get token
                auth = v3.Password(
                    auth_url=auth_url,
                    username=username,
                    password=password,
                    project_name=project_name,
                    user_domain_name='Default',
                    project_domain_name='Default'
                )
                sess = ks_session.Session(auth=auth, verify=False)
                token = sess.get_token()

                print("✅ Authentication successful")
                print()

                # Test secret retrieval
                print("Testing secret retrieval...")
                test_result = self.secret_manager.test_secret_access(secret_ref, token)

                if not test_result['metadata_accessible']:
                    print(f"❌ Cannot access secret metadata")
                    if test_result.get('error'):
                        print(f"   Error: {test_result['error']}")
                    print("\nPlease check:")
                    print("  - Secret reference URL is correct")
                    print("  - Token has permission to access the secret")
                    print("  - Secret exists in Barbican")
                    return

                print("✅ Secret metadata accessible")

                if not test_result['payload_accessible']:
                    print(f"❌ Cannot access secret payload")
                    if test_result.get('error'):
                        print(f"   Error: {test_result['error']}")
                    return

                print("✅ Secret payload accessible")
                print()

                # Retrieve and validate credentials
                credentials = self.secret_manager.retrieve_credentials(secret_ref, token)
                
                print("Retrieved credential keys:")
                for key in sorted(credentials.keys()):
                    if any(s in key.lower() for s in ['key', 'secret', 'password']):
                        print(f"  ✓ {key}: ****")
                    else:
                        print(f"  ✓ {key}")
                print()

                # Check for required keys
                required_keys = ['access_key', 'secret_key', 'vault_s3_bucket']
                missing_keys = [k for k in required_keys if k not in credentials]
                
                if missing_keys:
                    print(f"⚠ Warning: Missing required keys: {', '.join(missing_keys)}")
                else:
                    print("✅ All required S3 credentials present")
                print()

                # Check if vault_data_directory is in secret
                if 'vault_data_directory' in credentials:
                    if credentials['vault_data_directory'] != mount_path:
                        print(f"⚠ Note: vault_data_directory in secret ({credentials['vault_data_directory']})")
                        print(f"        differs from mount path ({mount_path})")
                        print(f"        The mount path will be used (from database).")
                        print()

            except Exception as e:
                LOG.error(f"Secret test failed: {e}", exc_info=True)
                print(f"❌ Secret test failed: {e}")
                print("\nContinue anyway? (yes/no): ", end='')
                if input().strip().lower() != 'yes':
                    return

        # Confirm
        print("\n" + "="*60)
        print("Review S3 Target Configuration")
        print("="*60)
        print(f"Name:        {target_name}")
        print(f"S3 Bucket:   {s3_bucket}")
        print(f"Mount Path:  {mount_path}")
        print(f"Secret Ref:  {secret_ref}")
        print()

        confirm = input("Create this target? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("❌ Cancelled")
            return

        # Create target
        session = get_session()
        try:
            target = BackupTarget(
                id=str(uuid.uuid4()),
                type='s3',
                name=target_name,
                filesystem_export=s3_bucket,
                filesystem_export_mount_path=mount_path,
                status='available',
                secret_ref=secret_ref
            )

            session.add(target)
            session.commit()

            print(f"\n✅ S3 target registered successfully!")
            print(f"   Target ID:   {target.id}")
            print(f"   Name:        {target_name}")
            print(f"   S3 Bucket:   {s3_bucket}")
            print(f"   Mount Path:  {mount_path}")
            print(f"   Secret Ref:  {secret_ref}")
            print()
            print("💡 Note: The mount path will be set as vault_data_directory")
            print("         when mounting with s3vaultfuse.")

        except Exception as e:
            LOG.error(f"Failed to register S3 target: {e}", exc_info=True)
            print(f"❌ Failed to register target: {e}")
            session.rollback()
        finally:
            session.close()
