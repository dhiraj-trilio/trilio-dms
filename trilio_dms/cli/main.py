"""Main CLI entry point with configuration options - Updated"""

import click
import socket
import sys
from trilio_dms.cli import commands
from trilio_dms.config import DMSConfig
from trilio_dms.utils.logger import get_logger

LOG = get_logger(__name__)


@click.group()
@click.option('--config', help='Configuration file path')
@click.option('--db-url', help='Database URL')
@click.option('--rabbitmq-url', help='RabbitMQ URL')
@click.option('--auth-url', help='Keystone authentication URL')
@click.option('--node-id', help='Node ID (defaults to hostname)')
@click.option('--log-level',
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                               case_sensitive=False),
              help='Log level')
@click.pass_context
def cli(ctx, config, db_url, rabbitmq_url, auth_url, node_id, log_level):
    """Trilio Dynamic Mount Service CLI"""
    ctx.ensure_object(dict)

    # Load configuration
    if config:
        try:
            dms_config = DMSConfig.from_file(config)
            LOG.info(f"Loaded configuration from {config}")
        except Exception as e:
            click.echo(f"Error loading config file: {e}", err=True)
            sys.exit(1)
    else:
        dms_config = DMSConfig()

    # Override with CLI arguments
    if db_url:
        dms_config.db_url = db_url
    if rabbitmq_url:
        dms_config.rabbitmq_url = rabbitmq_url
    if auth_url:
        dms_config.auth_url = auth_url
    if node_id:
        dms_config.node_id = node_id
    if log_level:
        dms_config.log_level = log_level

    ctx.obj['config'] = dms_config

    if log_level:
        import logging
        logging.getLogger('trilio_dms').setLevel(getattr(logging, log_level.upper()))


@cli.command()
@click.pass_context
def register(ctx):
    """
    Register new backup target (interactive wizard)

    Example:
      trilio-dms-cli register
      trilio-dms-cli --auth-url http://keystone:5000/v3 register
    """
    from trilio_dms.cli.wizard import BackupTargetWizard
    config = ctx.obj['config']
    wizard = BackupTargetWizard(config)
    wizard.run()


@cli.command()
@click.option('--format', '-f',
              type=click.Choice(['table', 'json', 'yaml', 'csv'], case_sensitive=False),
              default='table',
              help='Output format')
@click.option('--output', '-o',
              type=click.Path(),
              help='Output file (default: stdout)')
@click.option('--full', is_flag=True,
              help='Show full IDs and paths (no truncation)')
@click.pass_context
def list(ctx, format, output, full):
    """
    List all registered backup targets

    Examples:
      trilio-dms-cli list
      trilio-dms-cli list --format json
      trilio-dms-cli list --format table --full
      trilio-dms-cli list --format json --output targets.json
    """
    commands.list_targets(ctx.obj['config'], format, output, full)


@cli.command('list-mounts')
@click.option('--format', '-f',
              type=click.Choice(['table', 'json', 'yaml', 'csv'], case_sensitive=False),
              default='table',
              help='Output format')
@click.option('--output', '-o',
              type=click.Path(),
              help='Output file (default: stdout)')
@click.option('--full', is_flag=True,
              help='Show full IDs (no truncation)')
@click.pass_context
def list_mounts_cmd(ctx, format, output, full):
    """
    List active mount ledger entries

    Examples:
      trilio-dms-cli list-mounts
      trilio-dms-cli list-mounts --format json
      trilio-dms-cli list-mounts --full
    """
    commands.list_mounts(ctx.obj['config'], format, output, full)


@cli.command()
@click.argument('target_id')
@click.option('--format', '-f',
              type=click.Choice(['text', 'json', 'yaml'], case_sensitive=False),
              default='text',
              help='Output format')
@click.option('--output', '-o',
              type=click.Path(),
              help='Output file (default: stdout)')
@click.pass_context
def show(ctx, target_id, format, output):
    """
    Show detailed information about a target

    Examples:
      trilio-dms-cli show abc-123
      trilio-dms-cli show abc-123 --format json
      trilio-dms-cli show abc-123 --format yaml --output target.yaml
    """
    commands.show_target(ctx.obj['config'], target_id, format, output)


@cli.command()
@click.argument('target_id')
@click.confirmation_option(prompt='Are you sure you want to delete this target?')
@click.pass_context
def delete(ctx, target_id):
    """
    Delete a backup target

    Example:
      trilio-dms-cli delete abc-123-def-456
    """
    commands.delete_target(ctx.obj['config'], target_id)


@cli.command('test-mount')
@click.argument('target_id')
@click.option('--job-id', default=99999, help='Test job ID')
@click.option('--node-id', help='Node ID (overrides config)')
@click.pass_context
def test_mount_cmd(ctx, target_id, job_id, node_id):
    """
    Test mount/unmount operation for a target

    Example:
      trilio-dms-cli test-mount abc-123
      trilio-dms-cli test-mount abc-123 --job-id 123 --node-id compute-01
    """
    config = ctx.obj['config']
    node_id = node_id or config.node_id
    commands.test_mount(config, target_id, job_id, node_id)


@cli.command('test-secret')
@click.argument('secret_ref')
@click.option('--token', help='Keystone token (if not provided, will prompt for credentials)')
@click.pass_context
def test_secret_cmd(ctx, secret_ref, token):
    """
    Test secret retrieval from Barbican
    
    Example:
      trilio-dms-cli test-secret https://barbican:9311/v1/secrets/uuid
      trilio-dms-cli test-secret https://barbican:9311/v1/secrets/uuid --token <token>
    """
    from trilio_dms.cli.commands import test_secret
    test_secret(ctx.obj['config'], secret_ref, token)


@cli.command('test-s3-mount')
@click.argument('target_id')
@click.option('--token', help='Keystone token (if not provided, will prompt for credentials)')
@click.pass_context
def test_s3_mount_cmd(ctx, target_id, token):
    """
    Test S3 mount operation (retrieves credentials and mounts)
    
    Example:
      trilio-dms-cli test-s3-mount abc-123
      trilio-dms-cli test-s3-mount abc-123 --token <token>
    """
    from trilio_dms.cli.commands import test_s3_mount
    test_s3_mount(ctx.obj['config'], target_id, token)


@cli.command()
@click.pass_context
def cleanup(ctx):
    """
    Clean up stale ledger entries (completed/failed jobs)

    Example:
      trilio-dms-cli cleanup
    """
    commands.cleanup_stale_ledgers(ctx.obj['config'])


@cli.command('reconcile-status')
@click.option('--format', '-f',
              type=click.Choice(['text', 'json'], case_sensitive=False),
              default='text',
              help='Output format')
@click.pass_context
def reconcile_status_cmd(ctx, format):
    """
    Show reconciliation status
    
    Example:
      trilio-dms-cli reconcile-status
      trilio-dms-cli reconcile-status --format json
    """
    from trilio_dms.cli.commands import show_reconciliation_status
    show_reconciliation_status(ctx.obj['config'], format)


@cli.command('reconcile')
@click.pass_context
def reconcile_cmd(ctx):
    """
    Run reconciliation manually
    
    Example:
      trilio-dms-cli reconcile
    """
    from trilio_dms.cli.commands import run_reconciliation
    run_reconciliation(ctx.obj['config'])


@cli.command()
@click.pass_context
def status(ctx):
    """
    Show DMS service status

    Example:
      trilio-dms-cli status
    """
    commands.show_status(ctx.obj['config'])


@cli.command('generate-systemd')
@click.option('--output',
              default='/etc/systemd/system/trilio-dms.service',
              help='Output file path')
@click.pass_context
def generate_systemd_cmd(ctx, output):
    """
    Generate systemd service file

    Example:
      trilio-dms-cli generate-systemd
      trilio-dms-cli generate-systemd --output ./trilio-dms.service
    """
    commands.generate_systemd_service(ctx.obj['config'], output)


@cli.command('check-config')
@click.pass_context
def check_config_cmd(ctx):
    """
    Display current configuration

    Example:
      trilio-dms-cli check-config
      trilio-dms-cli --config /etc/trilio/config.json check-config
    """
    commands.show_config(ctx.obj['config'])


@cli.command('validate-target')
@click.argument('target_id')
@click.pass_context
def validate_target_cmd(ctx, target_id):
    """
    Validate target configuration and connectivity

    Example:
      trilio-dms-cli validate-target abc-123
    """
    commands.validate_target(ctx.obj['config'], target_id)


@cli.command('export-config')
@click.option('--output',
              type=click.Path(),
              help='Output file path (default: stdout)')
@click.option('--format',
              type=click.Choice(['json', 'yaml', 'env'], case_sensitive=False),
              default='json',
              help='Output format')
@click.pass_context
def export_config_cmd(ctx, output, format):
    """
    Export current configuration

    Example:
      trilio-dms-cli export-config
      trilio-dms-cli export-config --output config.json --format json
      trilio-dms-cli export-config --format env > .env
    """
    commands.export_config(ctx.obj['config'], output, format)


@cli.command('detect-stale-mounts')
@click.pass_context
def detect_stale_mounts_cmd(ctx):
    """
    Detect and clean up stale mounts
    
    Checks all registered targets and finds mounts that are:
    - Listed in /proc/mounts
    - But not actually accessible (stale/hung)
    
    Example:
      trilio-dms-cli detect-stale-mounts
    """
    from trilio_dms.cli.commands import detect_stale_mounts
    detect_stale_mounts(ctx.obj['config'])


@cli.command('force-unmount')
@click.argument('mount_path')
@click.option('--type', type=click.Choice(['nfs', 's3']), help='Mount type (auto-detected if not specified)')
@click.pass_context
def force_unmount_cmd(ctx, mount_path, type):
    """
    Force unmount a path (handles stale mounts)
    
    Example:
      trilio-dms-cli force-unmount /var/lib/trilio/triliovault-mounts/target-123
      trilio-dms-cli force-unmount /mnt/nfs/backup --type nfs
    """
    from trilio_dms.cli.commands import force_unmount
    force_unmount(ctx.obj['config'], mount_path, type)

def main():
    """Main entry point"""
    cli(obj={})


if __name__ == '__main__':
    main()
