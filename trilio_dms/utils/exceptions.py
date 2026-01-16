"""Custom exceptions for Trilio DMS"""


class DMSException(Exception):
    """Base exception for DMS"""
    pass


class MountException(DMSException):
    """Exception raised during mount operations"""
    pass


class UnmountException(DMSException):
    """Exception raised during unmount operations"""
    pass


class AuthenticationException(DMSException):
    """Exception raised for authentication failures"""
    pass


class TargetNotFoundException(DMSException):
    """Exception raised when target is not found"""
    pass


class ConfigurationException(DMSException):
    """Exception raised for configuration errors"""
    pass


class DatabaseException(DMSException):
    """Exception raised for database errors"""
    pass


class MessagingException(DMSException):
    """Exception raised for messaging errors"""
    pass


class ReconciliationException(DMSException):
    """Exception raised during reconciliation"""
    pass

