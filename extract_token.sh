#!/bin/bash
# Extract Granola credentials and create config.json
# Run this on a Mac where Granola is logged in

set -e

GRANOLA_FILE="$HOME/Library/Application Support/Granola/supabase.json"
CONFIG_FILE="config.json"

echo "🥣 Granola Token Extractor"
echo "=========================="

# Check if Granola file exists
if [ ! -f "$GRANOLA_FILE" ]; then
    echo "❌ Granola data file not found at:"
    echo "   $GRANOLA_FILE"
    echo ""
    echo "Make sure Granola is installed and you're logged in."
    exit 1
fi

# Check for jq
if ! command -v jq &> /dev/null; then
    echo "❌ jq is required but not installed."
    echo "   Install with: brew install jq"
    exit 1
fi

# Extract workos_tokens JSON string and parse it
WORKOS_TOKENS=$(jq -r '.workos_tokens' "$GRANOLA_FILE" 2>/dev/null)

if [ -z "$WORKOS_TOKENS" ] || [ "$WORKOS_TOKENS" = "null" ]; then
    echo "❌ No workos_tokens found in Granola data."
    echo "   Make sure you're logged into Granola."
    exit 1
fi

# Parse the tokens (it's a JSON string inside the JSON)
REFRESH_TOKEN=$(echo "$WORKOS_TOKENS" | jq -r '.refresh_token')
ACCESS_TOKEN=$(echo "$WORKOS_TOKENS" | jq -r '.access_token')

if [ -z "$REFRESH_TOKEN" ] || [ "$REFRESH_TOKEN" = "null" ]; then
    echo "❌ No refresh_token found."
    exit 1
fi

# Extract client_id from JWT payload
# JWT format: header.payload.signature - we need to decode the payload
JWT_PAYLOAD=$(echo "$ACCESS_TOKEN" | cut -d. -f2)

# Add padding if needed for base64
PADDED_PAYLOAD="$JWT_PAYLOAD"
case $((${#PADDED_PAYLOAD} % 4)) in
    2) PADDED_PAYLOAD="${PADDED_PAYLOAD}==" ;;
    3) PADDED_PAYLOAD="${PADDED_PAYLOAD}=" ;;
esac

# Decode and extract client_id
CLIENT_ID=$(echo "$PADDED_PAYLOAD" | base64 -d 2>/dev/null | jq -r '.iss // empty' | grep -oE 'client_[a-zA-Z0-9_]+' || true)

if [ -z "$CLIENT_ID" ]; then
    echo "⚠️  Could not extract client_id from JWT."
    echo "   You may need to find it manually."
    CLIENT_ID="client_PLACEHOLDER"
fi

# Backup existing config
if [ -f "$CONFIG_FILE" ]; then
    BACKUP_FILE="config.json.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$CONFIG_FILE" "$BACKUP_FILE"
    echo "📁 Backed up existing config to $BACKUP_FILE"
fi

# Create config.json
cat > "$CONFIG_FILE" << EOF
{
  "refresh_token": "$REFRESH_TOKEN",
  "client_id": "$CLIENT_ID",
  "extracted_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo ""
echo "✅ Created $CONFIG_FILE"
echo ""
echo "   refresh_token: ${REFRESH_TOKEN:0:10}...${REFRESH_TOKEN: -5}"
echo "   client_id:     $CLIENT_ID"
echo ""

if [ "$CLIENT_ID" = "client_PLACEHOLDER" ]; then
    echo "⚠️  WARNING: client_id is a placeholder. You need to find the real value."
    echo "   Try: https://dashboard.workos.com or check Granola's network requests."
    echo ""
fi

echo "Next steps:"
echo "  1. Run: python3 granola_sync.py --webhook YOUR_WEBHOOK_URL --dry-run"
echo "  2. Check the output looks correct"
echo "  3. Run without --dry-run to actually sync"
echo ""
echo "🍸 Cheers!"
