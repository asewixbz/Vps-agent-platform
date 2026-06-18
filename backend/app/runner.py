from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .model_runtime import chat_model
from .model_adapter import ModelAdapterError
from .settings import Settings


@dataclass
class RunResult:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    duration_ms: int
    artifacts: dict[str, Any]


def _prepare_workdir(settings: Settings, task_id: str) -> Path:
    work_root = Path(settings.work_dir)
    work_root.mkdir(parents=True, exist_ok=True)
    task_dir = work_root / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def run_python_script(settings: Settings, *, task_id: str, script: str, timeout_seconds: int | None = None) -> RunResult:
    workdir = _prepare_workdir(settings, task_id)
    script_path = workdir / "main.py"
    script_path.write_text(script, encoding="utf-8")
    started = time.monotonic()
    timeout = timeout_seconds or settings.default_timeout_seconds
    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        return RunResult(
            ok=proc.returncode == 0,
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            timed_out=False,
            duration_ms=duration_ms,
            artifacts={"workdir": str(workdir), "script_path": str(script_path)},
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return RunResult(
            ok=False,
            stdout=exc.stdout or "",
            stderr=exc.stderr or f"python task timed out after {timeout} seconds",
            exit_code=124,
            timed_out=True,
            duration_ms=duration_ms,
            artifacts={"workdir": str(workdir), "script_path": str(script_path)},
        )


def run_shell_command(settings: Settings, *, task_id: str, command: str, timeout_seconds: int | None = None) -> RunResult:
    workdir = _prepare_workdir(settings, task_id)
    started = time.monotonic()
    timeout = timeout_seconds or settings.default_timeout_seconds
    try:
        proc = subprocess.run(
            ["bash", "-lc", command],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        return RunResult(
            ok=proc.returncode == 0,
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            timed_out=False,
            duration_ms=duration_ms,
            artifacts={"workdir": str(workdir)},
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return RunResult(
            ok=False,
            stdout=exc.stdout or "",
            stderr=exc.stderr or f"shell task timed out after {timeout} seconds",
            exit_code=124,
            timed_out=True,
            duration_ms=duration_ms,
            artifacts={"workdir": str(workdir)},
        )


def run_model_task(
    settings: Settings,
    *,
    task_id: str,
    payload: dict[str, Any],
    timeout_seconds: int | None = None,
) -> RunResult:
    _ = task_id
    _ = timeout_seconds
    started = time.monotonic()
    try:
        response = chat_model(settings, payload)
    except ModelAdapterError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return RunResult(
            ok=False,
            stdout="",
            stderr=str(exc),
            exit_code=1,
            timed_out=False,
            duration_ms=duration_ms,
            artifacts={},
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    response_dump = {
        "text": response.text,
        "structured_data": response.structured_data,
        "tool_calls": response.tool_calls,
        "finish_reason": response.finish_reason,
        "model": response.model,
        "provider": response.provider,
        "usage": asdict(response.usage) if response.usage else None,
        "raw": response.raw,
        "metadata": response.metadata,
    }

    stdout = response.text or ""
    if response.structured_data is not None:
        structured_text = json.dumps(response.structured_data, ensure_ascii=False, indent=2)
        stdout = structured_text if not stdout else f"{stdout}\n\nSTRUCTURED_DATA:\n{structured_text}"
    if not stdout and response.tool_calls:
        stdout = json.dumps(response.tool_calls, ensure_ascii=False, indent=2)
    if not stdout and response.raw is not None:
        stdout = json.dumps(response.raw, ensure_ascii=False, indent=2)

    status = str(response.metadata.get("status") or response.finish_reason or "completed")
    ok = status in {"completed", "success", "succeeded"}
    return RunResult(
        ok=ok,
        stdout=stdout,
        stderr="" if ok else f"model request finished with status {status}",
        exit_code=0 if ok else 1,
        timed_out=False,
        duration_ms=duration_ms,
        artifacts={"response": response_dump},
    )


def run_browser_task(
    settings: Settings,
    *,
    task_id: str,
    url: str,
    timeout_seconds: int | None = None,
    wait_until: str = "domcontentloaded",
) -> RunResult:
    workdir = _prepare_workdir(settings, task_id)
    started = time.monotonic()
    timeout = timeout_seconds or settings.default_timeout_seconds
    if not url:
        return RunResult(
            ok=False,
            stdout="",
            stderr="browser payload is missing the url field",
            exit_code=2,
            timed_out=False,
            duration_ms=0,
            artifacts={"workdir": str(workdir)},
        )

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - import guard
        return RunResult(
            ok=False,
            stdout="",
            stderr=f"playwright is not installed: {exc}",
            exit_code=1,
            timed_out=False,
            duration_ms=0,
            artifacts={"workdir": str(workdir)},
        )

    html_path = workdir / "page.html"
    text_path = workdir / "page.txt"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until=wait_until, timeout=timeout * 1000)
            title = page.title()
            html = page.content()
            body_text = page.locator("body").inner_text(timeout=2000) if page.locator("body").count() else ""
            html_path.write_text(html, encoding="utf-8")
            text_path.write_text(body_text, encoding="utf-8")
            browser.close()
            duration_ms = int((time.monotonic() - started) * 1000)
            summary = body_text[:5000]
            return RunResult(
                ok=True,
                stdout=f"TITLE: {title}\nURL: {page.url}\nBODY:\n{summary}",
                stderr="",
                exit_code=0,
                timed_out=False,
                duration_ms=duration_ms,
                artifacts={
                    "workdir": str(workdir),
                    "html_path": str(html_path),
                    "text_path": str(text_path),
                    "title": title,
                    "url": page.url,
                },
            )
    except PlaywrightTimeoutError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return RunResult(
            ok=False,
            stdout="",
            stderr=f"browser task timed out after {timeout} seconds: {exc}",
            exit_code=124,
            timed_out=True,
            duration_ms=duration_ms,
            artifacts={"workdir": str(workdir), "html_path": str(html_path), "text_path": str(text_path)},
        )
    except Exception as exc:  # pragma: no cover - defensive safety net
        duration_ms = int((time.monotonic() - started) * 1000)
        return RunResult(
            ok=False,
            stdout="",
            stderr=str(exc),
            exit_code=1,
            timed_out=False,
            duration_ms=duration_ms,
            artifacts={"workdir": str(workdir), "html_path": str(html_path), "text_path": str(text_path)},
        )


def run_unimplemented(kind: str) -> RunResult:
    return RunResult(
        ok=False,
        stdout="",
        stderr=f"runner for kind '{kind}' is not implemented in phase 1",
        exit_code=1,
        timed_out=False,
        duration_ms=0,
        artifacts={},
    )
