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
from datetime import datetime
from pathlib import Path

# Default webhook (Moneypenny dashboard)
DEFAULT_WEBHOOK = "http://localhost:18793/api/granola/ingest?token=1a31f2f19e100e3f33f52125b1ffb9fd6947014b41e395f1"
CONFIG_FILE = "config.json"
SETTINGS_FILE = "settings.json"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "sync.log")

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

def check_config():
    """Check if Granola credentials are configured"""
    if not Path(CONFIG_FILE).exists():
        return False
    
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
        return bool(config.get('refresh_token') and config.get('client_id'))
    except:
        return False

def first_run_setup():
    """First-run setup wizard"""
    print("")
    print("🥣 Welcome to Granola Sync!")
    print("=" * 40)
    print("")
    print("Looks like this is your first time running.")
    print("Let's get you set up!")
    print("")
    
    # Check if Granola is installed
    granola_file = os.path.expanduser("~/Library/Application Support/Granola/supabase.json")
    if not os.path.exists(granola_file):
        print("❌ Granola data not found.")
        print("")
        print("Make sure:")
        print("  1. Granola is installed on this Mac")
        print("  2. You're logged into Granola")
        print("")
        print("Then run this script again.")
        return False
    
    print("✓ Found Granola installation")
    print("")
    
    # Run extract_token.sh
    print("Extracting your credentials...")
    extract_script = os.path.join(SCRIPT_DIR, 'extract_token.sh')
    
    if os.path.exists(extract_script):
        result = subprocess.run(['bash', extract_script], cwd=SCRIPT_DIR)
        if result.returncode != 0:
            print("")
            print("❌ Token extraction failed.")
            return False
    else:
        print("❌ extract_token.sh not found")
        return False
    
    # Verify config was created
    if not check_config():
        print("")
        print("❌ Config file wasn't created properly.")
        return False
    
    print("")
    print("✅ Setup complete!")
    print("")
    
    # Ask about webhook
    print("Where should transcripts be sent?")
    print("")
    print("  1. Moneypenny Dashboard (default)")
    print("  2. Custom webhook URL")
    print("")
    choice = input("Choice [1]: ").strip() or "1"
    
    settings = load_settings()
    if choice == "2":
        webhook = input("Enter webhook URL: ").strip()
        if webhook:
            settings['webhook'] = webhook
    else:
        settings['webhook'] = DEFAULT_WEBHOOK
    
    save_settings(settings)
    
    # Ask about cron
    print("")
    setup_cron_now = input("Set up automatic syncing now? [Y/n]: ").strip().lower()
    if setup_cron_now != 'n':
        setup_cron(settings.get('webhook', DEFAULT_WEBHOOK))
    
    print("")
    print("🎉 All set! You can now sync your transcripts.")
    print("")
    return True

def test_webhook(webhook):
    """Test if webhook is reachable"""
    import requests
    try:
        # Just check if the endpoint responds
        response = requests.post(
            webhook, 
            json={"test": True, "source": "granola-sync-test"},
            timeout=10
        )
        return response.status_code < 500
    except requests.exceptions.ConnectionError:
        return False
    except Exception as e:
        print(f"   Warning: {e}")
        return False

def show_status(webhook):
    """Show current sync status"""
    print("")
    print("📊 Status")
    print("=" * 40)
    print("")
    
    # Version
    print(f"  Version:     {get_version()}")
    
    # Config status
    if check_config():
        print("  Config:      ✓ Valid")
    else:
        print("  Config:      ✗ Missing or invalid")
    
    # Webhook status
    print(f"  Webhook:     Testing...", end="", flush=True)
    if test_webhook(webhook):
        print("\r  Webhook:     ✓ Reachable    ")
    else:
        print("\r  Webhook:     ✗ Not reachable")
    
    # Sync state
    state_file = os.path.join(SCRIPT_DIR, "sync_state.json")
    if os.path.exists(state_file):
        with open(state_file) as f:
            state = json.load(f)
        synced_count = len(state.get('synced_ids', []))
        last_sync = state.get('last_sync', 'never')
        if last_sync != 'never':
            try:
                dt = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
                last_sync = dt.strftime('%Y-%m-%d %H:%M')
            except:
                pass
        print(f"  Synced:      {synced_count} documents")
        print(f"  Last sync:   {last_sync}")
    else:
        print("  Synced:      0 documents")
        print("  Last sync:   never")
    
    # Cron status
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        if result.returncode == 0 and 'granola_sync.py' in result.stdout:
            # Extract schedule
            for line in result.stdout.split('\n'):
                if 'granola_sync.py' in line:
                    schedule = line.split()[0:5]
                    print(f"  Auto-sync:   ✓ Enabled ({' '.join(schedule)})")
                    break
        else:
            print("  Auto-sync:   ✗ Not configured")
    except:
        print("  Auto-sync:   ? Unknown")
    
    # Recent errors from log
    if os.path.exists(LOG_FILE):
        print("")
        print("  Recent activity:")
        try:
            with open(LOG_FILE) as f:
                lines = f.readlines()[-5:]
            for line in lines:
                line = line.strip()
                if line:
                    # Truncate long lines
                    if len(line) > 60:
                        line = line[:57] + "..."
                    print(f"    {line}")
        except:
            pass
    
    print("")

def view_logs():
    """View recent sync logs"""
    print("")
    print("📜 Recent Logs")
    print("=" * 40)
    print("")
    
    if not os.path.exists(LOG_FILE):
        print("No logs yet. Run a sync first!")
        return
    
    try:
        with open(LOG_FILE) as f:
            lines = f.readlines()
        
        # Show last 30 lines
        for line in lines[-30:]:
            print(line.rstrip())
        
        print("")
        print(f"Log file: {LOG_FILE}")
    except Exception as e:
        print(f"Error reading logs: {e}")

def interactive_menu():
    """Show interactive menu"""
    settings = load_settings()
    webhook = settings.get('webhook', DEFAULT_WEBHOOK)
    version = get_version()
    
    print("")
    print(f"🥣 Granola Sync v{version}")
    print("=" * 40)
    print("")
    print("  1. Sync new transcripts")
    print("  2. Sync ALL transcripts (backlog)")
    print("  3. Sync last 24 hours")
    print("  4. Sync last 7 days")
    print("  5. Preview (dry run)")
    print("  ─────────────────────────────")
    print("  6. Setup auto-sync (cron)")
    print("  7. Check status")
    print("  8. View logs")
    print("  9. Update to latest")
    print("  s. Settings")
    print("  0. Exit")
    print("")
    
    choice = input("Choice [1]: ").strip() or "1"
    return choice, webhook, settings

def run_sync(webhook, hours=None, force_all=False, dry_run=False):
    """Run the sync with given options"""
    from granola_sync import GranolaSync, TokenManager, setup_logging
    
    logger = setup_logging(verbose=False, log_file=LOG_FILE)
    
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
    if 'granola_sync.py' in current_crontab:
        print("✓ Cron job already installed!")
        print("")
        
        update = input("Update the schedule? [y/N]: ").strip().lower()
        if update != 'y':
            return
        
        # Remove old entries
        lines = [l for l in current_crontab.split('\n') 
                 if 'granola_sync.py' not in l and 'Granola Sync' not in l and l.strip()]
        current_crontab = '\n'.join(lines)
    
    # Ask for frequency
    print("How often should it sync?")
    print("  1. Every 5 minutes (recommended)")
    print("  2. Every 15 minutes")
    print("  3. Every hour")
    print("")
    freq = input("Choice [1]: ").strip() or "1"
    
    if freq == "1":
        schedule = "*/5 * * * *"
    elif freq == "2":
        schedule = "*/15 * * * *"
    elif freq == "3":
        schedule = "0 * * * *"
    else:
        schedule = "*/5 * * * *"
    
    # Build cron line
    cron_line = f"{schedule} cd {SCRIPT_DIR} && /usr/bin/python3 granola_sync.py --webhook '{webhook}' >> {LOG_FILE} 2>&1"
    
    # Add to crontab
    new_crontab = current_crontab.strip()
    if new_crontab:
        new_crontab += "\n"
    new_crontab += f"# Granola Sync - auto-sync transcripts\n{cron_line}\n"
    
    try:
        process = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, text=True)
        process.communicate(input=new_crontab)
        
        if process.returncode == 0:
            print("")
            print("✅ Cron job installed!")
            print(f"   Schedule: {schedule}")
            print(f"   Log: {LOG_FILE}")
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
        if 'granola_sync.py' not in current:
            print("No Granola Sync cron job found.")
            return
        
        lines = [l for l in current.split('\n') 
                 if 'granola_sync.py' not in l and 'Granola Sync' not in l and l.strip()]
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
    
    if not os.path.exists(os.path.join(SCRIPT_DIR, '.git')):
        print("❌ Not a git repository.")
        print("   To enable updates, clone from GitHub:")
        print(f"   git clone https://github.com/moneypenny-agent/granola-sync.git")
        return
    
    try:
        subprocess.run(['git', 'fetch'], cwd=SCRIPT_DIR, capture_output=True)
        
        result = subprocess.run(
            ['git', 'status', '-uno'], 
            cwd=SCRIPT_DIR, 
            capture_output=True, 
            text=True
        )
        
        if 'behind' in result.stdout:
            print("📥 Updates available!")
            print("")
            
            result = subprocess.run(
                ['git', 'log', '--oneline', 'HEAD..origin/main', '-5'],
                cwd=SCRIPT_DIR,
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                print("Changes:")
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
                    print("✅ Updated! Restart sync.py to use new version.")
                else:
                    print(f"❌ Update failed: {result.stderr}")
        else:
            print(f"✅ Already up to date (v{get_version()})")
    except Exception as e:
        print(f"❌ Error: {e}")

def show_settings(webhook, settings):
    """Show settings submenu"""
    while True:
        print("")
        print("⚙️  Settings")
        print("=" * 40)
        print("")
        print(f"  Webhook: {webhook[:50]}..." if len(webhook) > 50 else f"  Webhook: {webhook}")
        print("")
        print("  1. Change webhook URL")
        print("  2. Remove cron job")
        print("  3. Reset sync state")
        print("  4. Re-run setup wizard")
        print("  0. Back")
        print("")
        
        choice = input("Choice [0]: ").strip() or "0"
        
        if choice == "0":
            break
        elif choice == "1":
            new_webhook = input("New webhook URL: ").strip()
            if new_webhook:
                settings['webhook'] = new_webhook
                save_settings(settings)
                print("✅ Webhook updated!")
                return new_webhook
        elif choice == "2":
            remove_cron()
        elif choice == "3":
            confirm = input("Reset? This will re-sync all documents. [y/N]: ").strip().lower()
            if confirm == 'y':
                state_file = os.path.join(SCRIPT_DIR, "sync_state.json")
                if os.path.exists(state_file):
                    os.remove(state_file)
                print("✅ Sync state reset.")
        elif choice == "4":
            first_run_setup()
            break
    
    return webhook

def main():
    os.chdir(SCRIPT_DIR)
    
    # First-run setup if no config
    if not check_config():
        if not first_run_setup():
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
            print("\n🔄 Syncing ALL transcripts...")
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
            show_status(webhook)
        elif choice == "8":
            view_logs()
        elif choice == "9":
            update_tool()
        elif choice.lower() == "s":
            webhook = show_settings(webhook, settings)
            continue
        else:
            print("❓ Unknown option")
        
        print("")
        input("Press Enter to continue...")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        import granola_sync
        granola_sync.main()
    else:
        main()
