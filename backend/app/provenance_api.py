from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .memory_graph import build_memory_record_provenance, build_runtime_run_provenance
from .settings import get_settings
from .store import get_runtime_run

router = APIRouter()
settings = get_settings()


@router.get("/memory/records/{memory_record_id}/provenance")
def memory_record_provenance(memory_record_id: str, limit: int = 100) -> dict[str, object]:
    provenance = build_memory_record_provenance(settings, memory_record_id=memory_record_id, limit=limit)
    if provenance is None:
        raise HTTPException(status_code=404, detail="memory record not found")
    return provenance


@router.get("/agent/runs/{runtime_run_id}/provenance")
def agent_run_provenance(runtime_run_id: str, limit: int = 100) -> dict[str, object]:
    run = get_runtime_run(settings, runtime_run_id=runtime_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="runtime run not found")
    provenance = build_runtime_run_provenance(settings, runtime_run_id=runtime_run_id, limit=limit)
    return {
        "runtime_run": run,
        **provenance,
    }
