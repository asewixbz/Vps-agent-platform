from __future__ import annotations

from fastapi import APIRouter

from .persistence_layers import get_persistence_boundary_map
from .persistence_migrations import get_persistence_schema_snapshot
from .settings import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/persistence/layers")
def persistence_layers() -> dict[str, object]:
    return get_persistence_boundary_map()


@router.get("/persistence/schema")
def persistence_schema() -> dict[str, object]:
    return get_persistence_schema_snapshot(settings)
