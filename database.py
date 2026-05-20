import sqlite3
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = "screentime.db"):
        self.db_path = db_path
        self._init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initializes the SQLite database with required tables."""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Apps table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS apps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exe_path TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT DEFAULT 'neutral'
                )
            ''')
            
            # Activity Log table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id INTEGER NOT NULL,
                    window_title TEXT,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME NOT NULL,
                    duration INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (app_id) REFERENCES apps (id)
                )
            ''')
            
            # Create an index for faster analytics querying
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_time ON activity_log(start_time, end_time)')
            
            conn.commit()
            logger.info("Database initialized successfully.")

    def get_or_create_app(self, exe_path: str, name: str) -> int:
        """Returns the app ID, creating a new record if it doesn't exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Try to find existing
            cursor.execute('SELECT id FROM apps WHERE exe_path = ?', (exe_path,))
            result = cursor.fetchone()
            if result:
                return result[0]
            
            # Insert new
            cursor.execute('INSERT INTO apps (exe_path, name) VALUES (?, ?)', (exe_path, name))
            conn.commit()
            return cursor.lastrowid

    def update_app_category(self, app_id: int, category: str):
        """Updates the category of an app (e.g., 'productive', 'distracting')."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE apps SET category = ? WHERE id = ?', (category, app_id))
            conn.commit()

    def start_session(self, app_id: int, window_title: str) -> int:
        """Starts a new activity session and returns the session ID."""
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO activity_log (app_id, window_title, start_time, end_time, duration)
                VALUES (?, ?, ?, ?, ?)
            ''', (app_id, window_title, now, now, 0))
            conn.commit()
            return cursor.lastrowid

    def update_session_window_title(self, session_id: int, window_title: str):
        """Updates the window title of an active session (e.g. tab switch in browser)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE activity_log SET window_title = ? WHERE id = ?', (window_title, session_id))
            conn.commit()

    def update_session(self, session_id: int, start_time: datetime):
        """Updates the end_time and duration of an ongoing session."""
        now = datetime.now()
        end_time_iso = now.isoformat()
        duration = int((now - start_time).total_seconds())
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE activity_log 
                SET end_time = ?, duration = ? 
                WHERE id = ?
            ''', (end_time_iso, duration, session_id))
            conn.commit()
