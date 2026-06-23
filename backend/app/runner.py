from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .artifact_lifecycle import build_artifact_manifest, normalize_artifact_entry, normalize_artifact_manifest, write_artifact_manifest
from .model_runtime import chat_model
from .model_adapter import ModelAdapterError
from .policy import ShellPolicyError, parse_shell_command
from .sandbox import SubprocessSandbox, build_subprocess_sandbox
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
    try:
        task_dir.chmod(0o700)
    except OSError:
        pass
    tmp_dir = task_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        tmp_dir.chmod(0o700)
    except OSError:
        pass
    return task_dir


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _artifact_manifest_key(manifest_name: str) -> str:
    if Path(manifest_name).stem == "artifacts":
        return "artifact_manifest_path"
    return f"{Path(manifest_name).stem}_path"


def _artifact_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".txt", ".log"}:
        return "text"
    if suffix == ".py":
        return "script"
    if suffix == ".json":
        return "json"
    return "file"


def _discover_artifact_paths(workdir: Path) -> list[Path]:
    excluded_names = {"artifacts.json", "artifact_manifest.json", "schedule_manifest.json"}
    discovered: list[Path] = []
    for path in sorted(workdir.rglob("*")):
        if not path.is_file():
            continue
        try:
            relative_parts = path.relative_to(workdir).parts
        except ValueError:
            continue
        if any(part == "tmp" for part in relative_parts):
            continue
        if path.name in excluded_names:
            continue
        discovered.append(path)
    return discovered


def _artifact_entries_from_paths(paths: list[Path]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        artifact_ref = str(path)
        if artifact_ref in seen:
            continue
        seen.add(artifact_ref)
        entry = normalize_artifact_entry(
            {
                "artifact_type": _artifact_type_for_path(path),
                "artifact_ref": artifact_ref,
                "label": path.name,
            }
        )
        if entry is not None:
            entries.append(entry)
    return entries


def _persist_artifact_manifests(
    workdir: Path,
    *,
    task_id: str,
    source: str,
    manifest_names: tuple[str, ...],
) -> dict[str, Any]:
    discovered_paths = _discover_artifact_paths(workdir)
    if not discovered_paths:
        return {}

    manifest = build_artifact_manifest(
        scope_type="task",
        scope_id=task_id,
        artifacts=_artifact_entries_from_paths(discovered_paths),
        source=source,
    )
    materialized: dict[str, Any] = {}
    for manifest_name in manifest_names:
        manifest_path = workdir / manifest_name
        write_artifact_manifest(manifest_path, manifest)
        materialized[_artifact_manifest_key(manifest_name)] = str(manifest_path)
    return materialized


def _load_python_artifact_manifest(workdir: Path) -> dict[str, Any]:
    manifest_path = workdir / "artifacts.json"
    if not manifest_path.exists():
        return {}

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    normalized = normalize_artifact_manifest(raw, source="artifacts.json")
    return normalized if isinstance(normalized, dict) else {}


def _materialize_schedule_artifacts(workdir: Path, *, task_id: str) -> dict[str, Any]:
    schedule_json_path = workdir / "schedule.json"
    schedule_md_path = workdir / "schedule.md"
    if not schedule_json_path.exists() and not schedule_md_path.exists():
        return {}

    materialized: dict[str, Any] = {}
    if schedule_json_path.exists():
        materialized["schedule_json_path"] = str(schedule_json_path)
    if schedule_md_path.exists():
        materialized["schedule_md_path"] = str(schedule_md_path)

    materialized.update(
        _persist_artifact_manifests(
            workdir,
            task_id=task_id,
            source="schedule_runner",
            manifest_names=("artifacts.json", "schedule_manifest.json"),
        )
    )
    return materialized


def _materialize_workflow_artifacts(workdir: Path, *, task_id: str) -> dict[str, Any]:
    artifact_candidates = (
        ("report_path", workdir / "report.json"),
        ("report_md_path", workdir / "report.md"),
        ("ranking_path", workdir / "ranking.json"),
        ("ranking_md_path", workdir / "ranking.md"),
        ("scan_path", workdir / "scan.json"),
        ("scan_md_path", workdir / "scan.md"),
        ("compare_path", workdir / "compare.json"),
        ("compare_md_path", workdir / "compare.md"),
    )

    materialized: dict[str, Any] = {}
    for key, path in artifact_candidates:
        if path.exists():
            materialized[key] = str(path)

    if not materialized:
        return {}

    materialized.update(
        _persist_artifact_manifests(
            workdir,
            task_id=task_id,
            source="workflow_runner",
            manifest_names=("artifacts.json",),
        )
    )
    return materialized


def _run_subprocess(
    *,
    settings: Settings,
    workdir: Path,
    argv: list[str],
    timeout_seconds: int | None,
) -> tuple[subprocess.CompletedProcess[str], SubprocessSandbox]:
    sandbox = build_subprocess_sandbox(
        settings,
        workdir=workdir,
        argv=argv,
        timeout_seconds=timeout_seconds,
    )
    timeout = timeout_seconds or settings.default_timeout_seconds
    completed = subprocess.run(
        sandbox.argv,
        cwd=sandbox.cwd,
        env=sandbox.env,
        preexec_fn=sandbox.preexec_fn,
        capture_output=True,
        text=True,
        timeout=timeout,
        start_new_session=True,
    )
    return completed, sandbox


def _sandbox_artifacts(workdir: Path, sandbox: SubprocessSandbox, *, command_argv: list[str] | None = None) -> dict[str, Any]:
    artifacts: dict[str, Any] = {
        "workdir": str(workdir),
        "sandbox_backend": sandbox.backend,
        "sandbox_cwd": sandbox.cwd,
        "sandbox_file_policy": sandbox.file_policy,
        "sandbox_network_policy": sandbox.network_policy,
    }
    if command_argv is not None:
        artifacts["command_argv"] = command_argv
    return artifacts


def _prepare_python_argv(script_path: Path) -> list[str]:
    return [sys.executable, "-I", "-s", "-B", script_path.name]


def _prepare_shell_argv(command_argv: list[str]) -> list[str]:
    if command_argv and Path(command_argv[0]).name.startswith("python") and "-I" not in command_argv[1:]:
        return [command_argv[0], "-I", "-s", "-B", *command_argv[1:]]
    return command_argv


def run_python_script(settings: Settings, *, task_id: str, script: str, timeout_seconds: int | None = None) -> RunResult:
    workdir = _prepare_workdir(settings, task_id)
    script_path = workdir / "main.py"
    script_path.write_text(script, encoding="utf-8")
    started = time.monotonic()
    timeout = timeout_seconds or settings.default_timeout_seconds
    try:
        completed, sandbox = _run_subprocess(
            settings=settings,
            workdir=workdir,
            argv=_prepare_python_argv(script_path),
            timeout_seconds=timeout,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        artifacts = _sandbox_artifacts(workdir, sandbox, command_argv=[sys.executable, "-I", "-s", "-B", "main.py"])
        artifacts.update({"script_path": str(script_path)})
        artifacts.update(_materialize_schedule_artifacts(workdir, task_id=task_id))
        artifacts.update(_materialize_workflow_artifacts(workdir, task_id=task_id))
        artifacts.update(_load_python_artifact_manifest(workdir))
        return RunResult(
            ok=completed.returncode == 0,
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            timed_out=False,
            duration_ms=duration_ms,
            artifacts=artifacts,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        artifacts = {"script_path": str(script_path)}
        artifacts.update({"workdir": str(workdir)})
        artifacts.update(_materialize_schedule_artifacts(workdir, task_id=task_id))
        artifacts.update(_materialize_workflow_artifacts(workdir, task_id=task_id))
        artifacts.update(_load_python_artifact_manifest(workdir))
        return RunResult(
            ok=False,
            stdout=exc.stdout or "",
            stderr=exc.stderr or f"python task timed out after {timeout} seconds",
            exit_code=124,
            timed_out=True,
            duration_ms=duration_ms,
            artifacts=artifacts,
        )
    except Exception as exc:  # pragma: no cover - defensive safety net
        duration_ms = int((time.monotonic() - started) * 1000)
        return RunResult(
            ok=False,
            stdout="",
            stderr=f"sandbox setup failed: {exc}",
            exit_code=126,
            timed_out=False,
            duration_ms=duration_ms,
            artifacts={"workdir": str(workdir), "script_path": str(script_path)},
        )


def run_shell_command(settings: Settings, *, task_id: str, command: str, timeout_seconds: int | None = None) -> RunResult:
    workdir = _prepare_workdir(settings, task_id)
    started = time.monotonic()
    timeout = timeout_seconds or settings.default_timeout_seconds
    try:
        command_argv = parse_shell_command(command, settings.allowed_shell_command_list)
        command_argv = _prepare_shell_argv(command_argv)
        completed, sandbox = _run_subprocess(
            settings=settings,
            workdir=workdir,
            argv=command_argv,
            timeout_seconds=timeout,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        artifacts = _sandbox_artifacts(workdir, sandbox, command_argv=command_argv)
        artifacts.update(_persist_artifact_manifests(workdir, task_id=task_id, source="shell_runner", manifest_names=("artifacts.json",)))
        return RunResult(
            ok=completed.returncode == 0,
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            timed_out=False,
            duration_ms=duration_ms,
            artifacts=artifacts,
        )
    except ShellPolicyError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return RunResult(
            ok=False,
            stdout="",
            stderr=str(exc),
            exit_code=2,
            timed_out=False,
            duration_ms=duration_ms,
            artifacts={"workdir": str(workdir)},
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        artifacts = {"workdir": str(workdir)}
        artifacts.update(_persist_artifact_manifests(workdir, task_id=task_id, source="shell_runner", manifest_names=("artifacts.json",)))
        return RunResult(
            ok=False,
            stdout=exc.stdout or "",
            stderr=exc.stderr or f"shell task timed out after {timeout} seconds",
            exit_code=124,
            timed_out=True,
            duration_ms=duration_ms,
            artifacts=artifacts,
        )
    except Exception as exc:  # pragma: no cover - defensive safety net
        duration_ms = int((time.monotonic() - started) * 1000)
        return RunResult(
            ok=False,
            stdout="",
            stderr=f"sandbox setup failed: {exc}",
            exit_code=126,
            timed_out=False,
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
            artifacts = {
                "workdir": str(workdir),
                "html_path": str(html_path),
                "text_path": str(text_path),
                "title": title,
                "url": page.url,
            }
            artifacts.update(
                _persist_artifact_manifests(
                    workdir,
                    task_id=task_id,
                    source="browser_runner",
                    manifest_names=("artifacts.json",),
                )
            )
            return RunResult(
                ok=True,
                stdout=f"TITLE: {title}\nURL: {page.url}\nBODY:\n{summary}",
                stderr="",
                exit_code=0,
                timed_out=False,
                duration_ms=duration_ms,
                artifacts=artifacts,
            )
    except PlaywrightTimeoutError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        artifacts = {"workdir": str(workdir), "html_path": str(html_path), "text_path": str(text_path)}
        artifacts.update(
            _persist_artifact_manifests(
                workdir,
                task_id=task_id,
                source="browser_runner",
                manifest_names=("artifacts.json",),
            )
        )
        return RunResult(
            ok=False,
            stdout="",
            stderr=f"browser task timed out after {timeout} seconds: {exc}",
            exit_code=124,
            timed_out=True,
            duration_ms=duration_ms,
            artifacts=artifacts,
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
