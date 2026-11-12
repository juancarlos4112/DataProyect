# -*- coding: utf-8 -*-
"""Acceso a datos (SQLite) y utilidades de fecha/hora."""
import os
import sqlite3
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Santiago")
except Exception:  # pragma: no cover
    TZ = None

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(BASE, "data")
DB_PATH = os.path.join(DATA_DIR, "app.db")
UPLOADS = os.path.join(DATA_DIR, "uploads")
PDFS = os.path.join(DATA_DIR, "pdfs")
OUTBOX = os.path.join(DATA_DIR, "outbox")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'tech',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    rut TEXT DEFAULT '',
    contact TEXT DEFAULT '',
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    address TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    site TEXT DEFAULT '',
    racks TEXT DEFAULT '',
    recipients TEXT DEFAULT '',
    cc TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients (id)
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    project_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL DEFAULT 'preventiva',
    performed_at TEXT NOT NULL,
    rack TEXT DEFAULT '',
    site TEXT DEFAULT '',
    checklist TEXT DEFAULT '[]',
    work TEXT DEFAULT '',
    materials TEXT DEFAULT '',
    observations TEXT DEFAULT '',
    receiver TEXT DEFAULT '',
    email_to TEXT DEFAULT '',
    email_cc TEXT DEFAULT '',
    email_status TEXT DEFAULT '',
    email_detail TEXT DEFAULT '',
    pdf_file TEXT DEFAULT '',
    signature_file TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'otro',
    created_at TEXT NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders (id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def now():
    return datetime.now(TZ) if TZ else datetime.now()


def now_iso():
    return now().strftime("%Y-%m-%d %H:%M:%S")


def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init():
    for d in (UPLOADS, PDFS, OUTBOX):
        os.makedirs(d, exist_ok=True)
    con = connect()
    try:
        con.executescript(SCHEMA)
        con.commit()
    finally:
        con.close()


def query(sql, args=()):
    con = connect()
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def one(sql, args=()):
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql, args=()):
    con = connect()
    try:
        cur = con.execute(sql, args)
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def get_setting(key, default=""):
    row = one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row and row["value"] is not None else default


def set_setting(key, value):
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def settings_dict(keys):
    return {k: get_setting(k) for k in keys}
