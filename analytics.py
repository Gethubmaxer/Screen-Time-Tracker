import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any
from database import Database

class Analytics:
    def __init__(self, db: Database):
        self.db = db

    def get_summary_by_date_range(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Returns total duration per app within a specific date range."""
        start_iso = start_date.isoformat()
        end_iso = end_date.isoformat()
        
        with self.db.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT a.name, a.category, SUM(l.duration) as total_duration
                FROM activity_log l
                JOIN apps a ON l.app_id = a.id
                WHERE l.start_time >= ? AND l.end_time <= ?
                GROUP BY a.id
                ORDER BY total_duration DESC
            ''', (start_iso, end_iso))
            
            return [dict(row) for row in cursor.fetchall()]

    def get_todays_summary(self) -> List[Dict[str, Any]]:
        """Returns today's usage summary."""
        now = datetime.now()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.get_summary_by_date_range(start_of_day, now)

    def get_weekly_summary(self) -> List[Dict[str, Any]]:
        """Returns the last 7 days usage summary."""
        now = datetime.now()
        start_of_week = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        return self.get_summary_by_date_range(start_of_week, now)

    def get_category_breakdown(self, start_date: datetime, end_date: datetime) -> Dict[str, int]:
        """Returns total duration per category within a date range."""
        start_iso = start_date.isoformat()
        end_iso = end_date.isoformat()
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT a.category, SUM(l.duration) as total_duration
                FROM activity_log l
                JOIN apps a ON l.app_id = a.id
                WHERE l.start_time >= ? AND l.end_time <= ?
                GROUP BY a.category
            ''', (start_iso, end_iso))
            
            return {row[0]: row[1] for row in cursor.fetchall()}

    def get_recent_timeline(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns the most recently used unique apps and the last time they were used."""
        with self.db.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT a.name, a.category, MAX(l.start_time) as start_time, l.duration
                FROM activity_log l
                JOIN apps a ON l.app_id = a.id
                GROUP BY a.id
                ORDER BY start_time DESC
                LIMIT ?
            ''', (limit,))
            
            return [dict(row) for row in cursor.fetchall()]

    def get_weekly_in_depth(self) -> Dict[str, Dict[str, int]]:
        """Returns usage per app per day for the last 7 days."""
        now = datetime.now()
        start_of_week = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.name, date(l.start_time) as log_date, SUM(l.duration) as daily_duration
                FROM activity_log l
                JOIN apps a ON l.app_id = a.id
                WHERE l.start_time >= ?
                GROUP BY a.id, log_date
            ''', (start_of_week.isoformat(),))
            
            results = {}
            for row in cursor.fetchall():
                app_name, log_date, duration = row
                if app_name not in results:
                    results[app_name] = {}
                results[app_name][log_date] = duration
                
            return results
