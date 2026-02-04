#!/usr/bin/env python3
"""
Granola Sync - Interactive CLI
Simple interface for syncing Granola transcripts

Just run: python3 sync.py
"""
import os
import subprocess
import sys
import json
from pathlib import Path

# Default webhook (Moneypenny dashboard)
DEFAULT_WEBHOOK = "http://localhost:18793/api/granola/ingest?token=1a31f2f19e100e3f33f52125b1ffb9fd6947014b41e395f1"
CONFIG_FILE = "config.json"
SETTINGS_FILE = "settings.json"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

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

def get_version():
    """Get current version from granola_sync.py"""
    try:
        with open(os.path.join(SCRIPT_DIR, 'granola_sync.py')) as f:
            for line in f:
                if line.startswith('__version__'):
                    return line.split('"')[1]
    except:
        pass
    return "unknown"

def interactive_menu():
    """Show interactive menu"""
    settings = load_settings()
    webhook = settings.get('webhook', DEFAULT_WEBHOOK)
    version = get_version()
    
    print("")
    print(f"🥣 Granola Sync v{version}")
    print("=" * 40)
    print("")
    print("What would you like to do?")
    print("")
    print("  1. Sync new transcripts (since last sync)")
    print("  2. Sync ALL transcripts (full backlog)")
    print("  3. Sync last 24 hours")
    print("  4. Sync last 7 days")
    print("  5. Preview what would sync (dry run)")
    print("  ─────────────────────────────")
    print("  6. Setup auto-sync (cron job)")
    print("  7. Update to latest version")
    print("  8. Settings")
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
    """Automatically set up cron job"""
    print("")
    print("📅 Setting up auto-sync...")
    print("")
    
    # Check current crontab
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        current_crontab = result.stdout if result.returncode == 0 else ""
    except:
        current_crontab = ""
    
    # Check if already installed
    if 'granola_sync.py' in current_crontab or 'granola-sync' in current_crontab:
        print("✓ Cron job already installed!")
        print("")
        print("Current schedule:")
        for line in current_crontab.split('\n'):
            if 'granola' in line.lower():
                print(f"  {line}")
        print("")
        
        update = input("Update the cron job? [y/N]: ").strip().lower()
        if update != 'y':
            return
        
        # Remove old entries
        lines = [l for l in current_crontab.split('\n') 
                 if 'granola_sync.py' not in l and 'granola-sync' not in l and l.strip()]
        current_crontab = '\n'.join(lines)
    
    # Ask for frequency
    print("How often should it sync?")
    print("  1. Every 5 minutes (recommended)")
    print("  2. Every 15 minutes")
    print("  3. Every hour")
    print("  4. Custom")
    print("")
    freq = input("Choice [1]: ").strip() or "1"
    
    if freq == "1":
        schedule = "*/5 * * * *"
    elif freq == "2":
        schedule = "*/15 * * * *"
    elif freq == "3":
        schedule = "0 * * * *"
    elif freq == "4":
        schedule = input("Enter cron schedule (e.g., */10 * * * *): ").strip()
    else:
        schedule = "*/5 * * * *"
    
    # Build cron line
    log_file = os.path.join(SCRIPT_DIR, 'sync.log')
    cron_line = f"{schedule} cd {SCRIPT_DIR} && /usr/bin/python3 granola_sync.py --webhook '{webhook}' >> {log_file} 2>&1"
    
    # Add to crontab
    new_crontab = current_crontab.strip()
    if new_crontab:
        new_crontab += "\n"
    new_crontab += f"# Granola Sync - auto-sync transcripts\n{cron_line}\n"
    
    try:
        # Write new crontab
        process = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, text=True)
        process.communicate(input=new_crontab)
        
        if process.returncode == 0:
            print("")
            print("✅ Cron job installed!")
            print(f"   Schedule: {schedule}")
            print(f"   Log file: {log_file}")
            print("")
            print("Transcripts will now sync automatically.")
        else:
            print("❌ Failed to install cron job")
    except Exception as e:
        print(f"❌ Error: {e}")

def remove_cron():
    """Remove the cron job"""
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        if result.returncode != 0:
            print("No crontab found.")
            return
        
        current = result.stdout
        if 'granola_sync.py' not in current and 'granola-sync' not in current:
            print("No Granola Sync cron job found.")
            return
        
        # Remove granola lines
        lines = [l for l in current.split('\n') 
                 if 'granola_sync.py' not in l and 'granola-sync' not in l 
                 and 'Granola Sync' not in l and l.strip()]
        new_crontab = '\n'.join(lines) + '\n' if lines else ""
        
        process = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, text=True)
        process.communicate(input=new_crontab)
        
        print("✅ Cron job removed.")
    except Exception as e:
        print(f"❌ Error: {e}")

def update_tool():
    """Update to latest version via git pull"""
    print("")
    print("🔄 Checking for updates...")
    print("")
    
    # Check if we're in a git repo
    if not os.path.exists(os.path.join(SCRIPT_DIR, '.git')):
        print("❌ Not a git repository. Manual update required.")
        print(f"   cd {SCRIPT_DIR}")
        print("   git clone https://github.com/moneypenny-agent/granola-sync.git .")
        return
    
    try:
        # Fetch latest
        subprocess.run(['git', 'fetch'], cwd=SCRIPT_DIR, capture_output=True)
        
        # Check if updates available
        result = subprocess.run(
            ['git', 'status', '-uno'], 
            cwd=SCRIPT_DIR, 
            capture_output=True, 
            text=True
        )
        
        if 'behind' in result.stdout:
            print("📥 Updates available!")
            print("")
            
            # Show what's new
            result = subprocess.run(
                ['git', 'log', '--oneline', 'HEAD..origin/main', '-5'],
                cwd=SCRIPT_DIR,
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                print("Recent changes:")
                for line in result.stdout.strip().split('\n'):
                    print(f"  • {line}")
                print("")
            
            confirm = input("Install updates? [Y/n]: ").strip().lower()
            if confirm != 'n':
                result = subprocess.run(
                    ['git', 'pull', 'origin', 'main'],
                    cwd=SCRIPT_DIR,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    print("")
                    print("✅ Updated successfully!")
                    print("   Restart sync.py to use new version.")
                else:
                    print(f"❌ Update failed: {result.stderr}")
        else:
            print("✅ Already up to date!")
            print(f"   Version: {get_version()}")
    except Exception as e:
        print(f"❌ Error checking for updates: {e}")

def show_settings(webhook, settings):
    """Show current settings"""
    print("")
    print("📋 Settings")
    print("=" * 40)
    print("")
    print(f"  Version:  {get_version()}")
    print(f"  Webhook:  {webhook[:50]}..." if len(webhook) > 50 else f"  Webhook:  {webhook}")
    print(f"  Config:   {CONFIG_FILE}")
    print(f"  Dir:      {SCRIPT_DIR}")
    
    if Path("sync_state.json").exists():
        with open("sync_state.json") as f:
            state = json.load(f)
        print(f"  Synced:   {len(state.get('synced_ids', []))} documents")
        print(f"  Last:     {state.get('last_sync', 'never')}")
    
    # Check cron status
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        if result.returncode == 0 and 'granola_sync.py' in result.stdout:
            print(f"  Cron:     ✓ Enabled")
        else:
            print(f"  Cron:     ✗ Not set up")
    except:
        print(f"  Cron:     ? Unknown")
    
    print("")
    print("Options:")
    print("  1. Change webhook URL")
    print("  2. Remove cron job")
    print("  3. Reset sync state (re-sync everything)")
    print("  0. Back")
    print("")
    
    choice = input("Choice [0]: ").strip() or "0"
    
    if choice == "1":
        new_webhook = input(f"New webhook URL: ").strip()
        if new_webhook:
            settings['webhook'] = new_webhook
            save_settings(settings)
            print(f"✅ Webhook updated!")
    elif choice == "2":
        remove_cron()
    elif choice == "3":
        confirm = input("Reset sync state? This will re-sync all documents. [y/N]: ").strip().lower()
        if confirm == 'y':
            if Path("sync_state.json").exists():
                os.remove("sync_state.json")
                print("✅ Sync state reset.")

def main():
    os.chdir(SCRIPT_DIR)  # Ensure we're in the right directory
    
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
            setup_cron(webhook)
        
        elif choice == "7":
            update_tool()
        
        elif choice == "8":
            show_settings(webhook, settings)
            continue  # Don't show "Press Enter" after settings submenu
        
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
