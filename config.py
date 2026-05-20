"""
Configuration for Screentime Tracker Cloud Sync.

SETUP INSTRUCTIONS:
1. Go to https://supabase.com → Start a project
2. In the SQL Editor, run the SQL from supabase_setup.sql
3. Go to Settings → API → copy your Project URL and anon/public key
4. Paste them below
"""

# ─── SUPABASE CREDENTIALS ───
# These will be baked into the .exe. Get them from:
# Supabase Dashboard → Settings → API → Project URL + anon key
SUPABASE_URL = "https://civrdwybhcphwbqxsnhc.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNpdnJkd3liaGNwaHdicXhzbmhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkyMDY0OTYsImV4cCI6MjA5NDc4MjQ5Nn0.Knakff7i_JFnsSks9eBv8kKMKPdENn-WYo6W6uOvASo"

# ─── SYNC SETTINGS ───
# How often to push current activity to the cloud (in seconds)
PUSH_INTERVAL_SECONDS = 5

# ─── APP BEHAVIOR ───
# Show the dashboard window on launch (True) or run silent in tray (False)
SHOW_WINDOW_ON_LAUNCH = True
