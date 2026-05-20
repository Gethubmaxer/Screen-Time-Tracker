"""
Cloud sync module for Screentime Tracker.
Pushes tracking data to Supabase for remote monitoring via web dashboard.

Uses only stdlib (urllib) - no extra dependencies required.
Runs in a background thread, silently handles errors.
"""

import json
import logging
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class CloudSync:
    """Pushes current activity and session data to Supabase REST API."""

    def __init__(self, supabase_url: str, supabase_key: str, push_interval: int = 5, version: str = ""):
        self.supabase_url = supabase_url.rstrip("/")
        self.supabase_key = supabase_key
        self.push_interval = push_interval
        self._version = version

        self.running = False
        self._thread: Optional[threading.Thread] = None

        # Current app state (set by tracker via update_current_app)
        self._app_name = ""
        self._window_title = ""
        self._exe_path = ""
        self._category = "neutral"
        self._session_start: Optional[datetime] = None

        self._lock = threading.Lock()

        # Common headers for Supabase REST API
        self._headers = {
            "Content-Type": "application/json",
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
        }

        # Track last push to avoid excess 429s
        self._last_push_time = 0.0

        # Offline retry queue: sessions that failed to push go here,
        # re-tried by _sync_loop every cycle.
        self._pending_sessions: list[dict] = []
        self._pending_lock = threading.Lock()

    def update_current_app(
        self,
        app_name: str,
        window_title: str,
        exe_path: str,
        category: str = "neutral",
        session_start: Optional[datetime] = None,
    ):
        """Called by the tracker when the active window changes."""
        with self._lock:
            self._app_name = app_name
            self._window_title = window_title or ""
            self._exe_path = exe_path
            self._category = category
            self._session_start = session_start

    @staticmethod
    def _naive_local_to_utc_str(dt: Optional[datetime]) -> Optional[str]:
        """Convert a naive local datetime to a UTC ISO string ending in Z.

        Tracker.py stores timestamps as naive local datetimes (e.g. datetime.now()).
        Supabase TIMESTAMPTZ interprets bare strings as UTC, creating a timezone
        offset bug on the dashboard. This method converts to proper UTC.

        Returns None if dt is None, or a string like '2026-05-19T13:53:00.123456Z'.
        """
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        # Naive datetime — assume it's local time, convert to UTC.
        # time.timezone / time.altzone are seconds WEST of UTC (positive in the US).
        is_dst = time.localtime().tm_isdst
        offset_sec = time.altzone if (is_dst and time.daylight) else time.timezone
        dt_utc = dt + timedelta(seconds=offset_sec)
        return dt_utc.isoformat() + "Z"

    def _push_current_activity(self):
        """UPSERT the current activity into the current_activity table (singleton id=1)."""
        with self._lock:
            app_name = self._app_name
            window_title = self._window_title
            exe_path = self._exe_path
            category = self._category
            session_start = self._session_start

        if not app_name:
            return

        now_utc = datetime.utcnow().isoformat() + "Z"
        payload = {
            "id": 1,
            "app_name": app_name,
            "window_title": window_title,
            "exe_path": exe_path,
            "category": category,
            "version": self._version,
            "started_at": self._naive_local_to_utc_str(session_start) if session_start else now_utc,
            "updated_at": now_utc,
        }

        data = json.dumps(payload).encode("utf-8")
        url = f"{self.supabase_url}/rest/v1/current_activity"

        # POST with resolution=merge-duplicates handles both insert and update
        # reliably, unlike PUT which returns different errors depending on PostgREST version
        headers = {**self._headers, "Prefer": "resolution=merge-duplicates"}
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logger.debug(f"Cloud sync: push failed: {e}")

    def push_completed_session(
        self,
        app_name: str,
        window_title: str,
        exe_path: str,
        category: str,
        start_time: datetime,
        end_time: datetime,
        duration_seconds: int,
    ):
        """Called by the tracker when a session ends. Queues it for retry-safe push."""
        payload = {
            "app_name": app_name,
            "window_title": window_title or "",
            "exe_path": exe_path,
            "category": category,
            "start_time": self._naive_local_to_utc_str(start_time) or "",
            "end_time": self._naive_local_to_utc_str(end_time) or "",
            "duration_seconds": duration_seconds,
        }
        with self._pending_lock:
            self._pending_sessions.append(payload)

    def _push_one_session(self, session: dict) -> bool:
        """Try to push a single session. Returns True on success."""
        data = json.dumps(session).encode("utf-8")
        url = f"{self.supabase_url}/rest/v1/activity_logs"
        req = urllib.request.Request(url, data=data, headers=self._headers, method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            return True
        except Exception as e:
            logger.debug(f"Cloud sync: session push failed (queued for retry): {e}")
            return False

    def _flush_pending_sessions(self):
        """Push all queued sessions. Failed ones stay in queue for next cycle."""
        with self._pending_lock:
            pending = self._pending_sessions.copy()
            self._pending_sessions.clear()
        if not pending:
            return
        failed = [s for s in pending if not self._push_one_session(s)]
        if failed:
            with self._pending_lock:
                self._pending_sessions.extend(failed)
            logger.info(f"Cloud sync: {len(failed)}/{len(pending)} sessions queued for retry")
        elif len(pending) > 1:
            logger.info(f"Cloud sync: flushed {len(pending)} queued sessions")

    def _sync_loop(self):
        """Background loop that pushes current activity + pending sessions."""
        logger.info("Cloud sync loop started")
        while self.running:
            try:
                now = time.time()
                # Rate-limit: don't push faster than push_interval
                if now - self._last_push_time >= self.push_interval:
                    self._push_current_activity()
                    self._flush_pending_sessions()
                    self._last_push_time = now
            except Exception:
                # Absorb all errors - cloud sync must never crash the app
                pass
            time.sleep(1)  # Check every second but rate-limit above

    def start(self):
        """Start the cloud sync background thread."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()
        logger.info("Cloud sync started")

    def stop(self):
        """Stop the cloud sync thread."""
        self.running = False
        logger.info("Cloud sync stopped")
