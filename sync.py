#!/usr/bin/env python3
"""
Granola Sync - Interactive CLI
Simple interface for syncing Granola transcripts

Just run: python3 sync.py
"""
import os
import sys
import json
from pathlib import Path

# Default webhook (Moneypenny dashboard)
DEFAULT_WEBHOOK = "http://localhost:18793/api/granola/ingest?token=1a31f2f19e100e3f33f52125b1ffb9fd6947014b41e395f1"
CONFIG_FILE = "config.json"
SETTINGS_FILE = "settings.json"

def load_settings():
    """Load saved settings"""
    if Path(SETTINGS_FILE).exists():
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    return {}

def save_settings(settings):
    """Save settings for next time"""
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

def check_config():
    """Check if Granola credentials are configured"""
    if not Path(CONFIG_FILE).exists():
        print("❌ No config.json found!")
        print("")
        print("Run ./extract_token.sh first to get your Granola credentials.")
        print("(Make sure Granola is logged in on this Mac)")
        return False
    
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    
    if not config.get('refresh_token') or not config.get('client_id'):
        print("❌ config.json is missing refresh_token or client_id")
        print("Run ./extract_token.sh to fix this.")
        return False
    
    return True

def interactive_menu():
    """Show interactive menu"""
    settings = load_settings()
    webhook = settings.get('webhook', DEFAULT_WEBHOOK)
    
    print("")
    print("🥣 Granola Sync")
    print("=" * 40)
    print("")
    print("What would you like to do?")
    print("")
    print("  1. Sync new transcripts (since last sync)")
    print("  2. Sync ALL transcripts (full backlog)")
    print("  3. Sync last 24 hours")
    print("  4. Sync last 7 days")
    print("  5. Preview what would sync (dry run)")
    print("  6. Change webhook URL")
    print("  7. Show current settings")
    print("  8. Setup cron job (auto-sync)")
    print("  0. Exit")
    print("")
    
    choice = input("Enter choice [1]: ").strip() or "1"
    return choice, webhook, settings

def run_sync(webhook, hours=None, force_all=False, dry_run=False):
    """Run the sync with given options"""
    from granola_sync import GranolaSync, TokenManager, setup_logging
    
    logger = setup_logging(verbose=False)
    
    tm = TokenManager(config_file=CONFIG_FILE)
    if not tm.get_valid_token():
        print("❌ Could not get valid token. Run ./extract_token.sh")
        return False
    
    sync = GranolaSync(
        token_manager=tm,
        webhook_url=webhook,
        state_file="sync_state.json"
    )
    
    # Default to large hour range for "all" or recent for normal sync
    if hours is None:
        hours = 8760 if force_all else 168  # 1 year or 1 week
    
    stats = sync.sync(
        since_hours=hours,
        force_all=force_all,
        dry_run=dry_run
    )
    
    print("")
    print(f"✅ Done! {stats['synced']} synced, {stats['failed']} failed")
    print(f"   ({stats['new']} new of {stats['total']} total)")
    
    return stats['failed'] == 0

def setup_cron(webhook):
    """Help set up cron job"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("")
    print("📅 Cron Setup")
    print("=" * 40)
    print("")
    print("Add this to your crontab (crontab -e):")
    print("")
    print(f"# Granola Sync - every 5 minutes")
    print(f"*/5 * * * * cd {script_dir} && python3 granola_sync.py --webhook '{webhook}' >> /tmp/granola-sync.log 2>&1")
    print("")
    print("Or for hourly sync:")
    print(f"0 * * * * cd {script_dir} && python3 granola_sync.py --webhook '{webhook}' >> /tmp/granola-sync.log 2>&1")
    print("")
    input("Press Enter to continue...")

def main():
    # Quick check for config
    if not check_config():
        sys.exit(1)
    
    while True:
        choice, webhook, settings = interactive_menu()
        
        if choice == "0":
            print("👋 Bye!")
            break
        
        elif choice == "1":
            print("\n🔄 Syncing new transcripts...")
            run_sync(webhook, hours=168, force_all=False)
        
        elif choice == "2":
            print("\n🔄 Syncing ALL transcripts (this may take a while)...")
            run_sync(webhook, hours=8760, force_all=True)
        
        elif choice == "3":
            print("\n🔄 Syncing last 24 hours...")
            run_sync(webhook, hours=24, force_all=False)
        
        elif choice == "4":
            print("\n🔄 Syncing last 7 days...")
            run_sync(webhook, hours=168, force_all=False)
        
        elif choice == "5":
            print("\n👀 Preview (dry run)...")
            run_sync(webhook, hours=168, force_all=False, dry_run=True)
        
        elif choice == "6":
            print(f"\nCurrent webhook: {webhook}")
            new_webhook = input("New webhook URL (or Enter to keep): ").strip()
            if new_webhook:
                settings['webhook'] = new_webhook
                save_settings(settings)
                print(f"✅ Webhook updated to: {new_webhook}")
        
        elif choice == "7":
            print("\n📋 Current Settings:")
            print(f"  Webhook: {webhook}")
            print(f"  Config: {CONFIG_FILE}")
            if Path("sync_state.json").exists():
                with open("sync_state.json") as f:
                    state = json.load(f)
                print(f"  Synced documents: {len(state.get('synced_ids', []))}")
                print(f"  Last sync: {state.get('last_sync', 'never')}")
        
        elif choice == "8":
            setup_cron(webhook)
        
        else:
            print("❓ Unknown option")
        
        print("")
        input("Press Enter to continue...")

if __name__ == "__main__":
    # If run with arguments, pass through to main script
    if len(sys.argv) > 1:
        import granola_sync
        granola_sync.main()
    else:
        main()
