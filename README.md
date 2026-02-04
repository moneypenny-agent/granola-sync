# Granola Transcript Sync

Pull meeting transcripts from Granola and pipe them to Moneypenny via N8N.

## Setup Steps

### Step 1: Extract Your Granola Token (One-Time)

On your Mac, with Granola logged in:

```bash
# View the raw file
cat ~/Library/Application\ Support/Granola/supabase.json

# Or extract just the refresh token
cat ~/Library/Application\ Support/Granola/supabase.json | jq -r '.workos_tokens | fromjson | .refresh_token'

# Extract the client_id from the JWT
cat ~/Library/Application\ Support/Granola/supabase.json | jq -r '.workos_tokens | fromjson | .access_token' | cut -d. -f2 | base64 -d 2>/dev/null | jq -r '.iss' | grep -oE 'client_[a-zA-Z0-9_]+'
```

You'll get:
- `refresh_token`: Something like `22oWVolI9TRlthI2J5asHbfyx`
- `client_id`: Something like `client_01ABC123...`

### Step 2: Create config.json

```json
{
  "refresh_token": "YOUR_REFRESH_TOKEN_HERE",
  "client_id": "YOUR_CLIENT_ID_HERE"
}
```

### Step 3: Run the Sync Script

```bash
python3 granola_sync.py --webhook https://your-n8n-webhook-url
```

Or set up as cron (every 5 min to keep token alive):
```bash
*/5 * * * * cd /path/to/granola-sync && python3 granola_sync.py --webhook https://your-n8n-webhook-url
```

## N8N Workflow Setup

### Webhook Node (Trigger)
1. Add a **Webhook** node
2. HTTP Method: POST
3. Path: `granola-transcript`
4. Copy the webhook URL (you'll need this for the script)

### HTTP Request Node (Send to Moneypenny)
1. Add **HTTP Request** node
2. Method: POST
3. URL: `https://dash.universalexports.company/api/granola/ingest`
4. Authentication: Header Auth
5. Header Name: `Authorization`
6. Header Value: `Bearer YOUR_DASHBOARD_TOKEN`
7. Body Content Type: JSON
8. Body: `{{ $json }}`

### Workflow JSON (Import This)

```json
{
  "nodes": [
    {
      "name": "Granola Webhook",
      "type": "n8n-nodes-base.webhook",
      "position": [250, 300],
      "webhookId": "granola-transcript",
      "parameters": {
        "httpMethod": "POST",
        "path": "granola-transcript",
        "responseMode": "onReceived",
        "responseData": "allEntries"
      }
    },
    {
      "name": "Send to Moneypenny",
      "type": "n8n-nodes-base.httpRequest",
      "position": [500, 300],
      "parameters": {
        "url": "https://dash.universalexports.company/api/granola/ingest",
        "method": "POST",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendBody": true,
        "bodyParameters": {
          "parameters": [
            {
              "name": "={{ $json }}",
              "value": ""
            }
          ]
        },
        "options": {}
      }
    }
  ],
  "connections": {
    "Granola Webhook": {
      "main": [
        [
          {
            "node": "Send to Moneypenny",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  }
}
```

## Files

- `granola_sync.py` - Main sync script
- `token_manager.py` - Token refresh logic
- `config.json` - Your credentials (gitignored)
