import sqlite3, json, datetime
from contextlib import contextmanager
from pathlib import Path
from db import DB_PATH, get_conn  # reuse existing helpers

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "settings.json"

def init_users_table():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'operator',
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

def add_user_raw(username, password_hash, role='operator'):
    init_users_table()
    with get_conn() as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                      (username, password_hash, role, datetime.datetime.utcnow().isoformat()))
            conn.commit()
            return c.lastrowid
        except Exception:
            return None

def get_user_by_username(username):
    init_users_table()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id, username, password_hash, role FROM users WHERE username = ?", (username,))
        r = c.fetchone()
        if not r:
            return None
        return {"id": r[0], "username": r[1], "password_hash": r[2], "role": r[3]}

def load_settings():
    if not SETTINGS_PATH.exists():
        default = {
            "tolerance": 0.45,
            "last_updated": datetime.datetime.utcnow().isoformat(),
            "attendance_alert_threshold": 75,
            "liveness_enabled": True,
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_username": "",
            "smtp_password": "",
            "smtp_from": "",
            "smtp_use_tls": True,
        }
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
        return default
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Backfill any new keys for settings.json files created by older versions
    defaults = {
        "attendance_alert_threshold": 75,
        "liveness_enabled": True,
        "smtp_host": "", "smtp_port": 587, "smtp_username": "",
        "smtp_password": "", "smtp_from": "", "smtp_use_tls": True,
    }
    changed = False
    for k, v in defaults.items():
        if k not in data:
            data[k] = v
            changed = True
    if changed:
        save_settings(data)
    return data

def save_settings(d):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    return True
