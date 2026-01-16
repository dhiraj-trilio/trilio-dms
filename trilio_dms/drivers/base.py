"""Base mount driver interface"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseMountDriver(ABC):
    """Abstract base class for mount drivers"""
    
    @abstractmethod
    def mount(self, target_id: str, mount_path: str, **kwargs) -> bool:
        """
        Mount the target.
        
        Args:
            target_id: Target identifier
            mount_path: Path where target should be mounted
            **kwargs: Driver-specific parameters
            
        Returns:
            True if mount successful, False otherwise
        """
        pass
    
    @abstractmethod
    def unmount(self, target_id: str, mount_path: str) -> bool:
        """
        Unmount the target.
        
        Args:
            target_id: Target identifier
            mount_path: Path to unmount
            
        Returns:
            True if unmount successful, False otherwise
        """
        pass
    
    @abstractmethod
    def is_mounted(self, mount_path: str) -> bool:
        """
        Check if path is currently mounted.
        
        Args:
            mount_path: Path to check
            
        Returns:
            True if mounted, False otherwise
        """
        pass
    
    @abstractmethod
    def get_mount_info(self, mount_path: str) -> Dict[str, Any]:
        """
        Get information about a mount.
        
        Args:
            mount_path: Path to query
            
        Returns:
            Dictionary with mount information
        """
        pass

