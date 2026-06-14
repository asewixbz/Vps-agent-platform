from __future__ import annotations

from .runner import run_browser_task


if __name__ == "__main__":
    raise SystemExit("browser worker is not a separate service in phase 2; browser execution is handled by the main worker")
