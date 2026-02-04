#!/usr/bin/env python3
"""
Granola Transcript Sync
Fetches meeting transcripts from Granola API and sends to webhook (N8N)
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import requests
from token_manager import TokenManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('granola_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Granola API headers
def get_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": "Granola/5.354.0",
        "X-Client-Version": "5.354.0"
    }


def fetch_documents(token, limit=100, since_hours=24):
    """Fetch documents from Granola, optionally filtered by time"""
    url = "https://api.granola.ai/v2/get-documents"
    all_docs = []
    offset = 0
    cutoff = datetime.now() - timedelta(hours=since_hours)
    
    while True:
        data = {
            "limit": limit,
            "offset": offset,
            "include_last_viewed_panel": True
        }
        
        try:
            logger.info(f"Fetching documents: offset={offset}")
            response = requests.post(url, headers=get_headers(token), json=data)
            response.raise_for_status()
            result = response.json()
            
            docs = result.get("docs", [])
            if not docs:
                break
            
            # Filter by time if needed
            for doc in docs:
                created_at = doc.get("created_at", "")
                if created_at:
                    try:
                        doc_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        if doc_time.replace(tzinfo=None) >= cutoff:
                            all_docs.append(doc)
                    except:
                        all_docs.append(doc)
                else:
                    all_docs.append(doc)
            
            if len(docs) < limit:
                break
            offset += limit
            
        except Exception as e:
            logger.error(f"Error fetching documents: {e}")
            break
    
    logger.info(f"Found {len(all_docs)} documents")
    return all_docs


def fetch_transcript(token, document_id):
    """Fetch transcript for a specific document"""
    url = "https://api.granola.ai/v1/get-document-transcript"
    data = {"document_id": document_id}
    
    try:
        response = requests.post(url, headers=get_headers(token), json=data)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.debug(f"No transcript for {document_id}: {e}")
        return None


def convert_transcript_to_text(transcript_data):
    """Convert transcript JSON to readable text"""
    if not transcript_data:
        return ""
    
    segments = transcript_data.get("segments", [])
    if not segments:
        return ""
    
    lines = []
    for seg in segments:
        speaker = seg.get("speaker", "Unknown")
        text = seg.get("text", "")
        if text:
            lines.append(f"[{speaker}]: {text}")
    
    return "\n".join(lines)


def send_to_webhook(webhook_url, payload):
    """Send transcript to N8N webhook"""
    try:
        response = requests.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        logger.info(f"Sent to webhook: {payload.get('title', 'unknown')}")
        return True
    except Exception as e:
        logger.error(f"Webhook failed: {e}")
        return False


def load_sync_state(state_file="sync_state.json"):
    """Load list of already-synced document IDs"""
    if Path(state_file).exists():
        with open(state_file, 'r') as f:
            return set(json.load(f).get("synced_ids", []))
    return set()


def save_sync_state(synced_ids, state_file="sync_state.json"):
    """Save synced document IDs to avoid duplicates"""
    with open(state_file, 'w') as f:
        json.dump({"synced_ids": list(synced_ids), "last_sync": datetime.now().isoformat()}, f)


def main():
    parser = argparse.ArgumentParser(description="Sync Granola transcripts to webhook")
    parser.add_argument("--webhook", required=True, help="N8N webhook URL")
    parser.add_argument("--hours", type=int, default=24, help="Fetch meetings from last N hours")
    parser.add_argument("--all", action="store_true", help="Sync all documents, not just new ones")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually send to webhook")
    args = parser.parse_args()
    
    # Initialize token manager
    tm = TokenManager()
    token = tm.get_valid_token()
    if not token:
        logger.error("Could not get valid token. Check config.json")
        sys.exit(1)
    
    # Load sync state
    synced_ids = load_sync_state() if not args.all else set()
    
    # Fetch documents
    documents = fetch_documents(token, since_hours=args.hours)
    
    new_docs = [d for d in documents if d.get("id") not in synced_ids]
    logger.info(f"New documents to sync: {len(new_docs)}")
    
    # Process each document
    for doc in new_docs:
        doc_id = doc.get("id")
        title = doc.get("title", "Untitled Meeting")
        created_at = doc.get("created_at", "")
        
        logger.info(f"Processing: {title}")
        
        # Fetch transcript
        transcript_data = fetch_transcript(token, doc_id)
        transcript_text = convert_transcript_to_text(transcript_data)
        
        # Extract notes/content
        notes = ""
        last_panel = doc.get("last_viewed_panel", {})
        if last_panel:
            content = last_panel.get("content", {})
            # ProseMirror format - extract text
            if isinstance(content, dict):
                notes = json.dumps(content)  # Send raw for now
        
        # Build payload
        payload = {
            "source": "granola",
            "document_id": doc_id,
            "title": title,
            "created_at": created_at,
            "transcript": transcript_text,
            "notes": notes,
            "synced_at": datetime.now().isoformat()
        }
        
        if args.dry_run:
            logger.info(f"[DRY RUN] Would send: {title}")
            print(json.dumps(payload, indent=2))
        else:
            if send_to_webhook(args.webhook, payload):
                synced_ids.add(doc_id)
    
    # Save state
    if not args.dry_run:
        save_sync_state(synced_ids)
    
    logger.info("Sync complete!")


if __name__ == "__main__":
    main()
