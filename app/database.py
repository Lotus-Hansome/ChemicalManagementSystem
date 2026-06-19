from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.config import DATA_FILE, DB_FILE
from app.seed_data import PERMISSIONS, ROLE_PERMISSIONS, ROLES, USERS, default_data

@contextmanager
def connect(path: str | Path = DB_FILE):
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def initialize_database(path: str | Path = DB_FILE) -> None:
    with connect(path) as conn:
        _create_schema(conn)
        _seed_security(conn)
        _seed_business_data(conn)

def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS roles (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_system INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role_code TEXT NOT NULL REFERENCES roles(code),
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS permissions (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            module TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS role_permissions (
            role_code TEXT NOT NULL REFERENCES roles(code) ON DELETE CASCADE,
            permission_code TEXT NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
            PRIMARY KEY (role_code, permission_code)
        );

        CREATE TABLE IF NOT EXISTS chemicals (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            storage_area TEXT NOT NULL,
            inventory REAL NOT NULL,
            unit TEXT NOT NULL,
            hazard_level TEXT NOT NULL,
            cas TEXT NOT NULL,
            supplier TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS inventory_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chemical_id TEXT NOT NULL REFERENCES chemicals(id),
            changed_at TEXT NOT NULL,
            delta REAL NOT NULL,
            before_value REAL NOT NULL,
            after_value REAL NOT NULL,
            note TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS parameters (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            area TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            low REAL NOT NULL,
            high REAL NOT NULL,
            status TEXT NOT NULL,
            acknowledged INTEGER NOT NULL DEFAULT 0,
            acknowledged_at TEXT,
            acknowledged_by TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS parameter_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parameter_id TEXT NOT NULL REFERENCES parameters(id),
            sampled_at TEXT NOT NULL,
            value REAL NOT NULL,
            status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alarm_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parameter_id TEXT NOT NULL REFERENCES parameters(id),
            parameter_name TEXT NOT NULL,
            area TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            low REAL NOT NULL,
            high REAL NOT NULL,
            status TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            acknowledged INTEGER NOT NULL DEFAULT 0,
            acknowledged_at TEXT,
            acknowledged_by TEXT
        );

        CREATE TABLE IF NOT EXISTS work_orders (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            area TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            owner TEXT NOT NULL,
            created_at TEXT NOT NULL,
            due_date TEXT NOT NULL,
            description TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT NOT NULL,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_parameter_samples_parameter_time
            ON parameter_samples(parameter_id, sampled_at DESC);
        CREATE INDEX IF NOT EXISTS idx_alarm_history_time
            ON alarm_history(occurred_at DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_time
            ON audit_logs(time DESC);
        """
    )

def _seed_security(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT INTO roles(code, name, description, is_system)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            is_system = excluded.is_system
        """,
        ROLES,
    )
    conn.executemany(
        """
        INSERT INTO permissions(code, name, module, description)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            name = excluded.name,
            module = excluded.module,
            description = excluded.description
        """,
        PERMISSIONS,
    )
    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        for permission_code in permission_codes:
            conn.execute(
                """
                INSERT OR IGNORE INTO role_permissions(role_code, permission_code)
                VALUES (?, ?)
                """,
                (role_code, permission_code),
            )
    conn.executemany(
        """
        INSERT OR IGNORE INTO users(username, password, display_name, role_code, active)
        VALUES (?, ?, ?, ?, ?)
        """,
        USERS,
    )

def _seed_business_data(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM chemicals").fetchone()[0] > 0:
        return

    data = _load_seed_data()
    conn.executemany(
        """
        INSERT INTO chemicals(id, name, category, storage_area, inventory, unit, hazard_level, cas, supplier, updated_at)
        VALUES (:id, :name, :category, :storage_area, :inventory, :unit, :hazard_level, :cas, :supplier, :updated_at)
        """,
        data.get("chemicals", []),
    )
    for item in data.get("parameters", []):
        acknowledged = 1 if item.get("acknowledged") else 0
        conn.execute(
            """
            INSERT INTO parameters(id, name, area, value, unit, low, high, status, acknowledged, acknowledged_at, acknowledged_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                item["name"],
                item["area"],
                item["value"],
                item["unit"],
                item["low"],
                item["high"],
                item["status"],
                acknowledged,
                item.get("acknowledged_at"),
                item.get("acknowledged_by"),
                item["updated_at"],
            ),
        )
        conn.execute(
            """
            INSERT INTO parameter_samples(parameter_id, sampled_at, value, status)
            VALUES (?, ?, ?, ?)
            """,
            (item["id"], item["updated_at"], item["value"], item["status"]),
        )
        if item["status"] == "报警":
            conn.execute(
                """
                INSERT INTO alarm_history(parameter_id, parameter_name, area, value, unit, low, high, status, occurred_at, acknowledged)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    item["name"],
                    item["area"],
                    item["value"],
                    item["unit"],
                    item["low"],
                    item["high"],
                    item["status"],
                    item["updated_at"],
                    acknowledged,
                ),
            )
    conn.executemany(
        """
        INSERT INTO work_orders(id, title, area, priority, status, owner, created_at, due_date, description)
        VALUES (:id, :title, :area, :priority, :status, :owner, :created_at, :due_date, :description)
        """,
        data.get("work_orders", []),
    )
    for item in data.get("audit_logs", []):
        conn.execute(
            """
            INSERT INTO audit_logs(time, username, role, action, target, detail)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item.get("time", ""),
                item.get("username", ""),
                item.get("role", ""),
                item.get("action", ""),
                item.get("target", ""),
                item.get("detail", ""),
            ),
        )

def _load_seed_data() -> dict[str, Any]:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return default_data()
