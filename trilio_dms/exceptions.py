"""
Custom exceptions for Trilio DMS
"""


class DMSException(Exception):
    """Base exception for DMS"""
    pass


class DMSClientException(DMSException):
    """Exception raised by DMS Client"""
    pass


class DMSServerException(DMSException):
    """Exception raised by DMS Server"""
    pass


class MountException(DMSException):
    """Exception raised during mount operations"""
    pass


class UnmountException(DMSException):
    """Exception raised during unmount operations"""
    pass


class RequestValidationException(DMSException):
    """Exception raised when request validation fails"""
    pass


class RequestTimeoutException(DMSException):
    """Exception raised when request times out"""
    pass


class DatabaseException(DMSException):
    """Exception raised for database operations"""
    pass


class SecretFetchException(DMSException):
    """Exception raised when fetching secrets from Barbican"""
    pass


class RabbitMQException(DMSException):
    """Exception raised for RabbitMQ operations"""
    pass
