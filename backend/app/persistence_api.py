from __future__ import annotations

from fastapi import APIRouter

from .persistence_layers import get_persistence_boundary_map

router = APIRouter()


@router.get("/persistence/layers")
def persistence_layers() -> dict[str, object]:
    return get_persistence_boundary_map()
