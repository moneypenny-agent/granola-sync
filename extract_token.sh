#!/bin/bash
# Extract Granola tokens from local app storage
# Run this on the Mac where Granola is installed

GRANOLA_FILE="$HOME/Library/Application Support/Granola/supabase.json"

if [ ! -f "$GRANOLA_FILE" ]; then
    echo "ERROR: Granola data not found at $GRANOLA_FILE"
    echo "Make sure Granola is installed and you're logged in."
    exit 1
fi

echo "Extracting Granola credentials..."
echo ""

# Extract refresh token
REFRESH_TOKEN=$(cat "$GRANOLA_FILE" | jq -r '.workos_tokens | fromjson | .refresh_token')
echo "refresh_token: $REFRESH_TOKEN"
echo ""

# Extract client_id from JWT
ACCESS_TOKEN=$(cat "$GRANOLA_FILE" | jq -r '.workos_tokens | fromjson | .access_token')
CLIENT_ID=$(echo "$ACCESS_TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq -r '.iss' | grep -oE 'client_[a-zA-Z0-9_]+')
echo "client_id: $CLIENT_ID"
echo ""

# Create config.json
echo "Creating config.json..."
cat > config.json << EOF
{
  "refresh_token": "$REFRESH_TOKEN",
  "client_id": "$CLIENT_ID"
}
EOF

echo "Done! config.json created."
echo ""
echo "IMPORTANT: After extracting, quit Granola completely and remove its data:"
echo "  rm -rf ~/Library/Application\ Support/Granola/"
echo ""
echo "This prevents Granola from invalidating your token on next launch."
