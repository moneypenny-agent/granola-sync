"""
Token Manager for Granola API
Handles OAuth 2.0 refresh token rotation via WorkOS

The Granola app uses WorkOS for authentication. This manager handles:
- Loading tokens from config file
- Refreshing access tokens when expired
- Saving rotated refresh tokens (WorkOS rotates refresh tokens on each use)
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class TokenManager:
    """
    Manages Granola API authentication tokens.
    
    Tokens are stored in a config.json file:
    {
        "refresh_token": "...",
        "client_id": "client_01...",
        "access_token": "...",  # Cached, optional
        "token_expiry": "..."   # ISO timestamp, optional
    }
    """
    
    WORKOS_AUTH_URL = "https://api.workos.com/user_management/authenticate"
    TOKEN_BUFFER_MINUTES = 5  # Refresh tokens with less than this remaining
    
    def __init__(self, config_file: str = 'config.json'):
        self.config_file = Path(config_file)
        self.refresh_token: Optional[str] = None
        self.client_id: Optional[str] = None
        self.access_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self._load_config()
    
    def _load_config(self) -> bool:
        """Load configuration from disk"""
        if not self.config_file.exists():
            logger.error(f"Config file not found: {self.config_file}")
            logger.error("Create config.json with 'refresh_token' and 'client_id'")
            logger.error("Run ./extract_token.sh to get these from Granola")
            return False
        
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            
            self.refresh_token = config.get('refresh_token')
            self.client_id = config.get('client_id')
            self.access_token = config.get('access_token')
            
            expiry_str = config.get('token_expiry')
            if expiry_str:
                try:
                    self.token_expiry = datetime.fromisoformat(expiry_str)
                except ValueError:
                    self.token_expiry = None
            
            if not self.refresh_token:
                logger.error("No refresh_token in config file")
                return False
            
            if not self.client_id:
                logger.error("No client_id in config file")
                return False
            
            logger.debug(f"Config loaded from {self.config_file}")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return False
        except IOError as e:
            logger.error(f"Could not read config file: {e}")
            return False
    
    def _save_config(self) -> bool:
        """Save updated tokens to disk"""
        try:
            # Load existing config to preserve other fields
            config = {}
            if self.config_file.exists():
                try:
                    with open(self.config_file, 'r') as f:
                        config = json.load(f)
                except (json.JSONDecodeError, IOError):
                    pass
            
            # Update token fields
            config['refresh_token'] = self.refresh_token
            config['client_id'] = self.client_id
            config['access_token'] = self.access_token
            config['token_expiry'] = self.token_expiry.isoformat() if self.token_expiry else None
            config['last_refresh'] = datetime.now().isoformat()
            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.debug("Config saved")
            
            # IMPORTANT: Write rotated tokens back to Granola's own data file
            # so the desktop app doesn't get logged out when the refresh token rotates.
            self._sync_tokens_to_granola_app()
            
            return True
            
        except IOError as e:
            logger.error(f"Could not save config: {e}")
            return False
    
    def _sync_tokens_to_granola_app(self) -> None:
        """
        Write updated tokens back to Granola's supabase.json so the
        desktop app doesn't get logged out after token rotation.
        """
        import os
        granola_file = Path(os.path.expanduser(
            "~/Library/Application Support/Granola/supabase.json"
        ))
        
        if not granola_file.exists():
            return  # Not on the machine with Granola installed, skip silently
        
        try:
            with open(granola_file, 'r') as f:
                granola_data = json.load(f)
            
            # Parse current workos_tokens (stored as a JSON string inside the JSON)
            workos_str = granola_data.get('workos_tokens', '{}')
            try:
                workos_tokens = json.loads(workos_str) if isinstance(workos_str, str) else workos_str
            except (json.JSONDecodeError, TypeError):
                workos_tokens = {}
            
            # Update with our current tokens
            workos_tokens['refresh_token'] = self.refresh_token
            if self.access_token:
                workos_tokens['access_token'] = self.access_token
            
            # Write back (preserving the string-within-JSON format Granola uses)
            granola_data['workos_tokens'] = json.dumps(workos_tokens)
            
            with open(granola_file, 'w') as f:
                json.dump(granola_data, f)
            
            logger.debug("Synced rotated tokens back to Granola app")
            
        except Exception as e:
            # Non-fatal — script still works, just logs the issue
            logger.debug(f"Could not sync tokens to Granola app: {e}")
    
    def is_token_expired(self) -> bool:
        """Check if access token is expired or about to expire"""
        if not self.access_token or not self.token_expiry:
            return True
        
        buffer = timedelta(minutes=self.TOKEN_BUFFER_MINUTES)
        return datetime.now() >= (self.token_expiry - buffer)
    
    def refresh_access_token(self) -> bool:
        """
        Exchange refresh token for a new access token via WorkOS.
        
        IMPORTANT: WorkOS rotates refresh tokens - each refresh returns a NEW
        refresh token, and the old one becomes invalid. We must save the new one.
        """
        logger.info("Refreshing access token...")
        
        if not self.refresh_token or not self.client_id:
            logger.error("Missing refresh_token or client_id in config")
            return False
        
        payload = {
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }
        
        try:
            response = requests.post(
                self.WORKOS_AUTH_URL, 
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            # Extract new access token
            self.access_token = result.get('access_token')
            if not self.access_token:
                logger.error("No access_token in response")
                return False
            
            # CRITICAL: Save rotated refresh token
            new_refresh_token = result.get('refresh_token')
            if new_refresh_token:
                logger.debug("Refresh token rotated (old token is now invalid)")
                self.refresh_token = new_refresh_token
            
            # Calculate expiry
            expires_in = result.get('expires_in', 3600)
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in)
            
            # Save immediately (refresh token rotation!)
            self._save_config()
            
            logger.info(f"Access token obtained (expires in {expires_in}s)")
            return True
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"Token refresh failed: HTTP {e.response.status_code}")
            if e.response.text:
                logger.debug(f"Response: {e.response.text}")
            # If refresh fails with 401/400, the refresh token may be invalid
            if e.response.status_code in (400, 401):
                logger.error("Refresh token may be invalid. Re-extract from Granola app.")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Token refresh failed: {e}")
            return False
    
    def get_valid_token(self) -> Optional[str]:
        """
        Get a valid access token, refreshing if needed.
        
        Returns:
            Valid access token string, or None if unable to obtain one
        """
        if self.is_token_expired():
            if not self.refresh_access_token():
                logger.error("Could not obtain valid access token")
                return None
        return self.access_token
    
    @property
    def is_configured(self) -> bool:
        """Check if token manager has required configuration"""
        return bool(self.refresh_token and self.client_id)
