from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import Settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _ensure_columns(conn: sqlite3.Connection, table: str, column_defs: list[str]) -> None:
    existing = _table_columns(conn, table)
    for column_def in column_defs:
        column_name = column_def.split()[0]
        if column_name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")


def init_db(settings: Settings) -> None:
    conn = connect(settings.db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tools (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                kind TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                entrypoint TEXT,
                status TEXT NOT NULL,
                trust_level INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                approved INTEGER NOT NULL DEFAULT 0,
                approval_note TEXT,
                reason TEXT,
                stdout TEXT,
                stderr TEXT,
                exit_code INTEGER,
                timed_out INTEGER NOT NULL DEFAULT 0,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        _ensure_columns(
            conn,
            "tasks",
            [
                "queued_at TEXT",
                "started_at TEXT",
                "finished_at TEXT",
                "attempts INTEGER NOT NULL DEFAULT 0",
                "queue_name TEXT NOT NULL DEFAULT 'default'",
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    if "metadata_json" in data:
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
    if "payload_json" in data:
        data["payload"] = json.loads(data.pop("payload_json") or "{}")
    if "result_json" in data:
        raw = data.pop("result_json")
        data["result"] = json.loads(raw) if raw else None
    return data


def seed_builtin_tools(settings: Settings) -> None:
    existing = {tool["name"] for tool in list_tools(settings)}
    defaults = [
        {
            "name": "python_local",
            "kind": "python",
            "description": "Run a local Python script in the work directory",
            "entrypoint": "python",
            "status": "trusted",
            "trust_level": 2,
            "metadata": {"builtin": True},
        },
        {
            "name": "shell_safe",
            "kind": "shell",
            "description": "Run a restricted shell command in the work directory",
            "entrypoint": "bash",
            "status": "trusted",
            "trust_level": 2,
            "metadata": {"builtin": True},
        },
        {
            "name": "browser_runner",
            "kind": "browser",
            "description": "Headless browser automation runner",
            "entrypoint": "playwright",
            "status": "tested",
            "trust_level": 1,
            "metadata": {"builtin": True, "implemented": True},
        },
        {
            "name": "model_eval_runner",
            "kind": "model",
            "description": "Reserved slot for phase-2 local model evaluation",
            "entrypoint": "python",
            "status": "draft",
            "trust_level": 0,
            "metadata": {"builtin": True, "implemented": False},
        },
    ]
    for tool in defaults:
        if tool["name"] not in existing:
            register_tool(settings, **tool)


def register_tool(
    settings: Settings,
    *,
    name: str,
    kind: str,
    description: str,
    entrypoint: str | None = None,
    status: str = "draft",
    trust_level: int = 0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tool_id = str(uuid.uuid4())
    now = utc_now()
    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            INSERT INTO tools (id, name, kind, description, entrypoint, status, trust_level, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tool_id, name, kind, description, entrypoint, status, trust_level, json.dumps(metadata or {}), now, now),
        )
        conn.commit()
        return get_tool(settings, name=name)  # type: ignore[return-value]
    finally:
        conn.close()


def list_tools(settings: Settings) -> list[dict[str, Any]]:
    conn = connect(settings.db_path)
    try:
        rows = conn.execute("SELECT * FROM tools ORDER BY created_at ASC").fetchall()
        return [t for row in rows if (t := _to_dict(row)) is not None]
    finally:
        conn.close()


def get_tool(settings: Settings, *, name: str) -> dict[str, Any] | None:
    conn = connect(settings.db_path)
    try:
        row = conn.execute("SELECT * FROM tools WHERE name = ?", (name,)).fetchone()
        return _to_dict(row)
    finally:
        conn.close()


def create_task(
    settings: Settings,
    *,
    tool_name: str,
    payload: dict[str, Any],
    auto_run: bool,
) -> dict[str, Any]:
    task_id = str(uuid.uuid4())
    now = utc_now()
    conn = connect(settings.db_path)
    try:
        status = "queued" if auto_run else "draft"
        queued_at = now if auto_run else None
        conn.execute(
            """
            INSERT INTO tasks (id, tool_name, payload_json, status, approved, queued_at, attempts, queue_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, tool_name, json.dumps(payload), status, 0, queued_at, 0, "default", now, now),
        )
        conn.commit()
        task = get_task(settings, task_id=task_id)
        return task or {}
    finally:
        conn.close()


def update_task(settings: Settings, *, task_id: str, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return get_task(settings, task_id=task_id)
    allowed = {
        "status",
        "approved",
        "approval_note",
        "reason",
        "stdout",
        "stderr",
        "exit_code",
        "timed_out",
        "result_json",
        "queued_at",
        "started_at",
        "finished_at",
        "attempts",
        "queue_name",
        "updated_at",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return get_task(settings, task_id=task_id)
    updates["updated_at"] = utc_now()
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    values = []
    for key, value in updates.items():
        if key == "result_json" and isinstance(value, (dict, list)):
            value = json.dumps(value)
        values.append(value)
    values.append(task_id)
    conn = connect(settings.db_path)
    try:
        conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return get_task(settings, task_id=task_id)
    finally:
        conn.close()


def get_task(settings: Settings, *, task_id: str) -> dict[str, Any] | None:
    conn = connect(settings.db_path)
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _to_dict(row)
    finally:
        conn.close()


def list_tasks(settings: Settings) -> list[dict[str, Any]]:
    conn = connect(settings.db_path)
    try:
        rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        return [t for row in rows if (t := _to_dict(row)) is not None]
    finally:
        conn.close()


def approve_task(settings: Settings, *, task_id: str, note: str | None = None) -> dict[str, Any] | None:
    return update_task(settings, task_id=task_id, approved=1, approval_note=note, status="queued", queued_at=utc_now())
