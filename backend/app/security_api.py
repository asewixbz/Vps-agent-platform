from __future__ import annotations

from fastapi import APIRouter

from .security_controls import get_operational_controls
from .settings import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/security/controls")
def security_controls() -> dict[str, object]:
    return get_operational_controls(settings)
