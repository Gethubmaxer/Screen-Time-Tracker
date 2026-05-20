-- ============================================================
-- Supabase Setup for Screentime Tracker
-- Run this in Supabase Dashboard → SQL Editor
-- ============================================================

-- 1. Current Activity table (singleton row, id=1, constantly updated)
CREATE TABLE IF NOT EXISTS current_activity (
    id BIGINT PRIMARY KEY DEFAULT 1,
    app_name TEXT NOT NULL DEFAULT '',
    window_title TEXT NOT NULL DEFAULT '',
    exe_path TEXT NOT NULL DEFAULT '',
    category TEXT DEFAULT 'neutral',
    version TEXT DEFAULT '',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT single_row CHECK (id = 1)
);

-- 2. Activity Logs table (historical session data)
CREATE TABLE IF NOT EXISTS activity_logs (
    id BIGSERIAL PRIMARY KEY,
    app_name TEXT NOT NULL,
    window_title TEXT,
    exe_path TEXT NOT NULL,
    category TEXT DEFAULT 'neutral',
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Enable Row Level Security (RLS)
ALTER TABLE current_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_logs ENABLE ROW LEVEL SECURITY;

-- 4. Allow anonymous access (this is a personal monitoring tool)
CREATE POLICY "anon_all_current_activity" ON current_activity
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "anon_all_activity_logs" ON activity_logs
    FOR ALL USING (true) WITH CHECK (true);

-- 5. Index start_time for dashboard queries (gte 'start_time' on today's data)
CREATE INDEX IF NOT EXISTS idx_activity_logs_start_time ON activity_logs (start_time DESC);

-- 6. Enable real-time for current_activity (dashboard updates live)
ALTER PUBLICATION supabase_realtime ADD TABLE current_activity;
ALTER PUBLICATION supabase_realtime ADD TABLE activity_logs;

-- 7. Insert initial row for current_activity
INSERT INTO current_activity (id, app_name, window_title, exe_path)
VALUES (1, 'Not running', '', '')
ON CONFLICT (id) DO NOTHING;

-- 8. Migration: add version column to existing table (safe to re-run)
ALTER TABLE current_activity ADD COLUMN IF NOT EXISTS version TEXT DEFAULT '';
