"""Context manager for mount operations"""

from trilio_dms.client.dms_client import DMSClient


class MountContext:
    """
    Context manager for automatic mount/unmount.
    
    Note: This always uses sync mode (wait_for_response=True) to ensure
    mount is ready before proceeding with operations.
    """
    
    def __init__(self, client: DMSClient, job_id: int, target_id: str,
                 keystone_token: str, node_id: str = None):
        self.client = client
        self.job_id = job_id
        self.target_id = target_id
        self.keystone_token = keystone_token
        self.node_id = node_id
        self.mount_path = None
        self.mounted = False
        
        # Force sync mode for context manager
        self.original_mode = client.wait_for_response
        if not client.wait_for_response:
            LOG.warning("MountContext requires sync mode, switching temporarily")
            client.wait_for_response = True
    
    def __enter__(self):
        """Mount on context entry"""
        response = self.client.mount(
            self.job_id,
            self.target_id,
            self.keystone_token,
            self.node_id
        )
        
        if not response.get('success'):
            raise RuntimeError(f"Mount failed: {response.get('message')}")
        
        self.mount_path = response.get('mount_path')
        self.mounted = True
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Unmount on context exit"""
        if self.mounted:
            self.client.unmount(self.job_id, self.target_id, self.node_id)
        
        # Restore original mode
        self.client.wait_for_response = self.original_mode
