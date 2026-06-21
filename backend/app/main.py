from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .agent_runtime import run_agent_runtime, runtime_execution_to_dict
from .dossiers import (
    get_contact_dossier,
    get_project_dossier,
    list_contact_dossiers,
    list_dossiers,
    list_project_dossiers,
    upsert_contact_dossier,
    upsert_project_dossier,
)
from .job_queue import enqueue_task, queue_size
from .memory import (
    add_memory_record_artifact,
    get_memory_record,
    init_memory_schema,
    list_memory_record_artifacts,
    list_memory_records,
    touch_memory_record,
    upsert_memory_record,
)
from .memory_links import (
    add_memory_link,
    init_memory_links_schema,
    list_memory_links,
    list_memory_links_for_entity,
)
from .model_adapter import ModelAdapterError
from .model_runtime import chat_model, model_health as runtime_model_health
from .planner import build_execution_plan
from .provenance_api import router as provenance_router
from .runtime_events import group_runtime_events, runtime_events_for_step
from .settings import get_settings
from .store import (
    approve_task,
    create_task,
    get_runtime_run,
    get_task,
    get_tool,
    init_db,
    list_runtime_run_events,
    list_runtime_runs,
    list_tasks,
    list_tools,
    register_tool,
    seed_builtin_tools,
)
from .workflow_schedules import router as workflow_schedules_router
from .workflow_templates_api import router as workflow_templates_router

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(provenance_router)
app.include_router(workflow_templates_router)
app.include_router(workflow_schedules_router)
