"""
Token Manager for Granola API
Handles OAuth 2.0 refresh token rotation via WorkOS
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
import requests

logger = logging.getLogger(__name__)

class TokenManager:
    def __init__(self, config_file='config.json'):
        self.config_file = Path(config_file)
        self.refresh_token = None
        self.client_id = None
        self.access_token = None
        self.token_expiry = None
        self._load_config()

    def _load_config(self):
        if not self.config_file.exists():
            logger.error(f"Config file {self.config_file} does not exist!")
            logger.error("Create config.json with your refresh_token and client_id")
            return False

        try:
            with open(self.config_file, 'r') as f:
                config_data = json.load(f)

            self.refresh_token = config_data.get('refresh_token')
            self.client_id = config_data.get('client_id')
            self.access_token = config_data.get('access_token')
            expiry_str = config_data.get('token_expiry')
            if expiry_str:
                self.token_expiry = datetime.fromisoformat(expiry_str)

            logger.debug(f"Config loaded from {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
            return False

    def _save_config(self):
        """Save updated tokens back to config file"""
        try:
            config_data = {}
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)

            config_data['refresh_token'] = self.refresh_token
            if self.client_id:
                config_data['client_id'] = self.client_id
            config_data['access_token'] = self.access_token
            config_data['token_expiry'] = self.token_expiry.isoformat() if self.token_expiry else None

            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=2)

            logger.debug(f"Config saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Error saving config: {str(e)}")

    def is_token_expired(self):
        if not self.access_token or not self.token_expiry:
            return True
        # Consider expired if < 5 minutes remaining
        buffer = timedelta(minutes=5)
        return datetime.now() >= (self.token_expiry - buffer)

    def refresh_access_token(self):
        """Exchange refresh token for new access token via WorkOS"""
        logger.info("Refreshing access token...")

        if not self.refresh_token:
            logger.error("No refresh token in config.json")
            return False

        if not self.client_id:
            logger.error("No client_id in config.json")
            return False

        url = "https://api.workos.com/user_management/authenticate"
        data = {
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }

        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            result = response.json()

            self.access_token = result.get('access_token')
            
            # IMPORTANT: Token rotation - save new refresh token
            new_refresh_token = result.get('refresh_token')
            if new_refresh_token:
                self.refresh_token = new_refresh_token
                logger.info("Refresh token rotated (old token is now invalid)")

            expires_in = result.get('expires_in', 3600)
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in)

            self._save_config()

            logger.info(f"Access token obtained (expires in {expires_in}s)")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Token refresh failed: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.debug(f"Response: {e.response.text}")
            return False

    def get_valid_token(self):
        """Get a valid access token, refreshing if needed"""
        if self.is_token_expired():
            if not self.refresh_access_token():
                logger.error("Failed to obtain access token")
                return None
        return self.access_token
