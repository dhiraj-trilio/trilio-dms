"""Data schemas and validation"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class MountRequest:
    """Mount request schema"""
    operation: str
    job_id: int
    target_id: str
    token: str
    node_id: str
    timestamp: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MountRequest':
        return cls(**data)


@dataclass
class MountResponse:
    """Mount response schema"""
    success: bool
    message: str
    mount_path: Optional[str] = None
    error_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UnmountRequest:
    """Unmount request schema"""
    operation: str
    job_id: int
    target_id: str
    node_id: str
    timestamp: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TargetMetadata:
    """Backup target metadata"""
    id: str
    name: str
    type: str
    mount_path: str
    secret_ref: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
