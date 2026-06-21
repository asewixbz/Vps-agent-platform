from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from .agent_runtime import run_agent_runtime, runtime_execution_to_dict
from .settings import Settings, get_settings
from .store import connect, utc_now
from .workflow_template_registry import list_custom_workflow_templates
from .workflow_templates import (
    build_workflow_template_context,
    default_workflow_templates,
    normalize_workflow_template,
    resolve_workflow_template,
    workflow_template_to_dict,
)

router = APIRouter()
settings = get_settings()

_CADENCE_PATTERN = re.compile(r"^every\s+(?P<count>\d+)\s+(?P<unit>minute|minutes|hour|hours|day|days|week|weeks)$", re.IGNORECASE)


def ensure_workflow_schedule_registry(settings: Settings) -> None:
    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_schedules (
                id TEXT PRIMARY KEY,
                source_runtime_run_id TEXT UNIQUE NOT NULL,
                source_template_name TEXT NOT NULL,
                source_goal TEXT NOT NULL DEFAULT '',
                cadence TEXT NOT NULL,
                timezone TEXT NOT NULL DEFAULT 'UTC',
                target_workflow_name TEXT NOT NULL,
                target_goal TEXT NOT NULL,
                target_inputs_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'active',
                next_run_at TEXT,
                last_triggered_at TEXT,
                last_runtime_run_id TEXT,
                last_run_status TEXT,
                last_run_summary TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
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


def _coerce_datetime(value: Any | None) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return datetime.now(timezone.utc)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_cadence_delta(cadence: str) -> timedelta | None:
    normalized = cadence.strip().lower()
    if not normalized or normalized == "manual":
        return None
    if normalized in {"once", "one-shot", "one shot", "single", "single-run", "single run"}:
        return timedelta(0)
    if normalized in {"hourly", "every hour"}:
        return timedelta(hours=1)
    if normalized in {"daily", "every day"}:
        return timedelta(days=1)
    if normalized in {"weekly", "every week"}:
        return timedelta(days=7)

    match = _CADENCE_PATTERN.match(normalized)
    if match is None:
        return None

    count = int(match.group("count"))
    unit = match.group("unit")
    if unit.startswith("minute"):
        return timedelta(minutes=count)
    if unit.startswith("hour"):
        return timedelta(hours=count)
    if unit.startswith("day"):
        return timedelta(days=count)
    if unit.startswith("week"):
        return timedelta(days=7 * count)
    return None


def _next_run_at_for_cadence(cadence: str, base_time: datetime | None = None) -> str | None:
    normalized = cadence.strip().lower()
    if not normalized or normalized == "manual":
        return None

    base = base_time or datetime.now(timezone.utc)
    delta = _parse_cadence_delta(cadence)
    if delta is None:
        return None
    if delta == timedelta(0):
        return _format_datetime(base)
    return _format_datetime(base + delta)


def _registered_workflow_templates(settings: Settings) -> dict[str, dict[str, Any]]:
    templates = {name: workflow_template_to_dict(template) for name, template in default_workflow_templates().items()}
    for template in list_custom_workflow_templates(settings):
        normalized = normalize_workflow_template(template)
        if normalized is not None:
            templates[normalized.name] = workflow_template_to_dict(normalized)
    return templates


def _resolve_registered_workflow_template(settings: Settings, template_name: str):
    return resolve_workflow_template(
        {
            "workflow_template_name": template_name,
            "workflow_templates": _registered_workflow_templates(settings),
        }
    )


def _row_to_schedule(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None

    data = dict(row)
    data["target_inputs"] = _load_json(data.pop("target_inputs_json"), {})
    return data


def get_workflow_schedule(settings: Settings, *, schedule_id: str) -> dict[str, Any] | None:
    ensure_workflow_schedule_registry(settings)
    conn = connect(settings.db_path)
    try:
        row = conn.execute("SELECT * FROM workflow_schedules WHERE id = ?", (schedule_id,)).fetchone()
        return _row_to_schedule(row)
    finally:
        conn.close()


def get_workflow_schedule_by_source_runtime_run_id(settings: Settings, *, source_runtime_run_id: str) -> dict[str, Any] | None:
    ensure_workflow_schedule_registry(settings)
    conn = connect(settings.db_path)
    try:
        row = conn.execute("SELECT * FROM workflow_schedules WHERE source_runtime_run_id = ?", (source_runtime_run_id,)).fetchone()
        return _row_to_schedule(row)
    finally:
        conn.close()


def list_workflow_schedules(settings: Settings) -> list[dict[str, Any]]:
    ensure_workflow_schedule_registry(settings)
    conn = connect(settings.db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM workflow_schedules ORDER BY CASE WHEN next_run_at IS NULL THEN 1 ELSE 0 END, next_run_at ASC, created_at DESC"
        ).fetchall()
        return [schedule for row in rows if (schedule := _row_to_schedule(row)) is not None]
    finally:
        conn.close()


def register_workflow_schedule(
    settings: Settings,
    *,
    source_runtime_run_id: str,
    source_template_name: str,
    source_goal: str | None,
    workflow_inputs: dict[str, Any],
) -> dict[str, Any]:
    ensure_workflow_schedule_registry(settings)
    normalized_inputs = dict(workflow_inputs or {})
    cadence = str(normalized_inputs.get("cadence") or normalized_inputs.get("schedule_cadence") or "manual").strip() or "manual"
    timezone_name = str(normalized_inputs.get("timezone") or normalized_inputs.get("schedule_timezone") or "UTC").strip() or "UTC"
    target_workflow_name = str(normalized_inputs.get("target_workflow") or normalized_inputs.get("target_workflow_name") or "").strip()
    if not target_workflow_name:
        raise ValueError("target_workflow is required to register a recurring schedule")

    template = _resolve_registered_workflow_template(settings, target_workflow_name)
    target_goal = str(normalized_inputs.get("target_goal") or normalized_inputs.get("goal") or source_goal or "").strip()
    if not target_goal:
        target_goal = template.summary if template is not None else target_workflow_name

    target_inputs = normalized_inputs.get("target_inputs")
    if not isinstance(target_inputs, dict):
        target_inputs = normalized_inputs.get("workflow_inputs") if isinstance(normalized_inputs.get("workflow_inputs"), dict) else {}
    if not isinstance(target_inputs, dict):
        target_inputs = {}

    now = datetime.now(timezone.utc)
    next_run_at = _next_run_at_for_cadence(cadence, now)
    status = "paused" if next_run_at is None else "active"
    existing = get_workflow_schedule_by_source_runtime_run_id(settings, source_runtime_run_id=source_runtime_run_id)
    schedule_id = str(existing.get("id") if isinstance(existing, dict) and existing.get("id") else uuid.uuid4())
    created_at = str(existing.get("created_at") if isinstance(existing, dict) and existing.get("created_at") else utc_now())
    updated_at = utc_now()

    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            INSERT INTO workflow_schedules (
                id,
                source_runtime_run_id,
                source_template_name,
                source_goal,
                cadence,
                timezone,
                target_workflow_name,
                target_goal,
                target_inputs_json,
                status,
                next_run_at,
                last_triggered_at,
                last_runtime_run_id,
                last_run_status,
                last_run_summary,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_runtime_run_id) DO UPDATE SET
                source_template_name = excluded.source_template_name,
                source_goal = excluded.source_goal,
                cadence = excluded.cadence,
                timezone = excluded.timezone,
                target_workflow_name = excluded.target_workflow_name,
                target_goal = excluded.target_goal,
                target_inputs_json = excluded.target_inputs_json,
                status = excluded.status,
                next_run_at = excluded.next_run_at,
                updated_at = excluded.updated_at
            """,
            (
                schedule_id,
                source_runtime_run_id,
                source_template_name,
                source_goal or "",
                cadence,
                timezone_name,
                target_workflow_name,
                target_goal,
                json.dumps(target_inputs, ensure_ascii=False, sort_keys=True),
                status,
                next_run_at,
                None,
                None,
                None,
                None,
                created_at,
                updated_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    saved = get_workflow_schedule(settings, schedule_id=schedule_id)
    if saved is None:
        raise RuntimeError("workflow schedule could not be saved")
    return saved


def _claim_workflow_schedule(settings: Settings, *, schedule_id: str, claimed_at: str) -> bool:
    conn = connect(settings.db_path)
    try:
        cursor = conn.execute(
            "UPDATE workflow_schedules SET status = 'running', updated_at = ? WHERE id = ? AND status = 'active'",
            (claimed_at, schedule_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def _finalize_workflow_schedule(
    settings: Settings,
    *,
    schedule_id: str,
    status: str,
    next_run_at: str | None,
    last_triggered_at: str,
    runtime_run_id: str,
    runtime_status: str,
    runtime_summary: str | None,
) -> None:
    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            UPDATE workflow_schedules
            SET status = ?,
                next_run_at = ?,
                last_triggered_at = ?,
                last_runtime_run_id = ?,
                last_run_status = ?,
                last_run_summary = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (status, next_run_at, last_triggered_at, runtime_run_id, runtime_status, runtime_summary, utc_now(), schedule_id),
        )
        conn.commit()
    finally:
        conn.close()


def dispatch_due_workflow_schedules(
    settings: Settings,
    *,
    limit: int = 10,
    now: datetime | str | None = None,
) -> list[dict[str, Any]]:
    ensure_workflow_schedule_registry(settings)
    current = _coerce_datetime(now)
    now_iso = _format_datetime(current)

    conn = connect(settings.db_path)
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM workflow_schedules
            WHERE status = 'active'
              AND next_run_at IS NOT NULL
              AND next_run_at <= ?
            ORDER BY next_run_at ASC, created_at ASC
            LIMIT ?
            """,
            (now_iso, limit),
        ).fetchall()
    finally:
        conn.close()

    results: list[dict[str, Any]] = []
    for row in rows:
        schedule = _row_to_schedule(row)
        if schedule is None:
            continue

        schedule_id = str(schedule.get("id") or "")
        if not schedule_id:
            continue

        if not _claim_workflow_schedule(settings, schedule_id=schedule_id, claimed_at=now_iso):
            continue

        template_name = str(schedule.get("target_workflow_name") or "").strip()
        template = _resolve_registered_workflow_template(settings, template_name) if template_name else None
        if template is None:
            _finalize_workflow_schedule(
                settings,
                schedule_id=schedule_id,
                status="error",
                next_run_at=None,
                last_triggered_at=now_iso,
                runtime_run_id=str(schedule.get("last_runtime_run_id") or ""),
                runtime_status="missing_template",
                runtime_summary="workflow template not found",
            )
            results.append(
                {
                    "schedule": schedule,
                    "error": f'workflow template "{template_name}" not found',
                }
            )
            continue

        target_inputs = schedule.get("target_inputs") if isinstance(schedule.get("target_inputs"), dict) else {}
        workflow_context = build_workflow_template_context(
            template,
            workflow_inputs=target_inputs,
            context={
                "workflow_template_name": template.name,
                "scheduled_from_schedule_id": schedule_id,
                "scheduled_from_runtime_run_id": schedule.get("source_runtime_run_id"),
            },
        )
        execution = run_agent_runtime(
            settings,
            goal=str(schedule.get("target_goal") or template.summary),
            context=workflow_context,
        )

        cadence = str(schedule.get("cadence") or "manual")
        next_run_at = _next_run_at_for_cadence(cadence, _coerce_datetime(schedule.get("next_run_at") or current))
        final_status = "active"
        if cadence.strip().lower() in {"once", "one-shot", "one shot", "single", "single-run", "single run"}:
            final_status = "completed"
            next_run_at = None
        elif next_run_at is None:
            final_status = "paused"

        _finalize_workflow_schedule(
            settings,
            schedule_id=schedule_id,
            status=final_status,
            next_run_at=next_run_at,
            last_triggered_at=now_iso,
            runtime_run_id=execution.runtime_run_id,
            runtime_status=execution.status,
            runtime_summary=execution.summary,
        )
        results.append(
            {
                "schedule": get_workflow_schedule(settings, schedule_id=schedule_id),
                "workflow_template": workflow_template_to_dict(template),
                "workflow_inputs": workflow_context.get("workflow_inputs", {}),
                "execution": runtime_execution_to_dict(execution),
            }
        )

    return results


@router.get("/workflow-schedules")
def list_workflow_schedules_route() -> list[dict[str, object]]:
    return list_workflow_schedules(settings)


@router.post("/workflow-schedules/dispatch-due")
def dispatch_due_workflow_schedules_route(limit: int = 10) -> dict[str, object]:
    dispatched = dispatch_due_workflow_schedules(settings, limit=limit)
    return {"count": len(dispatched), "dispatched": dispatched}


@router.get("/workflow-schedules/{schedule_id}")
def get_workflow_schedule_route(schedule_id: str) -> dict[str, object]:
    schedule = get_workflow_schedule(settings, schedule_id=schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="workflow schedule not found")
    return schedule
