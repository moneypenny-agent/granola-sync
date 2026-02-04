#!/usr/bin/env python3
"""
Granola Transcript Sync
Fetches meeting transcripts from Granola API and sends to webhook (N8N/Moneypenny)

Usage:
    python3 granola_sync.py --webhook https://your-webhook-url
    python3 granola_sync.py --webhook https://your-webhook-url --hours 48 --verbose
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from token_manager import TokenManager

__version__ = "1.1.0"

# Configure logging
def setup_logging(verbose: bool = False, log_file: Optional[str] = None) -> logging.Logger:
    """Configure logging with optional file output"""
    level = logging.DEBUG if verbose else logging.INFO
    
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers
    )
    return logging.getLogger(__name__)


def create_session(retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """Create a requests session with retry logic"""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class GranolaSync:
    """Main class for syncing Granola transcripts"""
    
    API_BASE = "https://api.granola.ai"
    USER_AGENT = "Granola/5.354.0"
    CLIENT_VERSION = "5.354.0"
    
    def __init__(self, token_manager: TokenManager, webhook_url: str, 
                 state_file: str = "sync_state.json"):
        self.tm = token_manager
        self.webhook_url = webhook_url
        self.state_file = Path(state_file)
        self.session = create_session()
        self.logger = logging.getLogger(__name__)
        self.synced_ids: Set[str] = set()
        self._load_state()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get API headers with current token"""
        token = self.tm.get_valid_token()
        if not token:
            raise RuntimeError("Could not obtain valid token")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "User-Agent": self.USER_AGENT,
            "X-Client-Version": self.CLIENT_VERSION
        }
    
    def _load_state(self) -> None:
        """Load sync state from disk"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.synced_ids = set(data.get("synced_ids", []))
                    self.logger.debug(f"Loaded {len(self.synced_ids)} previously synced IDs")
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Could not load state file: {e}")
                self.synced_ids = set()
    
    def _save_state(self) -> None:
        """Save sync state to disk"""
        try:
            data = {
                "synced_ids": list(self.synced_ids),
                "last_sync": datetime.now().isoformat(),
                "version": __version__
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
            self.logger.debug(f"Saved state with {len(self.synced_ids)} synced IDs")
        except IOError as e:
            self.logger.error(f"Could not save state: {e}")
    
    def fetch_documents(self, since_hours: int = 24, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch documents from Granola API"""
        url = f"{self.API_BASE}/v2/get-documents"
        all_docs = []
        offset = 0
        cutoff = datetime.utcnow() - timedelta(hours=since_hours)
        
        while True:
            payload = {
                "limit": limit,
                "offset": offset,
                "include_last_viewed_panel": True
            }
            
            try:
                self.logger.debug(f"Fetching documents: offset={offset}, limit={limit}")
                response = self.session.post(url, headers=self._get_headers(), json=payload, timeout=30)
                response.raise_for_status()
                result = response.json()
                
                docs = result.get("docs", [])
                if not docs:
                    break
                
                # Filter by creation time
                for doc in docs:
                    created_at = doc.get("created_at", "")
                    if created_at:
                        try:
                            doc_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                            if doc_time.replace(tzinfo=None) >= cutoff:
                                all_docs.append(doc)
                        except ValueError:
                            all_docs.append(doc)  # Include if can't parse date
                    else:
                        all_docs.append(doc)
                
                if len(docs) < limit:
                    break
                offset += limit
                
            except requests.RequestException as e:
                self.logger.error(f"Failed to fetch documents: {e}")
                break
        
        self.logger.info(f"Found {len(all_docs)} documents from last {since_hours} hours")
        return all_docs
    
    def fetch_transcript(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Fetch transcript for a specific document"""
        url = f"{self.API_BASE}/v1/get-document-transcript"
        payload = {"document_id": document_id}
        
        try:
            response = self.session.post(url, headers=self._get_headers(), json=payload, timeout=30)
            if response.status_code == 404:
                self.logger.debug(f"No transcript for document {document_id}")
                return None
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.debug(f"Could not fetch transcript for {document_id}: {e}")
            return None
    
    @staticmethod
    def transcript_to_text(transcript_data: Optional[Dict[str, Any]]) -> str:
        """Convert transcript JSON to readable text format"""
        if not transcript_data:
            return ""
        
        segments = transcript_data.get("segments", [])
        if not segments:
            return ""
        
        lines = []
        for seg in segments:
            speaker = seg.get("speaker", "Unknown")
            text = seg.get("text", "").strip()
            timestamp = seg.get("start", 0)
            
            if text:
                # Format timestamp as MM:SS
                mins, secs = divmod(int(timestamp), 60)
                lines.append(f"[{mins:02d}:{secs:02d}] {speaker}: {text}")
        
        return "\n".join(lines)
    
    @staticmethod
    def extract_notes(panel_content: Any) -> str:
        """Extract readable text from ProseMirror content"""
        if not panel_content:
            return ""
        
        if isinstance(panel_content, str):
            return panel_content
        
        if not isinstance(panel_content, dict):
            return ""
        
        def extract_text(node: Dict[str, Any]) -> str:
            """Recursively extract text from ProseMirror nodes"""
            texts = []
            
            if node.get("type") == "text":
                texts.append(node.get("text", ""))
            
            for child in node.get("content", []):
                if isinstance(child, dict):
                    texts.append(extract_text(child))
            
            return " ".join(texts)
        
        return extract_text(panel_content).strip()
    
    def send_to_webhook(self, payload: Dict[str, Any]) -> bool:
        """Send payload to webhook endpoint"""
        try:
            response = self.session.post(
                self.webhook_url, 
                json=payload, 
                timeout=30,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            self.logger.info(f"✓ Sent to webhook: {payload.get('title', 'unknown')[:50]}")
            return True
        except requests.RequestException as e:
            self.logger.error(f"✗ Webhook failed for {payload.get('title', 'unknown')}: {e}")
            return False
    
    def sync(self, since_hours: int = 24, force_all: bool = False, 
             dry_run: bool = False) -> Dict[str, int]:
        """
        Main sync method - fetch documents and send to webhook
        
        Returns dict with counts: {'total': N, 'new': N, 'synced': N, 'failed': N}
        """
        stats = {"total": 0, "new": 0, "synced": 0, "failed": 0}
        
        # Fetch documents
        documents = self.fetch_documents(since_hours=since_hours)
        stats["total"] = len(documents)
        
        # Filter to new documents only (unless force_all)
        if force_all:
            new_docs = documents
        else:
            new_docs = [d for d in documents if d.get("id") not in self.synced_ids]
        
        stats["new"] = len(new_docs)
        self.logger.info(f"Processing {len(new_docs)} new documents (of {len(documents)} total)")
        
        if not new_docs:
            self.logger.info("Nothing new to sync")
            return stats
        
        # Process each document
        for doc in new_docs:
            doc_id = doc.get("id")
            title = doc.get("title", "Untitled Meeting")
            created_at = doc.get("created_at", "")
            
            self.logger.info(f"Processing: {title[:60]}...")
            
            # Fetch transcript
            transcript_data = self.fetch_transcript(doc_id)
            transcript_text = self.transcript_to_text(transcript_data)
            
            # Extract notes from panel content
            notes = ""
            last_panel = doc.get("last_viewed_panel", {})
            if last_panel:
                content = last_panel.get("content", {})
                notes = self.extract_notes(content)
            
            # Build payload
            payload = {
                "source": "granola",
                "document_id": doc_id,
                "title": title,
                "created_at": created_at,
                "transcript": transcript_text,
                "transcript_segments": len(transcript_data.get("segments", [])) if transcript_data else 0,
                "notes": notes,
                "attendees": doc.get("attendees", []),
                "synced_at": datetime.utcnow().isoformat() + "Z"
            }
            
            if dry_run:
                self.logger.info(f"[DRY RUN] Would send: {title}")
                print(json.dumps(payload, indent=2, ensure_ascii=False))
                stats["synced"] += 1
            else:
                if self.send_to_webhook(payload):
                    self.synced_ids.add(doc_id)
                    stats["synced"] += 1
                else:
                    stats["failed"] += 1
        
        # Save state
        if not dry_run:
            self._save_state()
        
        return stats


def main():
    parser = argparse.ArgumentParser(
        description="Sync Granola meeting transcripts to a webhook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --webhook https://n8n.example.com/webhook/granola
  %(prog)s --webhook https://n8n.example.com/webhook/granola --hours 48
  %(prog)s --webhook https://n8n.example.com/webhook/granola --all --dry-run

For more info: https://github.com/moneypenny-agent/granola-sync
        """
    )
    parser.add_argument("--webhook", required=True, help="Webhook URL to send transcripts to")
    parser.add_argument("--hours", type=int, default=24, help="Fetch meetings from last N hours (default: 24)")
    parser.add_argument("--all", action="store_true", help="Sync all documents, not just new ones")
    parser.add_argument("--dry-run", action="store_true", help="Print payloads without sending")
    parser.add_argument("--config", default="config.json", help="Path to config file (default: config.json)")
    parser.add_argument("--state", default="sync_state.json", help="Path to state file (default: sync_state.json)")
    parser.add_argument("--log", help="Log file path (optional)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose/debug output")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(verbose=args.verbose, log_file=args.log)
    logger.info(f"Granola Sync v{__version__}")
    
    # Initialize token manager
    tm = TokenManager(config_file=args.config)
    if not tm.get_valid_token():
        logger.error("Could not obtain valid token. Check your config.json")
        logger.error("Run extract_token.sh to get your credentials from Granola")
        sys.exit(1)
    
    # Initialize sync client
    sync = GranolaSync(
        token_manager=tm,
        webhook_url=args.webhook,
        state_file=args.state
    )
    
    # Run sync
    stats = sync.sync(
        since_hours=args.hours,
        force_all=args.all,
        dry_run=args.dry_run
    )
    
    # Print summary
    logger.info(f"Sync complete: {stats['synced']} sent, {stats['failed']} failed, {stats['new']} new of {stats['total']} total")
    
    # Exit with error if any failed
    if stats["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
