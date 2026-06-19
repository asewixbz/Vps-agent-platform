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

            CREATE TABLE IF NOT EXISTS runtime_runs (
                id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT,
                plan_json TEXT NOT NULL DEFAULT '{}',
                context_json TEXT NOT NULL DEFAULT '{}',
                steps_json TEXT NOT NULL DEFAULT '[]',
                checkpoint_json TEXT NOT NULL DEFAULT '{}',
                resume_hint TEXT,
                blocked_reason TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                started_at TEXT,
                finished_at TEXT,
                last_run_at TEXT,
                last_resume_from_step_index INTEGER,
                last_max_steps INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runtime_run_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                runtime_run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                step_index INTEGER,
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
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
        _ensure_columns(
            conn,
            "runtime_runs",
            [
                "summary TEXT",
                "plan_json TEXT NOT NULL DEFAULT '{}'",
                "context_json TEXT NOT NULL DEFAULT '{}'",
                "steps_json TEXT NOT NULL DEFAULT '[]'",
                "checkpoint_json TEXT NOT NULL DEFAULT '{}'",
                "resume_hint TEXT",
                "blocked_reason TEXT",
                "attempts INTEGER NOT NULL DEFAULT 0",
                "started_at TEXT",
                "finished_at TEXT",
                "last_run_at TEXT",
                "last_resume_from_step_index INTEGER",
                "last_max_steps INTEGER",
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _load_json(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return default
        return parsed if isinstance(parsed, (dict, list)) else default
    return default


def _to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    if "metadata_json" in data:
        data["metadata"] = _load_json(data.pop("metadata_json"), {})
    if "payload_json" in data:
        data["payload"] = _load_json(data.pop("payload_json"), {})
    if "result_json" in data:
        raw = data.pop("result_json")
        data["result"] = _load_json(raw, None)
    if "plan_json" in data:
        data["plan"] = _load_json(data.pop("plan_json"), {})
    if "context_json" in data:
        data["context"] = _load_json(data.pop("context_json"), {})
    if "steps_json" in data:
        data["steps"] = _load_json(data.pop("steps_json"), [])
    if "checkpoint_json" in data:
        data["checkpoint"] = _load_json(data.pop("checkpoint_json"), {})
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


def create_runtime_run(
    settings: Settings,
    *,
    goal: str,
    plan: dict[str, Any],
    context: dict[str, Any],
    runtime_run_id: str | None = None,
    status: str = "running",
    summary: str | None = None,
    steps: list[dict[str, Any]] | None = None,
    checkpoint: dict[str, Any] | None = None,
    blocked_reason: str | None = None,
    resume_hint: str | None = None,
    attempts: int = 1,
    started_at: str | None = None,
    finished_at: str | None = None,
    last_run_at: str | None = None,
    last_resume_from_step_index: int | None = None,
    last_max_steps: int | None = None,
) -> dict[str, Any]:
    run_id = runtime_run_id or str(uuid.uuid4())
    existing = get_runtime_run(settings, runtime_run_id=run_id)
    if existing is not None:
        return existing

    now = utc_now()
    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            INSERT INTO runtime_runs (
                id, goal, status, summary, plan_json, context_json, steps_json, checkpoint_json,
                resume_hint, blocked_reason, attempts, started_at, finished_at, last_run_at,
                last_resume_from_step_index, last_max_steps, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                goal,
                status,
                summary,
                json.dumps(plan),
                json.dumps(context),
                json.dumps(steps or []),
                json.dumps(checkpoint or {}),
                resume_hint,
                blocked_reason,
                attempts,
                started_at or now,
                finished_at,
                last_run_at or now,
                last_resume_from_step_index,
                last_max_steps,
                now,
                now,
            ),
        )
        conn.commit()
        return get_runtime_run(settings, runtime_run_id=run_id) or {}
    finally:
        conn.close()


def update_runtime_run(settings: Settings, *, runtime_run_id: str, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return get_runtime_run(settings, runtime_run_id=runtime_run_id)
    allowed = {
        "goal",
        "status",
        "summary",
        "plan_json",
        "context_json",
        "steps_json",
        "checkpoint_json",
        "resume_hint",
        "blocked_reason",
        "attempts",
        "started_at",
        "finished_at",
        "last_run_at",
        "last_resume_from_step_index",
        "last_max_steps",
        "updated_at",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return get_runtime_run(settings, runtime_run_id=runtime_run_id)
    updates["updated_at"] = utc_now()
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    values = []
    for key, value in updates.items():
        if key in {"plan_json", "context_json", "steps_json", "checkpoint_json"} and isinstance(value, (dict, list)):
            value = json.dumps(value)
        values.append(value)
    values.append(runtime_run_id)
    conn = connect(settings.db_path)
    try:
        conn.execute(f"UPDATE runtime_runs SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return get_runtime_run(settings, runtime_run_id=runtime_run_id)
    finally:
        conn.close()


def get_runtime_run(settings: Settings, *, runtime_run_id: str) -> dict[str, Any] | None:
    conn = connect(settings.db_path)
    try:
        row = conn.execute(
            """
            SELECT runtime_runs.*, (
                SELECT COUNT(1)
                FROM runtime_run_events
                WHERE runtime_run_events.runtime_run_id = runtime_runs.id
            ) AS event_count
            FROM runtime_runs
            WHERE runtime_runs.id = ?
            """,
            (runtime_run_id,),
        ).fetchone()
        return _to_dict(row)
    finally:
        conn.close()


def list_runtime_runs(settings: Settings, *, limit: int | None = 100) -> list[dict[str, Any]]:
    conn = connect(settings.db_path)
    try:
        query = """
            SELECT runtime_runs.*, (
                SELECT COUNT(1)
                FROM runtime_run_events
                WHERE runtime_run_events.runtime_run_id = runtime_runs.id
            ) AS event_count
            FROM runtime_runs
            ORDER BY updated_at DESC
        """
        params: tuple[Any, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        rows = conn.execute(query, params).fetchall()
        return [r for row in rows if (r := _to_dict(row)) is not None]
    finally:
        conn.close()


def create_runtime_run_event(
    settings: Settings,
    *,
    runtime_run_id: str,
    event_type: str,
    message: str,
    step_index: int | None = None,
    payload: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    now = created_at or utc_now()
    conn = connect(settings.db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO runtime_run_events (runtime_run_id, event_type, step_index, message, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (runtime_run_id, event_type, step_index, message, json.dumps(payload or {}), now),
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "runtime_run_id": runtime_run_id,
            "event_type": event_type,
            "step_index": step_index,
            "message": message,
            "payload": payload or {},
            "created_at": now,
        }
    finally:
        conn.close()


def list_runtime_run_events(
    settings: Settings,
    *,
    runtime_run_id: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    conn = connect(settings.db_path)
    try:
        query = "SELECT * FROM runtime_run_events WHERE runtime_run_id = ? ORDER BY id ASC"
        params: list[Any] = [runtime_run_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(query, tuple(params)).fetchall()
        return [e for row in rows if (e := _to_dict(row)) is not None]
    finally:
        conn.close()
