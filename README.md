# Granola Sync 🥣

Sync meeting transcripts from [Granola](https://granola.ai) to external services via webhook.

Granola is an AI meeting assistant that captures transcripts and generates notes. This tool extracts those transcripts and sends them to your automation platform (N8N, Make, Zapier, etc.) for further processing.

## Features

- ✅ Fetches meeting documents and transcripts from Granola API
- ✅ Handles OAuth token refresh (with rotation)
- ✅ Tracks synced documents to avoid duplicates
- ✅ Extracts readable text from transcripts and notes
- ✅ Sends to any webhook endpoint
- ✅ Retry logic with exponential backoff
- ✅ Dry-run mode for testing

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Extract your Granola credentials

Run the extraction script (requires Granola to be logged in on your Mac):

```bash
./extract_token.sh
```

This creates `config.json` with your credentials.

**Manual extraction** (if script doesn't work):

```bash
# Get the refresh token
cat ~/Library/Application\ Support/Granola/supabase.json | \
  jq -r '.workos_tokens | fromjson | .refresh_token'

# Get the client_id from the JWT
cat ~/Library/Application\ Support/Granola/supabase.json | \
  jq -r '.workos_tokens | fromjson | .access_token' | \
  cut -d. -f2 | base64 -d 2>/dev/null | jq -r '.iss' | \
  grep -oE 'client_[a-zA-Z0-9_]+'
```

Create `config.json`:
```json
{
  "refresh_token": "YOUR_REFRESH_TOKEN",
  "client_id": "client_01..."
}
```

### 3. Run the sync

```bash
python3 granola_sync.py --webhook https://your-webhook-url
```

## Usage

```
usage: granola_sync.py [-h] --webhook WEBHOOK [--hours HOURS] [--all]
                       [--dry-run] [--config CONFIG] [--state STATE]
                       [--log LOG] [-v] [--version]

Options:
  --webhook URL    Webhook URL to send transcripts to (required)
  --hours N        Fetch meetings from last N hours (default: 24)
  --all            Sync all documents, not just new ones
  --dry-run        Print payloads without sending
  --config FILE    Path to config file (default: config.json)
  --state FILE     Path to state file (default: sync_state.json)
  --log FILE       Log file path (optional)
  -v, --verbose    Enable debug output
  --version        Show version
```

### Examples

```bash
# Basic sync - last 24 hours, only new documents
python3 granola_sync.py --webhook https://n8n.example.com/webhook/granola

# Sync last 48 hours with verbose output
python3 granola_sync.py --webhook https://... --hours 48 --verbose

# Dry run to see what would be sent
python3 granola_sync.py --webhook https://... --dry-run

# Force re-sync all documents
python3 granola_sync.py --webhook https://... --all
```

## Webhook Payload

Each synced document sends a JSON payload like this:

```json
{
  "source": "granola",
  "document_id": "abc123...",
  "title": "Weekly Standup",
  "created_at": "2026-02-04T10:00:00.000Z",
  "transcript": "[00:00] Alice: Good morning everyone...\n[00:15] Bob: Morning!...",
  "transcript_segments": 42,
  "notes": "Meeting notes extracted from Granola...",
  "attendees": ["alice@example.com", "bob@example.com"],
  "synced_at": "2026-02-04T15:30:00.000Z"
}
```

## Automation Setup

### N8N

1. Create a **Webhook** node:
   - HTTP Method: `POST`
   - Path: `granola-transcript`
   - Copy the webhook URL

2. Add processing nodes (HTTP Request, Notion, Slack, etc.)

3. Configure your cron or run manually

### Cron Setup

To run every 5 minutes (keeps token fresh):

```bash
# Edit crontab
crontab -e

# Add this line (adjust paths)
*/5 * * * * cd /path/to/granola-sync && python3 granola_sync.py --webhook https://... >> /var/log/granola-sync.log 2>&1
```

## Files

| File | Purpose |
|------|---------|
| `granola_sync.py` | Main sync script |
| `token_manager.py` | OAuth token handling |
| `extract_token.sh` | Credential extraction helper |
| `config.json` | Your credentials (gitignored) |
| `sync_state.json` | Tracks synced documents (gitignored) |
| `requirements.txt` | Python dependencies |

## Token Rotation Warning ⚠️

**WorkOS rotates refresh tokens on every use.** When you refresh your access token, you get a NEW refresh token, and the old one becomes invalid.

This tool automatically saves the new refresh token to `config.json`. If you interrupt the script mid-refresh, your config may have a stale token. In that case, re-run `extract_token.sh` to get fresh credentials from the Granola app.

## Troubleshooting

### "Could not obtain valid token"

1. Make sure Granola is logged in on your Mac
2. Re-run `./extract_token.sh` to get fresh credentials
3. Check that `config.json` has both `refresh_token` and `client_id`

### "Token refresh failed: HTTP 401"

Your refresh token is invalid. Re-extract from Granola:
```bash
./extract_token.sh
```

### "No transcript for document"

Not all Granola documents have transcripts. If there was no audio recording, there's no transcript. The sync will still send the document metadata and notes.

### Documents not syncing

The script only syncs NEW documents by default. Use `--all` to re-sync everything, or delete `sync_state.json` to reset the sync state.

## License

MIT - Use freely, attribution appreciated.

## Credits

Built by [Moneypenny](https://github.com/moneypenny-agent) 🍸
