"""Secret management service for Barbican integration"""

import json
from typing import Dict, Optional
import json
import logging
import requests
from typing import Dict

from keystoneauth1 import session as ks_session
from keystoneauth1.identity import v3
from barbicanclient.v1 import client as barbican_client

from keystoneauth1 import token_endpoint

from trilio_dms.utils.logger import get_logger
from trilio_dms.utils.exceptions import AuthenticationException

LOG = get_logger(__name__)


class SecretManager:
    """Manages secret retrieval from OpenStack Barbican using only token."""
    
    def __init__(self, config: Dict = None):
        """
        Initialize SecretManager.
        
        Args:
            config: Optional configuration dictionary containing:
                - verify_ssl: SSL verification (default: False)
        """
        self.config = config or {}
        self.verify_ssl = self.config.get('verify_ssl', False)
        
        if not self.verify_ssl:
            # Disable SSL warnings
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def retrieve_credentials(self, secret_ref: str, keystone_token: str) -> Dict:
        """
        Retrieve credentials from Barbican using only secret_ref and token.
        
        This method uses direct REST API calls to Barbican with the provided
        Keystone token. No additional authentication is needed.
        
        Args:
            secret_ref: Full URL to the Barbican secret
                       (e.g., 'https://host:9311/v1/secrets/uuid')
            keystone_token: Valid project-scoped Keystone token
            
        Returns:
            Dictionary containing the secret credentials
            
        Raises:
            AuthenticationException: If credential retrieval fails
        """
        if not secret_ref:
            raise AuthenticationException("secret_ref is required")
        
        if not keystone_token:
            raise AuthenticationException("keystone_token is required")
        
        try:
            LOG.info(f"Retrieving secret from: {secret_ref}")
            LOG.debug(f"Using token: {keystone_token[:20]}...")
            
            # Step 1: Get secret metadata
            headers = {
                'X-Auth-Token': keystone_token,
                'Accept': 'application/json'
            }
            
            LOG.debug(f"Fetching secret metadata from: {secret_ref}")
            response = requests.get(
                secret_ref,
                headers=headers,
                verify=self.verify_ssl,
                timeout=30
            )
            
            # Handle common errors
            if response.status_code == 401:
                raise AuthenticationException(
                    "Invalid or expired Keystone token. Token authentication failed."
                )
            elif response.status_code == 403:
                raise AuthenticationException(
                    "Access denied to secret. Check token permissions and project scope."
                )
            elif response.status_code == 404:
                raise AuthenticationException(
                    f"Secret not found at {secret_ref}. Verify the secret_ref URL."
                )
            
            response.raise_for_status()
            secret_metadata = response.json()
            
            LOG.debug(f"Secret metadata retrieved: {json.dumps(secret_metadata, indent=2)}")
            
            # Step 2: Get the payload
            payload_url = f"{secret_ref}/payload"
            
            # Determine content type from metadata
            content_types = secret_metadata.get('content_types', {})
            content_type = content_types.get('default', 'application/octet-stream')
            
            LOG.debug(f"Content type: {content_type}")
            
            # Update headers for payload request
            headers['Accept'] = content_type
            
            LOG.debug(f"Fetching payload from: {payload_url}")
            payload_response = requests.get(
                payload_url,
                headers=headers,
                verify=self.verify_ssl,
                timeout=30
            )
            
            # Handle payload-specific errors
            if payload_response.status_code == 401:
                raise AuthenticationException(
                    "Token expired while retrieving payload. Please use a fresh token."
                )
            elif payload_response.status_code == 404:
                raise AuthenticationException(
                    f"Secret payload not found at {payload_url}. The secret may be empty."
                )
            
            payload_response.raise_for_status()
            
            # Step 3: Parse payload based on content type
            payload_text = payload_response.text
            LOG.debug(f"Raw payload (first 100 chars): {payload_text[:100]}")
            
            if not payload_text or payload_text.strip() == '':
                raise AuthenticationException("Secret payload is empty")
            
            # Try to parse as JSON
            if 'json' in content_type.lower() or payload_text.strip().startswith('{'):
                try:
                    credentials = json.loads(payload_text)
                    LOG.info("Successfully parsed credentials as JSON")
                except json.JSONDecodeError as e:
                    LOG.warning(f"Failed to parse payload as JSON: {e}")
                    # Return as raw payload if not JSON
                    credentials = {'raw_payload': payload_text}
            else:
                # Not JSON, return as raw payload
                LOG.info("Payload is not JSON, returning as raw content")
                credentials = {'raw_payload': payload_text}
            
            LOG.info("Successfully retrieved credentials from Barbican")
            LOG.debug(f"Credential keys: {list(credentials.keys())}")
            
            return credentials
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error retrieving secret: {e}"
            if e.response is not None:
                error_msg += f"\nStatus code: {e.response.status_code}"
                error_msg += f"\nResponse: {e.response.text[:200]}"
            LOG.error(error_msg)
            raise AuthenticationException(error_msg)
            
        except requests.exceptions.Timeout as e:
            error_msg = f"Timeout retrieving secret: {e}"
            LOG.error(error_msg)
            raise AuthenticationException(error_msg)
            
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Connection error retrieving secret: {e}"
            LOG.error(error_msg)
            raise AuthenticationException(error_msg)
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error retrieving secret: {e}"
            LOG.error(error_msg)
            raise AuthenticationException(error_msg)
            
        except AuthenticationException:
            # Re-raise our custom exceptions
            raise
            
        except Exception as e:
            error_msg = f"Unexpected error retrieving credentials: {str(e)}"
            LOG.error(error_msg, exc_info=True)
            raise AuthenticationException(error_msg)
    
    def test_secret_access(self, secret_ref: str, keystone_token: str) -> Dict:
        """
        Test access to a secret without retrieving the full payload.
        
        Useful for debugging token and secret_ref issues.
        
        Args:
            secret_ref: Full URL to the Barbican secret
            keystone_token: Valid project-scoped Keystone token
            
        Returns:
            Dictionary with test results including:
                - metadata_accessible: bool
                - payload_accessible: bool
                - content_type: str
                - error: str (if any)
        """
        result = {
            'metadata_accessible': False,
            'payload_accessible': False,
            'content_type': None,
            'error': None
        }
        
        try:
            headers = {
                'X-Auth-Token': keystone_token,
                'Accept': 'application/json'
            }
            
            # Test metadata access
            response = requests.get(
                secret_ref,
                headers=headers,
                verify=self.verify_ssl,
                timeout=10
            )
            
            if response.status_code == 200:
                result['metadata_accessible'] = True
                metadata = response.json()
                result['content_type'] = metadata.get('content_types', {}).get('default')
                
                # Test payload access
                payload_url = f"{secret_ref}/payload"
                payload_response = requests.get(
                    payload_url,
                    headers=headers,
                    verify=self.verify_ssl,
                    timeout=10
                )
                
                if payload_response.status_code == 200:
                    result['payload_accessible'] = True
                else:
                    result['error'] = f"Payload not accessible: {payload_response.status_code}"
            else:
                result['error'] = f"Metadata not accessible: {response.status_code} - {response.text[:100]}"
                
        except Exception as e:
            result['error'] = str(e)
        
        return result
