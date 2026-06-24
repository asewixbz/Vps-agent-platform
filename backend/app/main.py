from __future__ import annotations

from fastapi import FastAPI

from .control_plane_api import router as control_plane_router
from .memory import init_memory_schema
from .memory_links import init_memory_links_schema
from .model_api import router as model_router
from .persistence_api import router as persistence_router
from .persistence_migrations import ensure_persistence_schema
from .provenance_api import router as provenance_router
from .runtime_api import router as runtime_router
from .security_api import router as security_router
from .settings import get_settings
from .store import init_db, seed_builtin_tools
from .workflow_schedules import ensure_workflow_schedule_registry, router as workflow_schedules_router
from .workflow_template_registry import ensure_workflow_template_registry
from .workflow_templates_api import router as workflow_templates_router

settings = get_settings()
app = FastAPI(title=settings.app_name)


@app.on_event("startup")
def startup() -> None:
    init_db(settings)
    ensure_persistence_schema(settings)
    init_memory_schema(settings)
    init_memory_links_schema(settings)
    ensure_workflow_template_registry(settings)
    ensure_workflow_schedule_registry(settings)
    seed_builtin_tools(settings)


app.include_router(control_plane_router)
app.include_router(model_router)
app.include_router(runtime_router)
app.include_router(provenance_router)
app.include_router(persistence_router)
app.include_router(security_router)
app.include_router(workflow_templates_router)
app.include_router(workflow_schedules_router)
