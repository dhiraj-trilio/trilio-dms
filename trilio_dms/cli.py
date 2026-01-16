"""
Command-line interface for Trilio DMS
"""

import click
import json
import sys
from datetime import datetime
from tabulate import tabulate
from trilio_dms.client import DMSClient
from trilio_dms.config import DMSConfig


@click.group()
@click.option('--db-url', envvar='DMS_DB_URL', help='Database URL')
@click.option('--rabbitmq-url', envvar='DMS_RABBITMQ_URL', help='RabbitMQ URL')
@click.pass_context
def cli(ctx, db_url, rabbitmq_url):
    """Trilio Dynamic Mount Service CLI"""
    ctx.ensure_object(dict)
    ctx.obj['client'] = DMSClient(db_url=db_url, rabbitmq_url=rabbitmq_url)


@cli.command()
@click.option('--job-id', required=True, help='Job ID')
@click.option('--target-id', required=True, help='Backup target ID')
@click.option('--target-type', required=True, type=click.Choice(['s3', 'nfs']), help='Target type')
@click.option('--host', required=True, help='Target host/node')
@click.option('--token', envvar='KEYSTONE_TOKEN', required=True, help='Keystone token')
@click.option('--secret-ref', help='Barbican secret reference (for S3)')
@click.option('--nfs-export', help='NFS export path (for NFS)')
@click.option('--nfs-opts', default='defaults', help='NFS mount options')
@click.pass_context
def mount(ctx, job_id, target_id, target_type, host, token, secret_ref, nfs_export, nfs_opts):
    """Mount a backup target"""
    client = ctx.obj['client']
    
    # Build request
    request = {
        'context': {'user_id': 'cli-user'},
        'keystone_token': token,
        'job': {
            'jobid': job_id,
            'progress': 0,
            'status': 'running',
            'completed_at': None,
            'action': 'mount',
            'parent_jobid': None,
            'job_details': []
        },
        'host': host,
        'action': 'mount',
        'backup_target': {
            'id': target_id,
            'deleted': False,
            'type': target_type,
            'filesystem_export': nfs_export if target_type == 'nfs' else None,
            'filesystem_export_mount_path': None,
            'status': 'available',
            'secret_ref': secret_ref if target_type == 's3' else None,
            'nfs_mount_opts': nfs_opts if target_type == 'nfs' else None
        }
    }
    
    try:
        click.echo(f"Mounting {target_type} target {target_id} on {host}...")
        response = client.mount(request)
        
        if response['status'] == 'success':
            click.secho(f"✓ {response['success_msg']}", fg='green')
        else:
            click.secho(f"✗ {response['error_msg']}", fg='red')
            sys.exit(1)
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg='red')
        sys.exit(1)
    finally:
        client.close()


@cli.command()
@click.option('--job-id', required=True, help='Job ID')
@click.option('--target-id', required=True, help='Backup target ID')
@click.option('--target-type', required=True, type=click.Choice(['s3', 'nfs']), help='Target type')
@click.option('--host', required=True, help='Target host/node')
@click.option('--token', envvar='KEYSTONE_TOKEN', required=True, help='Keystone token')
@click.pass_context
def unmount(ctx, job_id, target_id, target_type, host, token):
    """Unmount a backup target"""
    client = ctx.obj['client']
    
    request = {
        'context': {'user_id': 'cli-user'},
        'keystone_token': token,
        'job': {
            'jobid': job_id,
            'progress': 0,
            'status': 'running',
            'action': 'unmount',
            'job_details': []
        },
        'host': host,
        'action': 'unmount',
        'backup_target': {
            'id': target_id,
            'type': target_type,
            'status': 'available',
            'secret_ref': None
        }
    }
    
    try:
        click.echo(f"Unmounting {target_type} target {target_id} from {host}...")
        response = client.unmount(request)
        
        if response['status'] == 'success':
            click.secho(f"✓ {response['success_msg']}", fg='green')
        else:
            click.secho(f"✗ {response['error_msg']}", fg='red')
            sys.exit(1)
    except Exception as e:
        click.secho(f"✗ Error: {e}", fg='red')
        sys.exit(1)
    finally:
        client.close()


@cli.command()
@click.option('--job-id', required=True, help='Job ID')
@click.option('--target-id', required=True, help='Backup target ID')
@click.pass_context
def status(ctx, job_id, target_id):
    """Get mount status"""
    client = ctx.obj['client']
    
    try:
        result = client.get_mount_status(job_id, target_id)
        
        if result:
            data = [
                ['ID', result.id],
                ['Job ID', result.job_id],
                ['Target ID', result.backup_target_id],
                ['Host', result.host],
                ['Action', result.action],
                ['Status', result.status],
                ['Mount Path', result.mount_path or 'N/A'],
                ['Created', result.created_at],
                ['Completed', result.completed_at or 'N/A'],
            ]
            
            if result.error_msg:
                data.append(['Error', result.error_msg])
            if result.success_msg:
                data.append(['Message', result.success_msg])
            
            click.echo(tabulate(data, tablefmt='grid'))
        else:
            click.echo("No status found")
    except Exception as e:
        click.secho(f"Error: {e}", fg='red')
        sys.exit(1)
    finally:
        client.close()


@cli.command()
@click.option('--host', help='Filter by host')
@click.option('--format', 'output_format', type=click.Choice(['table', 'json']), default='table')
@click.pass_context
def list_mounts(ctx, host, output_format):
    """List active mounts"""
    client = ctx.obj['client']
    
    try:
        mounts = client.get_active_mounts(host)
        
        if output_format == 'json':
            data = [m.to_dict() for m in mounts]
            click.echo(json.dumps(data, indent=2))
        else:
            if mounts:
                data = []
                for m in mounts:
                    data.append([
                        m.id[:8] + '...',
                        m.backup_target_id,
                        m.job_id[:12] + '...',
                        m.host,
                        m.mount_path,
                        m.created_at.strftime('%Y-%m-%d %H:%M:%S')
                    ])
                
                headers = ['ID', 'Target', 'Job', 'Host', 'Path', 'Mounted']
                click.echo(tabulate(data, headers=headers, tablefmt='grid'))
                click.echo(f"\nTotal: {len(mounts)} active mounts")
            else:
                click.echo("No active mounts found")
    except Exception as e:
        click.secho(f"Error: {e}", fg='red')
        sys.exit(1)
    finally:
        client.close()


@cli.command()
@click.option('--target-id', required=True, help='Backup target ID')
@click.option('--limit', default=20, help='Maximum entries to show')
@click.pass_context
def history(ctx, target_id, limit):
    """Show mount/unmount history for a target"""
    client = ctx.obj['client']
    
    try:
        entries = client.get_ledger_history(target_id, limit)
        
        if entries:
            data = []
            for e in entries:
                data.append([
                    e.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    e.action,
                    e.status,
                    e.job_id[:12] + '...',
                    e.host,
                    (e.success_msg or e.error_msg or '')[:40]
                ])
            
            headers = ['Time', 'Action', 'Status', 'Job', 'Host', 'Message']
            click.echo(tabulate(data, headers=headers, tablefmt='grid'))
            click.echo(f"\nTotal: {len(entries)} entries")
        else:
            click.echo("No history found")
    except Exception as e:
        click.secho(f"Error: {e}", fg='red')
        sys.exit(1)
    finally:
        client.close()


@cli.command()
@click.option('--hours', default=24, help='Age threshold in hours')
@click.pass_context
def cleanup(ctx, hours):
    """Cleanup stale pending entries"""
    client = ctx.obj['client']
    
    try:
        click.echo(f"Cleaning up entries older than {hours} hours...")
        count = client.cleanup_stale_entries(hours)
        click.secho(f"✓ Cleaned up {count} stale entries", fg='green')
    except Exception as e:
        click.secho(f"Error: {e}", fg='red')
        sys.exit(1)
    finally:
        client.close()


if __name__ == '__main__':
    cli()
