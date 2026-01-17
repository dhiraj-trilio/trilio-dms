#!/usr/bin/env python3
"""
Monitor s3vaultfuse processes
This script monitors all running s3vaultfuse processes on the server
"""

import os
import sys
import time
import argparse
import psutil
from datetime import datetime
from tabulate import tabulate


def find_s3vaultfuse_processes():
    """Find all s3vaultfuse processes"""
    processes = []
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'cpu_percent', 'memory_info']):
        try:
            cmdline = proc.info.get('cmdline', [])
            if cmdline and 's3vaultfuse' in ' '.join(cmdline):
                # Extract mount path from cmdline
                mount_path = None
                if len(cmdline) > 1:
                    mount_path = cmdline[1]
                
                # Get process stats
                create_time = datetime.fromtimestamp(proc.info['create_time'])
                uptime = datetime.now() - create_time
                
                processes.append({
                    'pid': proc.info['pid'],
                    'name': proc.info['name'],
                    'mount_path': mount_path,
                    'create_time': create_time,
                    'uptime': str(uptime).split('.')[0],  # Remove microseconds
                    'cpu_percent': proc.info.get('cpu_percent', 0),
                    'memory_mb': proc.info['memory_info'].rss / 1024 / 1024 if proc.info.get('memory_info') else 0,
                    'status': proc.status()
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    return processes


def display_processes(processes, detailed=False):
    """Display processes in a table"""
    if not processes:
        print("No s3vaultfuse processes found")
        return
    
    print(f"\n{'='*80}")
    print(f"S3VaultFuse Process Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total processes: {len(processes)}")
    print(f"{'='*80}\n")
    
    if detailed:
        # Detailed view
        for proc in processes:
            print(f"PID: {proc['pid']}")
            print(f"  Mount Path: {proc['mount_path']}")
            print(f"  Status: {proc['status']}")
            print(f"  Uptime: {proc['uptime']}")
            print(f"  CPU: {proc['cpu_percent']:.1f}%")
            print(f"  Memory: {proc['memory_mb']:.1f} MB")
            print(f"  Started: {proc['create_time'].strftime('%Y-%m-%d %H:%M:%S')}")
            print()
    else:
        # Table view
        headers = ['PID', 'Mount Path', 'Status', 'Uptime', 'CPU%', 'Memory(MB)']
        rows = []
        
        for proc in processes:
            rows.append([
                proc['pid'],
                proc['mount_path'][:50] if proc['mount_path'] else 'N/A',
                proc['status'],
                proc['uptime'],
                f"{proc['cpu_percent']:.1f}",
                f"{proc['memory_mb']:.1f}"
            ])
        
        print(tabulate(rows, headers=headers, tablefmt='grid'))


def kill_process(pid, force=False):
    """Kill a specific process"""
    try:
        proc = psutil.Process(pid)
        
        if force:
            print(f"Force killing process {pid}...")
            proc.kill()  # SIGKILL
        else:
            print(f"Terminating process {pid}...")
            proc.terminate()  # SIGTERM
            
            # Wait for termination
            try:
                proc.wait(timeout=10)
                print(f"Process {pid} terminated successfully")
            except psutil.TimeoutExpired:
                print(f"Process {pid} did not terminate, force killing...")
                proc.kill()
                proc.wait(timeout=5)
                print(f"Process {pid} force killed")
        
        return True
        
    except psutil.NoSuchProcess:
        print(f"Process {pid} not found")
        return False
    except psutil.AccessDenied:
        print(f"Permission denied to kill process {pid}")
        return False
    except Exception as e:
        print(f"Error killing process {pid}: {e}")
        return False


def cleanup_zombie_processes():
    """Cleanup zombie processes"""
    zombies = []
    
    for proc in psutil.process_iter(['pid', 'name', 'status']):
        try:
            if proc.info['status'] == psutil.STATUS_ZOMBIE and 's3vaultfuse' in proc.info.get('name', ''):
                zombies.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if zombies:
        print(f"Found {len(zombies)} zombie s3vaultfuse processes")
        for pid in zombies:
            print(f"  Cleaning up zombie process {pid}")
            try:
                os.system(f"kill -9 {pid}")
            except:
                pass
    else:
        print("No zombie processes found")


def watch_processes(interval=5):
    """Watch processes continuously"""
    try:
        while True:
            os.system('clear' if os.name != 'nt' else 'cls')
            processes = find_s3vaultfuse_processes()
            display_processes(processes)
            print(f"\nRefreshing every {interval} seconds... (Press Ctrl+C to exit)")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitoring stopped")


def main():
    parser = argparse.ArgumentParser(
        description='Monitor s3vaultfuse processes',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '-d', '--detailed',
        action='store_true',
        help='Show detailed information'
    )
    
    parser.add_argument(
        '-w', '--watch',
        action='store_true',
        help='Watch processes continuously'
    )
    
    parser.add_argument(
        '-i', '--interval',
        type=int,
        default=5,
        help='Refresh interval for watch mode (seconds)'
    )
    
    parser.add_argument(
        '-k', '--kill',
        type=int,
        metavar='PID',
        help='Kill a specific process by PID'
    )
    
    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='Force kill (SIGKILL) instead of graceful termination'
    )
    
    parser.add_argument(
        '-c', '--cleanup',
        action='store_true',
        help='Cleanup zombie processes'
    )
    
    args = parser.parse_args()
    
    # Kill specific process
    if args.kill:
        kill_process(args.kill, args.force)
        return
    
    # Cleanup zombies
    if args.cleanup:
        cleanup_zombie_processes()
        return
    
    # Watch mode
    if args.watch:
        watch_processes(args.interval)
        return
    
    # Default: list processes once
    processes = find_s3vaultfuse_processes()
    display_processes(processes, args.detailed)


if __name__ == '__main__':
    main()
