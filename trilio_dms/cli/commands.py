"""CLI command implementations - Updated with new commands"""

import json
import socket
import sys
from datetime import datetime
from typing import Optional
from keystoneauth1 import session as ks_session
from keystoneauth1.identity import v3

from trilio_dms.config import DMSConfig
from trilio_dms.models import BackupTarget, BackupTargetMountLedger, Job, get_session, initialize_database
from trilio_dms.client import DMSClient
from trilio_dms.utils.logger import get_logger
from trilio_dms.utils.validators import validate_mount_path

LOG = get_logger(__name__)


def list_targets(config: DMSConfig, format: str = 'table', 
                output: Optional[str] = None, full: bool = False):
    """List all registered targets with formatting options"""
    initialize_database(config)
    session = get_session()
    
    try:
        targets = session.query(BackupTarget).filter_by(deleted=False).all()
        
        if format == 'json':
            _output_json(targets, output, full)
        elif format == 'yaml':
            _output_yaml(targets, output, full)
        elif format == 'csv':
            _output_csv_targets(targets, output, full)
        else:  # table
            _output_table_targets(targets, full)
        
    finally:
        session.close()

def _output_table_targets(targets, full: bool = False):
    """Output targets as formatted table"""
    if not targets:
        print("\n📭 No targets found")
        return
    
    print("\n" + "="*140)
    print("Registered Backup Targets")
    print("="*140)
    
    if full:
        # Full output - no truncation
        print(f"{'Export':<50} {'Type':<8} {'Mount Path':<50} {'Status':<12} {'ID':<36}")
        print("-"*140)
        
        for target in targets:
            print(f"{target.filesystem_export:<50} "
                  f"{target.type:<8} "
                  f"{target.filesystem_export_mount_path:<50} "
                  f"{target.status:<12} "
                  f"{target.id:<36}")
    else:
        # Truncated output for better readability
        print(f"{'Export':<35} {'Type':<8} {'Mount Path':<40} {'Status':<12} {'ID':<20}")
        print("-"*140)
        
        for target in targets:
            # Truncate long values
            export = _truncate(target.filesystem_export, 33)
            mount_path = _truncate(target.filesystem_export_mount_path, 38)
            target_id = _truncate(target.id, 18)
            
            print(f"{export:<35} "
                  f"{target.type:<8} "
                  f"{mount_path:<40} "
                  f"{target.status:<12} "
                  f"{target_id:<20}")
    
    print(f"\nTotal: {len(targets)} targets")
    print("\n💡 Tip: Use --full to see complete values")
    print("💡 Tip: Use --format json for machine-readable output\n")


def _output_json(targets, output: Optional[str], full: bool = False):
    """Output as JSON"""
    data = []
    for target in targets:
        item = {
            'id': target.id,
            'type': target.type,
            'filesystem_export': target.filesystem_export,
            'filesystem_export_mount_path': target.filesystem_export_mount_path,
            'status': target.status,
            'created_at': target.created_at.isoformat() if target.created_at else None,
            'updated_at': target.updated_at.isoformat() if target.updated_at else None,
            'deleted': target.deleted,
        }
        if target.secret_ref:
            item['secret_ref'] = target.secret_ref
        data.append(item)
    
    json_output = json.dumps(data, indent=2)
    
    if output:
        with open(output, 'w') as f:
            f.write(json_output)
        print(f"✅ Output written to {output}")
    else:
        print(json_output)


def _output_yaml(targets, output: Optional[str], full: bool = False):
    """Output as YAML"""
    try:
        import yaml
    except ImportError:
        print("❌ PyYAML not installed. Install with: pip install pyyaml")
        return
    
    data = []
    for target in targets:
        item = {
            'id': target.id,
            'type': target.type,
            'filesystem_export': target.filesystem_export,
            'filesystem_export_mount_path': target.filesystem_export_mount_path,
            'status': target.status,
            'created_at': target.created_at.isoformat() if target.created_at else None,
            'updated_at': target.updated_at.isoformat() if target.updated_at else None,
            'deleted': target.deleted,
        }
        if target.secret_ref:
            item['secret_ref'] = target.secret_ref
        data.append(item)
    
    yaml_output = yaml.dump(data, default_flow_style=False, sort_keys=False)
    
    if output:
        with open(output, 'w') as f:
            f.write(yaml_output)
        print(f"✅ Output written to {output}")
    else:
        print(yaml_output)


def _output_csv_targets(targets, output: Optional[str], full: bool = False):
    """Output as CSV"""
    import csv
    from io import StringIO
    
    output_buffer = StringIO() if not output else None
    
    fieldnames = ['id', 'type', 'filesystem_export', 'filesystem_export_mount_path', 
                  'status', 'secret_ref', 'created_at', 'updated_at']
    
    if output:
        with open(output, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for target in targets:
                writer.writerow({
                    'id': target.id,
                    'type': target.type,
                    'filesystem_export': target.filesystem_export,
                    'filesystem_export_mount_path': target.filesystem_export_mount_path,
                    'status': target.status,
                    'secret_ref': target.secret_ref or '',
                    'created_at': target.created_at.isoformat() if target.created_at else '',
                    'updated_at': target.updated_at.isoformat() if target.updated_at else '',
                })
        print(f"✅ Output written to {output}")
    else:
        writer = csv.DictWriter(output_buffer, fieldnames=fieldnames)
        writer.writeheader()
        for target in targets:
            writer.writerow({
                'id': target.id,
                'type': target.type,
                'filesystem_export': target.filesystem_export,
                'filesystem_export_mount_path': target.filesystem_export_mount_path,
                'status': target.status,
                'secret_ref': target.secret_ref or '',
                'created_at': target.created_at.isoformat() if target.created_at else '',
                'updated_at': target.updated_at.isoformat() if target.updated_at else '',
            })
        print(output_buffer.getvalue())

def list_mounts(config: DMSConfig, format: str = 'table',
               output: Optional[str] = None, full: bool = False):
    """List active mount ledger entries with formatting"""
    initialize_database(config)
    session = get_session()
    
    try:
        ledgers = session.query(
            BackupTargetMountLedger,
            Job
        ).join(
            Job, BackupTargetMountLedger.jobid == Job.jobid
        ).filter(
            BackupTargetMountLedger.deleted == False
        ).all()
        
        if format == 'json':
            _output_mounts_json(ledgers, output)
        elif format == 'yaml':
            _output_mounts_yaml(ledgers, output)
        elif format == 'csv':
            _output_mounts_csv(ledgers, output)
        else:  # table
            _output_table_mounts(session, ledgers, full)
        
    finally:
        session.close()

def _output_table_mounts(session, ledgers, full: bool = False):
    """Output mounts as formatted table"""
    if not ledgers:
        print("\n📭 No active mounts found")
        return
    
    print("\n" + "="*140)
    print("Active Mount Ledger Entries")
    print("="*140)
    
    if full:
        print(f"{'ID':<8} {'Target ID':<40} {'Job ID':<10} {'Host':<25} {'Job Status':<12} {'Mounted':<8}")
        print("-"*140)
        
        for ledger, job in ledgers:
            mounted_str = "✓" if ledger.mounted else "✗"
            print(f"{ledger.id:<8} "
                  f"{ledger.backup_target_id:<40} "
                  f"{ledger.jobid:<10} "
                  f"{ledger.host:<25} "
                  f"{job.status:<12} "
                  f"{mounted_str:<8}")
    else:
        print(f"{'ID':<8} {'Target ID':<22} {'Job ID':<10} {'Host':<20} {'Job Status':<12} {'Mounted':<8}")
        print("-"*140)
        
        for ledger, job in ledgers:
            mounted_str = "✓" if ledger.mounted else "✗"
            target_id = _truncate(ledger.backup_target_id, 20)
            host = _truncate(ledger.host, 18)
            
            print(f"{ledger.id:<8} "
                  f"{target_id:<22} "
                  f"{ledger.jobid:<10} "
                  f"{host:<20} "
                  f"{job.status:<12} "
                  f"{mounted_str:<8}")
    
    print(f"\nTotal: {len(ledgers)} active entries")
    
    # Summary by target
    from sqlalchemy import func
    summary = session.query(
        BackupTargetMountLedger.backup_target_id,
        BackupTargetMountLedger.host,
        func.count(BackupTargetMountLedger.id).label('count'),
        func.max(BackupTargetMountLedger.mounted).label('mounted')
    ).filter(
        BackupTargetMountLedger.deleted == False
    ).group_by(
        BackupTargetMountLedger.backup_target_id,
        BackupTargetMountLedger.host
    ).all()
    
    if summary:
        print("\n" + "="*100)
        print("Summary by Target")
        print("="*100)
        
        if full:
            print(f"{'Target ID':<40} {'Host':<25} {'Active Jobs':<12} {'Mounted':<8}")
            print("-"*100)
            for target_id, host, count, mounted in summary:
                mounted_str = "✓" if mounted else "✗"
                print(f"{target_id:<40} {host:<25} {count:<12} {mounted_str:<8}")
        else:
            print(f"{'Target ID':<30} {'Host':<20} {'Active Jobs':<12} {'Mounted':<8}")
            print("-"*100)
            for target_id, host, count, mounted in summary:
                mounted_str = "✓" if mounted else "✗"
                target_display = _truncate(target_id, 28)
                host_display = _truncate(host, 18)
                print(f"{target_display:<30} {host_display:<20} {count:<12} {mounted_str:<8}")
    
    print("\n💡 Tip: Use --full to see complete values")
    print("💡 Tip: Use --format json for machine-readable output\n")

def _output_mounts_json(ledgers, output: Optional[str]):
    """Output mounts as JSON"""
    data = []
    for ledger, job in ledgers:
        data.append({
            'ledger_id': ledger.id,
            'backup_target_id': ledger.backup_target_id,
            'jobid': ledger.jobid,
            'host': ledger.host,
            'mounted': ledger.mounted,
            'job_status': job.status,
            'job_action': job.action,
            'job_progress': job.progress,
            'created_at': ledger.created_at.isoformat() if ledger.created_at else None,
        })
    
    json_output = json.dumps(data, indent=2)
    
    if output:
        with open(output, 'w') as f:
            f.write(json_output)
        print(f"✅ Output written to {output}")
    else:
        print(json_output)


def _output_mounts_yaml(ledgers, output: Optional[str]):
    """Output mounts as YAML"""
    try:
        import yaml
    except ImportError:
        print("❌ PyYAML not installed. Install with: pip install pyyaml")
        return
    
    data = []
    for ledger, job in ledgers:
        data.append({
            'ledger_id': ledger.id,
            'backup_target_id': ledger.backup_target_id,
            'jobid': ledger.jobid,
            'host': ledger.host,
            'mounted': ledger.mounted,
            'job_status': job.status,
            'job_action': job.action,
            'job_progress': job.progress,
            'created_at': ledger.created_at.isoformat() if ledger.created_at else None,
        })
    
    yaml_output = yaml.dump(data, default_flow_style=False, sort_keys=False)
    
    if output:
        with open(output, 'w') as f:
            f.write(yaml_output)
        print(f"✅ Output written to {output}")
    else:
        print(yaml_output)


def _output_mounts_csv(ledgers, output: Optional[str]):
    """Output mounts as CSV"""
    import csv
    from io import StringIO
    
    fieldnames = ['ledger_id', 'backup_target_id', 'jobid', 'host', 'mounted',
                  'job_status', 'job_action', 'job_progress', 'created_at']
    
    if output:
        with open(output, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for ledger, job in ledgers:
                writer.writerow({
                    'ledger_id': ledger.id,
                    'backup_target_id': ledger.backup_target_id,
                    'jobid': ledger.jobid,
                    'host': ledger.host,
                    'mounted': ledger.mounted,
                    'job_status': job.status,
                    'job_action': job.action,
                    'job_progress': job.progress,
                    'created_at': ledger.created_at.isoformat() if ledger.created_at else '',
                })
        print(f"✅ Output written to {output}")
    else:
        output_buffer = StringIO()
        writer = csv.DictWriter(output_buffer, fieldnames=fieldnames)
        writer.writeheader()
        for ledger, job in ledgers:
            writer.writerow({
                'ledger_id': ledger.id,
                'backup_target_id': ledger.backup_target_id,
                'jobid': ledger.jobid,
                'host': ledger.host,
                'mounted': ledger.mounted,
                'job_status': job.status,
                'job_action': job.action,
                'job_progress': job.progress,
                'created_at': ledger.created_at.isoformat() if ledger.created_at else '',
            })
        print(output_buffer.getvalue())

def show_target(config: DMSConfig, target_id: str, format: str = 'text',
               output: Optional[str] = None):
    """Show target details including NFS mount options"""
    from trilio_dms.models import initialize_database, get_session, BackupTarget
    
    initialize_database(config)
    session = get_session()
    
    try:
        target = session.query(BackupTarget).filter_by(id=target_id).first()
        
        if not target:
            print(f"❌ Target {target_id} not found")
            return
        
        if format == 'text':
            print("\n" + "="*80)
            print(f"Target Details")
            print("="*80)
            print(f"ID:                  {target.id}")
            print(f"Type:                {target.type}")
            print(f"Export:              {target.filesystem_export}")
            print(f"Mount Path:          {target.filesystem_export_mount_path}")
            print(f"Status:              {target.status}")
            
            # Show NFS mount options if NFS type
            if target.type == 'nfs' and target.nfs_mount_opts:
                print(f"NFS Mount Options:   {target.nfs_mount_opts}")
            
            print(f"Created:             {target.created_at}")
            print(f"Updated:             {target.updated_at}")
            
            if target.secret_ref:
                print(f"Secret Ref:          {target.secret_ref}")
        
        elif format == 'json':
            data = {
                'id': target.id,
                'type': target.type,
                'filesystem_export': target.filesystem_export,
                'filesystem_export_mount_path': target.filesystem_export_mount_path,
                'status': target.status,
                'nfs_mount_opts': target.nfs_mount_opts,
                'secret_ref': target.secret_ref,
                'created_at': target.created_at.isoformat() if target.created_at else None,
                'updated_at': target.updated_at.isoformat() if target.updated_at else None,
            }
            print(json.dumps(data, indent=2))
        
    finally:
        session.close()

def _output_target_text(target, session):
    """Output target as formatted text"""
    print("\n" + "="*80)
    print(f"Target Details")
    print("="*80)
    print(f"ID:                  {target.id}")
    print(f"Type:                {target.type}")
    print(f"Export:              {target.filesystem_export}")
    print(f"Mount Path:          {target.filesystem_export_mount_path}")
    print(f"Status:              {target.status}")
    print(f"Created:             {target.created_at}")
    print(f"Updated:             {target.updated_at}")
    print(f"Deleted:             {target.deleted}")
    
    if target.secret_ref:
        print(f"Secret Ref:          {target.secret_ref}")
    
    # Active mounts
    active_ledgers = session.query(BackupTargetMountLedger).filter_by(
        backup_target_id=target.id,
        deleted=False
    ).all()
    
    if active_ledgers:
        print(f"\nActive Mounts: {len(active_ledgers)}")
        for ledger in active_ledgers:
            print(f"  - Job {ledger.jobid} on {ledger.host} (mounted: {ledger.mounted})")
    else:
        print("\nNo active mounts")
    print()


def _output_target_json(target, session, output: Optional[str]):
    """Output target as JSON"""
    active_ledgers = session.query(BackupTargetMountLedger).filter_by(
        backup_target_id=target.id,
        deleted=False
    ).all()
    
    data = {
        'id': target.id,
        'type': target.type,
        'filesystem_export': target.filesystem_export,
        'filesystem_export_mount_path': target.filesystem_export_mount_path,
        'status': target.status,
        'secret_ref': target.secret_ref,
        'created_at': target.created_at.isoformat() if target.created_at else None,
        'updated_at': target.updated_at.isoformat() if target.updated_at else None,
        'deleted': target.deleted,
        'active_mounts': [
            {
                'ledger_id': ledger.id,
                'jobid': ledger.jobid,
                'host': ledger.host,
                'mounted': ledger.mounted
            }
            for ledger in active_ledgers
        ]
    }
    
    json_output = json.dumps(data, indent=2)
    
    if output:
        with open(output, 'w') as f:
            f.write(json_output)
        print(f"✅ Output written to {output}")
    else:
        print(json_output)


def _output_target_yaml(target, session, output: Optional[str]):
    """Output target as YAML"""
    try:
        import yaml
    except ImportError:
        print("❌ PyYAML not installed. Install with: pip install pyyaml")
        return
    
    active_ledgers = session.query(BackupTargetMountLedger).filter_by(
        backup_target_id=target.id,
        deleted=False
    ).all()
    
    data = {
        'id': target.id,
        'type': target.type,
        'filesystem_export': target.filesystem_export,
        'filesystem_export_mount_path': target.filesystem_export_mount_path,
        'status': target.status,
        'secret_ref': target.secret_ref,
        'created_at': target.created_at.isoformat() if target.created_at else None,
        'updated_at': target.updated_at.isoformat() if target.updated_at else None,
        'deleted': target.deleted,
        'active_mounts': [
            {
                'ledger_id': ledger.id,
                'jobid': ledger.jobid,
                'host': ledger.host,
                'mounted': ledger.mounted
            }
            for ledger in active_ledgers
        ]
    }
    
    yaml_output = yaml.dump(data, default_flow_style=False, sort_keys=False)
    
    if output:
        with open(output, 'w') as f:
            f.write(yaml_output)
        print(f"✅ Output written to {output}")
    else:
        print(yaml_output)

def _truncate(text: str, max_len: int, suffix: str = '..') -> str:
    """Truncate text to max length with suffix"""
    if len(text) <= max_len:
        return text
    return text[:max_len - len(suffix)] + suffix


def delete_target(config: DMSConfig, target_id: str):
    """Delete a target"""
    initialize_database(config)
    session = get_session()
    
    try:
        target = session.query(BackupTarget).filter_by(id=target_id).first()
        
        if not target:
            print(f"❌ Target {target_id} not found")
            return
        
        # Check for active mounts
        active_mounts = session.query(BackupTargetMountLedger).filter_by(
            backup_target_id=target_id,
            deleted=False
        ).count()
        
        if active_mounts > 0:
            print(f"⚠️  Warning: Target has {active_mounts} active mount(s)")
            print("   Deleting the target will not unmount active mounts.")
            print("   Please ensure all jobs using this target are completed first.")
        
        target.deleted = True
        target.deleted_at = datetime.utcnow()
        session.commit()
        print(f"✅ Target '{target.name}' deleted")
            
    except Exception as e:
        print(f"❌ Error deleting target: {e}")
        session.rollback()
    finally:
        session.close()


def cleanup_stale_ledgers(config: DMSConfig):
    """Clean up ledger entries for completed/failed jobs"""
    initialize_database(config)
    session = get_session()
    
    try:
        # Find ledger entries with completed/failed/canceled jobs
        terminal_statuses = ['COMPLETED', 'FAILED', 'CANCELED', 'ERROR']
        
        stale_ledgers = session.query(BackupTargetMountLedger).join(
            Job, BackupTargetMountLedger.jobid == Job.jobid
        ).filter(
            BackupTargetMountLedger.deleted == False,
            Job.status.in_(terminal_statuses)
        ).all()
        
        print(f"\n📋 Found {len(stale_ledgers)} stale ledger entries")
        
        if stale_ledgers:
            # Show details
            print("\nStale entries:")
            for ledger in stale_ledgers[:10]:  # Show first 10
                job = session.query(Job).filter_by(jobid=ledger.jobid).first()
                print(f"  - Ledger {ledger.id}: Job {ledger.jobid} ({job.status}) on {ledger.host}")
            
            if len(stale_ledgers) > 10:
                print(f"  ... and {len(stale_ledgers) - 10} more")
            
            confirm = input("\nMark these entries as deleted? (yes/no): ").strip().lower()
            if confirm == 'yes':
                for ledger in stale_ledgers:
                    ledger.deleted = True
                    ledger.deleted_at = datetime.utcnow()
                
                session.commit()
                print(f"✅ Cleaned up {len(stale_ledgers)} stale entries")
            else:
                print("❌ Cancelled")
        else:
            print("✨ No stale entries found")
        
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        session.rollback()
    finally:
        session.close()


def test_mount(config: DMSConfig, target_id: str, job_id: int, node_id: str):
    """Test mount operation"""
    # Get authentication
    print("\n🔐 Authentication Required")
    print("-" * 40)
    username = input("Username: ").strip()
    password = input("Password: ").strip()
    project_name = input("Project [admin]: ").strip() or 'admin'
    
    try:
        auth = v3.Password(
            auth_url=config.auth_url,
            username=username,
            password=password,
            project_name=project_name,
            user_domain_name='Default',
            project_domain_name='Default'
        )
        sess = ks_session.Session(auth=auth)
        token = sess.get_token()
        
        print("✅ Authentication successful\n")
        
        # Test mount
        print(f"🔧 Testing mount for target {target_id}...")
        with DMSClient(config) as client:
            response = client.mount(job_id, target_id, token, node_id)
            
            print(f"\n📤 Mount Response:")
            print(json.dumps(response, indent=2))
            
            if response.get('success'):
                print(f"\n✅ Mount successful at: {response.get('mount_path')}")
                input("\n⏸  Press Enter to unmount...")
                
                print(f"\n🔧 Testing unmount...")
                response = client.unmount(job_id, target_id, node_id)
                print(f"\n📤 Unmount Response:")
                print(json.dumps(response, indent=2))
                
                if response.get('success'):
                    print("\n✅ Unmount successful")
            else:
                print(f"\n❌ Mount failed: {response.get('message')}")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")


def show_status(config: DMSConfig):
    """Show DMS service status"""
    import subprocess
    
    print("\n" + "="*60)
    print("DMS Service Status")
    print("="*60)
    
    try:
        result = subprocess.run(
            ['systemctl', 'status', 'trilio-dms'],
            capture_output=True,
            text=True
        )
        print(result.stdout)
    except FileNotFoundError:
        print("❌ systemctl not found (not running on systemd)")
    except Exception as e:
        print(f"❌ Could not get service status: {e}")


def show_config(config: DMSConfig):
    """Display current configuration"""
    print("\n" + "="*60)
    print("Current Configuration")
    print("="*60)
    print(f"Database URL:     {config.db_url}")
    print(f"RabbitMQ URL:     {config.rabbitmq_url}")
    print(f"Auth URL:         {config.auth_url}")
    print(f"Node ID:          {config.node_id}")
    print(f"Log Level:        {config.log_level}")
    print(f"Mount Base:       {config.mount_base_path}")
    print(f"S3 PID Dir:       {config.s3_pidfile_dir}")
    print(f"Mount Timeout:    {config.mount_timeout}s")
    print(f"Operation Timeout: {config.operation_timeout}s")
    print(f"Verify SSL:       {config.verify_ssl}")


def validate_target(config: DMSConfig, target_id: str):
    """Validate target configuration"""
    initialize_database(config)
    session = get_session()
    
    try:
        target = session.query(BackupTarget).filter_by(id=target_id).first()
        
        if not target:
            print(f"❌ Target {target_id} not found")
            return
        
        print(f"\n🔍 Validating target: {target.filesystem_export}")
        print("="*60)
        
        errors = []
        warnings = []
        
        # Validate mount path
        if not validate_mount_path(target.filesystem_export_mount_path):
            errors.append(f"Invalid mount path: {target.filesystem_export_mount_path}")
        
        # Validate by type
        if target.type == 'nfs':
            if not validate_nfs_share(target.filesystem_export):
                errors.append(f"Invalid NFS share format: {target.filesystem_export}")
                
        elif target.type == 's3':
            if not validate_s3_bucket(target.filesystem_export):
                errors.append(f"Invalid S3 bucket name: {target.filesystem_export}")
            if not target.secret_ref:
                errors.append("Missing secret_ref for S3 target")
        
        # Check status
        if target.status not in ['available', 'error', 'creating', 'deleting']:
            warnings.append(f"Unusual status: {target.status}")
        
        # Check if mount path exists
        import os
        if not os.path.exists(target.filesystem_export_mount_path):
            warnings.append(f"Mount path does not exist: {target.filesystem_export_mount_path}")
        
        # Display results
        if errors:
            print("\n❌ Errors found:")
            for error in errors:
                print(f"   - {error}")
        
        if warnings:
            print("\n⚠️  Warnings:")
            for warning in warnings:
                print(f"   - {warning}")
        
        if not errors and not warnings:
            print("\n✅ Target configuration is valid")
        
    finally:
        session.close()


def export_config(config: DMSConfig, output: str, format: str):
    """Export configuration"""
    if format.lower() == 'json':
        config_dict = {
            'db_url': config.db_url,
            'rabbitmq_url': config.rabbitmq_url,
            'auth_url': config.auth_url,
            'node_id': config.node_id,
            'log_level': config.log_level,
            'mount_base_path': config.mount_base_path,
            's3_pidfile_dir': config.s3_pidfile_dir,
            'mount_timeout': config.mount_timeout,
            'operation_timeout': config.operation_timeout,
            'verify_ssl': config.verify_ssl
        }
        output_text = json.dumps(config_dict, indent=2)
        
    elif format.lower() == 'yaml':
        try:
            import yaml
            config_dict = {
                'db_url': config.db_url,
                'rabbitmq_url': config.rabbitmq_url,
                'auth_url': config.auth_url,
                'node_id': config.node_id,
                'log_level': config.log_level,
                'mount_base_path': config.mount_base_path,
                's3_pidfile_dir': config.s3_pidfile_dir,
                'mount_timeout': config.mount_timeout,
                'operation_timeout': config.operation_timeout,
                'verify_ssl': config.verify_ssl
            }
            output_text = yaml.dump(config_dict, default_flow_style=False)
        except ImportError:
            print("❌ PyYAML not installed. Install with: pip install pyyaml")
            return
            
    elif format.lower() == 'env':
        output_text = f"""# Trilio DMS Configuration
DMS_DB_URL={config.db_url}
DMS_RABBITMQ_URL={config.rabbitmq_url}
DMS_AUTH_URL={config.auth_url}
DMS_NODE_ID={config.node_id}
DMS_LOG_LEVEL={config.log_level}
DMS_MOUNT_BASE={config.mount_base_path}
DMS_S3_PIDFILE_DIR={config.s3_pidfile_dir}
DMS_MOUNT_TIMEOUT={config.mount_timeout}
DMS_OPERATION_TIMEOUT={config.operation_timeout}
DMS_VERIFY_SSL={str(config.verify_ssl).lower()}
"""
    
    if output:
        with open(output, 'w') as f:
            f.write(output_text)
        print(f"✅ Configuration exported to {output}")
    else:
        print(output_text)


def generate_systemd_service(config: DMSConfig, output_file: str):
    """Generate systemd service file"""
    template = f"""[Unit]
Description=Trilio Dynamic Mount Service
After=network.target rabbitmq-server.service mysql.service
Wants=rabbitmq-server.service mysql.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/trilio/dms

Environment="DMS_DB_URL={config.db_url}"
Environment="DMS_RABBITMQ_URL={config.rabbitmq_url}"
Environment="DMS_AUTH_URL={config.auth_url}"
Environment="DMS_NODE_ID={config.node_id}"
Environment="DMS_LOG_LEVEL={config.log_level}"

ExecStart=/usr/bin/python3 -m trilio_dms.server.dms_server \\
    --db-url $DMS_DB_URL \\
    --rabbitmq-url $DMS_RABBITMQ_URL \\
    --auth-url $DMS_AUTH_URL \\
    --node-id $DMS_NODE_ID \\
    --log-level $DMS_LOG_LEVEL

# KillMode=process ensures child FUSE processes survive DMS restart
KillMode=process
Restart=always
RestartSec=10

# Resource limits
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
"""
    
    try:
        with open(output_file, 'w') as f:
            f.write(template)
        
        print(f"✅ Service file created: {output_file}")
        print("\nNext steps:")
        print("  1. systemctl daemon-reload")
        print("  2. systemctl enable trilio-dms")
        print("  3. systemctl start trilio-dms")
        print("  4. systemctl status trilio-dms")
        
    except Exception as e:
        print(f"❌ Failed to create service file: {e}")


"""Additional CLI commands to add to commands.py"""

def test_secret(config: DMSConfig, secret_ref: str, token: Optional[str] = None):
    """Test secret retrieval from Barbican"""
    from trilio_dms.services.secret_manager import SecretManager
    
    # Get token if not provided
    if not token:
        print("\n🔐 Authentication Required")
        print("-" * 40)
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        project_name = input("Project [admin]: ").strip() or 'admin'
        
        auth_url = getattr(config, 'auth_url', None)
        if not auth_url:
            auth_url = input("Auth URL: ").strip()
        
        try:
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
            print("✅ Authentication successful\n")
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return
    
    # Initialize SecretManager
    secret_config = {'verify_ssl': getattr(config, 'verify_ssl', False)}
    secret_manager = SecretManager(secret_config)
    
    print("\n" + "="*60)
    print("Testing Secret Access")
    print("="*60)
    print(f"Secret Ref: {secret_ref}")
    print(f"Token: {token[:20]}...")
    print()
    
    try:
        # Test access
        print("Step 1: Testing secret access...")
        test_result = secret_manager.test_secret_access(secret_ref, token)
        
        if not test_result['metadata_accessible']:
            print("❌ Cannot access secret metadata")
            if test_result.get('error'):
                print(f"   Error: {test_result['error']}")
            print("\nPossible causes:")
            print("  - Invalid secret reference URL")
            print("  - Token expired or invalid")
            print("  - Token not project-scoped")
            print("  - No permission to access secret")
            return
        
        print("✅ Secret metadata accessible")
        
        if not test_result['payload_accessible']:
            print("❌ Cannot access secret payload")
            if test_result.get('error'):
                print(f"   Error: {test_result['error']}")
            return
        
        print("✅ Secret payload accessible")
        print()
        
        # Retrieve credentials
        print("Step 2: Retrieving credentials...")
        credentials = secret_manager.retrieve_credentials(secret_ref, token)
        
        print("✅ Successfully retrieved credentials")
        print()
        
        # Display credentials (mask sensitive data)
        print("Credential keys:")
        for key in sorted(credentials.keys()):
            value = credentials[key]
            
            # Mask sensitive values
            if any(sensitive in key.lower() for sensitive in ['key', 'secret', 'password', 'token']):
                if isinstance(value, str) and len(value) > 8:
                    masked_value = value[:4] + '*' * (len(value) - 8) + value[-4:]
                else:
                    masked_value = '****'
                print(f"  {key}: {masked_value}")
            else:
                # Show full value for non-sensitive keys
                display_value = str(value)
                if len(display_value) > 80:
                    display_value = display_value[:77] + '...'
                print(f"  {key}: {display_value}")
        
        print()
        
        # Check for required S3 credentials
        required_s3_keys = ['access_key', 'secret_key', 'vault_s3_bucket']
        missing_keys = [key for key in required_s3_keys if key not in credentials]
        
        if missing_keys:
            print(f"⚠ Warning: Missing required S3 keys: {', '.join(missing_keys)}")
        else:
            print("✅ All required S3 credentials present")
        
        # Check if vault_data_directory is in secret
        if 'vault_data_directory' in credentials:
            print()
            print(f"⚠ Note: vault_data_directory found in secret: {credentials['vault_data_directory']}")
            print("  The system will use filesystem_export_mount_path from database instead.")
            print("  This value will be overridden during mount.")
        
        print()
        print("✅ Secret test completed successfully")
        
    except Exception as e:
        LOG.error(f"Secret test failed: {e}", exc_info=True)
        print(f"❌ Secret test failed: {e}")


def test_s3_mount(config: DMSConfig, target_id: str, token: Optional[str] = None):
    """Test S3 mount operation"""
    from trilio_dms.services.mount_service import MountService
    
    # Get token if not provided
    if not token:
        print("\n🔐 Authentication Required")
        print("-" * 40)
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        project_name = input("Project [admin]: ").strip() or 'admin'
        
        auth_url = getattr(config, 'auth_url', None)
        if not auth_url:
            auth_url = input("Auth URL: ").strip()
        
        try:
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
            print("✅ Authentication successful\n")
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return
    
    initialize_database(config)
    session = get_session()
    
    try:
        # Get target
        target = session.query(BackupTarget).filter_by(
            id=target_id,
            deleted=False
        ).first()
        
        if not target:
            print(f"❌ Target {target_id} not found")
            return
        
        if target.type != 's3':
            print(f"❌ Target is not S3 type (found: {target.type})")
            return
        
        print("\n" + "="*60)
        print(f"Testing S3 Mount: {target.name}")
        print("="*60)
        print(f"Target ID:   {target.id}")
        print(f"S3 Bucket:   {target.filesystem_export}")
        print(f"Mount Path:  {target.filesystem_export_mount_path}")
        print(f"Secret Ref:  {target.secret_ref}")
        print()
        
        # Initialize mount service
        mount_service = MountService(config)
        
        # Test mount
        test_job_id = 999999
        print(f"Attempting mount (test job ID: {test_job_id})...")
        
        result = mount_service.mount(
            job_id=test_job_id,
            target_id=target_id,
            keystone_token=token
        )
        
        if result.get('success'):
            print("✅ Mount successful")
            print(f"   Mount Path: {result.get('mount_path')}")
            print()
            
            # Check if files are accessible
            import os
            mount_path = result.get('mount_path')
            if os.path.exists(mount_path):
                try:
                    files = os.listdir(mount_path)
                    print(f"✅ Mount point accessible")
                    print(f"   Files found: {len(files)}")
                    if files:
                        print(f"   Sample: {files[:5]}")
                except Exception as e:
                    print(f"⚠ Warning: Could not list files: {e}")
            
            print()
            
            # Check s3vaultfuse process
            import subprocess
            try:
                ps_result = subprocess.run(
                    ['ps', 'aux'],
                    capture_output=True,
                    text=True
                )
                for line in ps_result.stdout.split('\n'):
                    if 's3vaultfuse' in line and mount_path in line:
                        print(f"✅ s3vaultfuse process running")
                        print(f"   {line.strip()}")
                        break
            except:
                pass
            
            print()
            
            # Prompt to unmount
            unmount = input("Unmount now? (yes/no) [yes]: ").strip().lower()
            unmount = unmount if unmount else 'yes'
            
            if unmount == 'yes':
                print("\nUnmounting...")
                unmount_result = mount_service.unmount(
                    job_id=test_job_id,
                    target_id=target_id
                )
                
                if unmount_result.get('success'):
                    print("✅ Unmount successful")
                else:
                    print(f"❌ Unmount failed: {unmount_result.get('message')}")
            else:
                print("\n⚠ Note: Remember to unmount manually:")
                print(f"   trilio-dms-cli unmount --job-id {test_job_id} --target-id {target_id}")
        else:
            print(f"❌ Mount failed: {result.get('message')}")
            print("\nTroubleshooting:")
            print("  1. Check secret credentials are correct")
            print("  2. Verify s3vaultfuse is installed: which /usr/bin/s3vaultfuse.py")
            print("  3. Check logs: tail -f /var/log/trilio_dms/service.log")
            print("  4. Test secret access: trilio-dms-cli test-secret <secret_ref>")
    
    except Exception as e:
        LOG.error(f"S3 mount test failed: {e}", exc_info=True)
        print(f"❌ Test failed: {e}")
    finally:
        session.close()


def show_reconciliation_status(config: DMSConfig, format: str = 'text'):
    """Show reconciliation status"""
    from trilio_dms.services.mount_service import MountService
    from trilio_dms.services.reconciliation import ReconciliationService
    
    try:
        # Initialize services
        mount_service = MountService(config)
        reconciliation_service = ReconciliationService(config, mount_service)
        
        # Get status
        status = reconciliation_service.get_reconciliation_status()
        
        if format == 'json':
            print(json.dumps(status, indent=2))
        else:
            # Text format
            print("\n" + "="*80)
            print(f"Reconciliation Status - Node: {status['node_id']}")
            print("="*80)
            print()
            
            # NFS mounts
            if status['nfs_mounts']:
                print(f"NFS Mounts ({len(status['nfs_mounts'])})")
                print("-" * 80)
                for mount in status['nfs_mounts']:
                    mounted_icon = "✓" if mount['is_mounted'] else "✗"
                    print(f"  [{mounted_icon}] {_truncate(mount['target_id'], 40)}")
                    print(f"      Path: {mount['mount_path']}")
                    print(f"      Active Jobs: {mount['active_jobs']}")
                    print()
            
            # S3 mounts
            if status['s3_mounts']:
                print(f"S3 Mounts ({len(status['s3_mounts'])})")
                print("-" * 80)
                for mount in status['s3_mounts']:
                    mounted_icon = "✓" if mount['is_mounted'] else "✗"
                    print(f"  [{mounted_icon}] {_truncate(mount['target_id'], 40)}")
                    print(f"      Path: {mount['mount_path']}")
                    print(f"      Active Jobs: {mount['active_jobs']}")
                    if mount.get('process_info'):
                        pi = mount['process_info']
                        print(f"      Process: PID {pi.get('pid')} - {pi.get('status')}")
                    print()
            
            # Inconsistencies
            if status['inconsistencies']:
                print(f"⚠ Inconsistencies ({len(status['inconsistencies'])})")
                print("-" * 80)
                for issue in status['inconsistencies']:
                    print(f"  {issue['target_id']} ({issue['type']})")
                    print(f"    Issue: {issue['issue']}")
                    print(f"    Active Jobs: {issue['active_jobs']}")
                    print(f"    Mounted: {issue['is_mounted']}")
                    print()
            else:
                print("✅ No inconsistencies found")
            
            print()
    
    except Exception as e:
        LOG.error(f"Failed to get reconciliation status: {e}", exc_info=True)
        print(f"❌ Error: {e}")


def run_reconciliation(config: DMSConfig):
    """Run reconciliation manually"""
    from trilio_dms.services.mount_service import MountService
    from trilio_dms.services.reconciliation import ReconciliationService
    
    print("\n" + "="*60)
    print("Running Reconciliation")
    print("="*60)
    print()
    
    try:
        # Initialize services
        mount_service = MountService(config)
        reconciliation_service = ReconciliationService(config, mount_service)
        
        # Run reconciliation
        reconciliation_service.reconcile_on_startup()
        
        print("✅ Reconciliation completed")
        print()
        
        # Show status
        status = reconciliation_service.get_reconciliation_status()
        
        # Summary
        print("Summary:")
        print(f"  NFS Mounts: {len(status['nfs_mounts'])}")
        print(f"  S3 Mounts: {len(status['s3_mounts'])}")
        
        if status['inconsistencies']:
            print(f"  ⚠ Inconsistencies: {len(status['inconsistencies'])}")
            for issue in status['inconsistencies']:
                print(f"    - {issue['target_id']}: {issue['issue']}")
        else:
            print("  ✅ No inconsistencies")
        
        print()
    
    except Exception as e:
        LOG.error(f"Reconciliation failed: {e}", exc_info=True)
        print(f"❌ Error: {e}")

def detect_stale_mounts(config: DMSConfig):
    """Detect stale mounts"""
    from trilio_dms.drivers import NFSDriver, S3Driver
    
    initialize_database(config)
    session = get_session()
    
    print("\n" + "="*80)
    print("Detecting Stale Mounts")
    print("="*80)
    print()
    
    nfs_driver = NFSDriver()
    s3_config = {
        's3vaultfuse_path': getattr(config, 's3_vaultfuse_path', '/usr/bin/s3vaultfuse.py'),
        'default_log_config': getattr(config, 's3_log_config', '/etc/triliovault-object-store/object_store_logging.conf'),
        'default_data_directory': getattr(config, 's3_data_directory', '/var/lib/trilio/triliovault-mounts')
    }
    s3_driver = S3Driver(s3_config)
    
    stale_mounts = []
    
    try:
        # Get all targets
        targets = session.query(BackupTarget).filter_by(deleted=False).all()
        
        print(f"Checking {len(targets)} target(s)...\n")
        
        for target in targets:
            mount_path = target.filesystem_export_mount_path
            
            # Check if in /proc/mounts
            in_proc_mounts = False
            try:
                with open('/proc/mounts', 'r') as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2 and parts[1] == mount_path:
                            in_proc_mounts = True
                            break
            except:
                pass
            
            if not in_proc_mounts:
                continue
            
            # Check if accessible
            is_accessible = False
            try:
                import signal
                import os
                
                def timeout_handler(signum, frame):
                    raise TimeoutError()
                
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(2)
                
                try:
                    os.listdir(mount_path)
                    is_accessible = True
                    signal.alarm(0)
                except TimeoutError:
                    is_accessible = False
                    signal.alarm(0)
                except:
                    is_accessible = False
                    signal.alarm(0)
                finally:
                    signal.signal(signal.SIGALRM, old_handler)
            except:
                is_accessible = False
            
            if not is_accessible:
                stale_mounts.append({
                    'target_id': target.id,
                    'target_name': target.name,
                    'type': target.type,
                    'mount_path': mount_path,
                    'export': target.filesystem_export
                })
        
        if stale_mounts:
            print(f"⚠ Found {len(stale_mounts)} stale mount(s):\n")
            
            for i, mount in enumerate(stale_mounts, 1):
                print(f"{i}. Target: {mount['target_name']} ({mount['target_id']})")
                print(f"   Type: {mount['type']}")
                print(f"   Export: {mount['export']}")
                print(f"   Mount Path: {mount['mount_path']}")
                print(f"   Status: In /proc/mounts but NOT accessible")
                print()
            
            # Show cleanup options
            print("Cleanup options:")
            print("  1. Clean up all stale mounts")
            print("  2. Clean up specific mounts (enter numbers)")
            print("  3. Cancel")
            print()
            
            choice = input("Enter choice [1-3]: ").strip()
            
            if choice == '1':
                print("\nCleaning up all stale mounts...")
                for mount in stale_mounts:
                    print(f"\nCleaning up: {mount['mount_path']}")
                    if mount['type'] == 'nfs':
                        success = nfs_driver.cleanup_stale_mount(mount['mount_path'])
                    else:
                        success = s3_driver.cleanup_stale_mount(mount['mount_path'])
                    
                    if success:
                        print(f"  ✅ Cleaned up successfully")
                    else:
                        print(f"  ❌ Failed to clean up")
                
            elif choice == '2':
                indices = input("Enter mount numbers (comma-separated): ").strip()
                try:
                    nums = [int(x.strip()) for x in indices.split(',')]
                    for num in nums:
                        if 1 <= num <= len(stale_mounts):
                            mount = stale_mounts[num - 1]
                            print(f"\nCleaning up: {mount['mount_path']}")
                            if mount['type'] == 'nfs':
                                success = nfs_driver.cleanup_stale_mount(mount['mount_path'])
                            else:
                                success = s3_driver.cleanup_stale_mount(mount['mount_path'])
                            
                            if success:
                                print(f"  ✅ Cleaned up successfully")
                            else:
                                print(f"  ❌ Failed to clean up")
                except ValueError:
                    print("❌ Invalid input")
            else:
                print("Cancelled")
        else:
            print("✅ No stale mounts detected")
        
        print()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        LOG.error(f"Error detecting stale mounts: {e}", exc_info=True)
    finally:
        session.close()


def force_unmount(config: DMSConfig, mount_path: str, mount_type: str = None):
    """Force unmount a path"""
    from trilio_dms.drivers import NFSDriver, S3Driver
    
    print(f"\n⚠ Force Unmounting: {mount_path}")
    print("="*80)
    
    # Auto-detect type if not specified
    if not mount_type:
        initialize_database(config)
        session = get_session()
        try:
            target = session.query(BackupTarget).filter_by(
                filesystem_export_mount_path=mount_path,
                deleted=False
            ).first()
            if target:
                mount_type = target.type
                print(f"Detected type: {mount_type}")
            else:
                print("Could not detect type, trying both NFS and S3...")
        finally:
            session.close()
    
    success = False
    
    # Try NFS cleanup
    if not mount_type or mount_type == 'nfs':
        print("\nTrying NFS cleanup...")
        nfs_driver = NFSDriver()
        success = nfs_driver.cleanup_stale_mount(mount_path)
        if success:
            print("✅ Successfully cleaned up as NFS mount")
            return
    
    # Try S3 cleanup
    if not mount_type or mount_type == 's3':
        print("\nTrying S3 cleanup...")
        s3_config = {
            's3vaultfuse_path': getattr(config, 's3_vaultfuse_path', '/usr/bin/s3vaultfuse.py'),
            'default_log_config': getattr(config, 's3_log_config', '/etc/triliovault-object-store/object_store_logging.conf'),
            'default_data_directory': getattr(config, 's3_data_directory', '/var/lib/trilio/triliovault-mounts')
        }
        s3_driver = S3Driver(s3_config)
        success = s3_driver.cleanup_stale_mount(mount_path)
        if success:
            print("✅ Successfully cleaned up as S3 mount")
            return
    
    if not success:
        print("❌ Failed to clean up mount")
        print("\nManual cleanup may be required:")
        print(f"  sudo umount -l {mount_path}")
        print(f"  sudo fusermount -uz {mount_path}")

