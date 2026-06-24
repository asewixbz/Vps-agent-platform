from __future__ import annotations

import contextlib
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .settings import Settings

try:  # pragma: no cover - resource is unavailable on some platforms
    import resource
except Exception:  # pragma: no cover - fallback for non-POSIX platforms
    resource = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubprocessSandbox:
    argv: list[str]
    cwd: str
    env: dict[str, str]
    preexec_fn: Callable[[], None] | None
    backend: str
    requested_mode: str
    selection_reason: str
    fallback_used: bool
    file_policy: str
    network_policy: str


_SANDBOX_RO_BIND_PATHS = (
    Path("/usr"),
    Path("/usr/local"),
    Path("/bin"),
    Path("/lib"),
    Path("/lib64"),
    Path("/etc/ld.so.cache"),
    Path("/etc/localtime"),
    Path("/etc/passwd"),
    Path("/etc/group"),
    Path("/etc/nsswitch.conf"),
)


def _sandbox_tmp_dir(workdir: Path) -> Path:
    tmp_dir = workdir / "tmp"
    tmp_dir.mkdir(mode=0o700, exist_ok=True)
    try:
        tmp_dir.chmod(0o700)
    except OSError:
        pass
    return tmp_dir


def _sandbox_env(cwd: str) -> dict[str, str]:
    return {
        "HOME": cwd,
        "PWD": cwd,
        "TMPDIR": str(Path(cwd) / "tmp"),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
    }


def _apply_rlimits(*, timeout_seconds: int, settings: Settings, workdir: Path) -> Callable[[], None]:
    cpu_limit_seconds = max(1, int(timeout_seconds) + 2)
    memory_limit_bytes = max(0, int(settings.task_sandbox_memory_mb)) * 1024 * 1024
    file_size_limit_bytes = max(0, int(settings.task_sandbox_max_file_size_mb)) * 1024 * 1024
    max_processes = max(1, int(settings.task_sandbox_max_processes))
    max_open_files = max(16, int(settings.task_sandbox_max_open_files))

    def _apply() -> None:
        os.chdir(workdir)
        os.setsid()
        os.umask(0o077)
        if resource is None:
            return

        with contextlib.suppress(Exception):
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        with contextlib.suppress(Exception):
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit_seconds, cpu_limit_seconds))
        if memory_limit_bytes > 0 and hasattr(resource, "RLIMIT_AS"):
            with contextlib.suppress(Exception):
                resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
        if file_size_limit_bytes > 0 and hasattr(resource, "RLIMIT_FSIZE"):
            with contextlib.suppress(Exception):
                resource.setrlimit(resource.RLIMIT_FSIZE, (file_size_limit_bytes, file_size_limit_bytes))
        if hasattr(resource, "RLIMIT_NPROC"):
            with contextlib.suppress(Exception):
                resource.setrlimit(resource.RLIMIT_NPROC, (max_processes, max_processes))
        if hasattr(resource, "RLIMIT_NOFILE"):
            with contextlib.suppress(Exception):
                resource.setrlimit(resource.RLIMIT_NOFILE, (max_open_files, max_open_files))

    return _apply


def _bubblewrap_available() -> bool:
    return shutil.which("bwrap") is not None


def _existing_ro_binds() -> list[Path]:
    return [path for path in _SANDBOX_RO_BIND_PATHS if path.exists()]


def _build_bubblewrap_argv(workdir: Path, argv: list[str], *, allow_network: bool) -> list[str]:
    tmp_dir = _sandbox_tmp_dir(workdir)
    bwrap_argv: list[str] = [
        "bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
    ]
    if not allow_network:
        bwrap_argv.append("--unshare-net")
    bwrap_argv.extend(
        [
            "--bind",
            str(workdir),
            "/work",
            "--bind",
            str(tmp_dir),
            "/work/tmp",
            "--chdir",
            "/work",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--clearenv",
            "--setenv",
            "HOME",
            "/work",
            "--setenv",
            "PWD",
            "/work",
            "--setenv",
            "TMPDIR",
            "/work/tmp",
            "--setenv",
            "PATH",
            "/usr/local/bin:/usr/bin:/bin",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--setenv",
            "LC_ALL",
            "C.UTF-8",
        ]
    )
    for bind_path in _existing_ro_binds():
        bwrap_argv.extend(["--ro-bind", str(bind_path), str(bind_path)])
    bwrap_argv.append("--")
    bwrap_argv.extend(argv)
    return bwrap_argv


def build_subprocess_sandbox(
    settings: Settings,
    *,
    workdir: Path,
    argv: list[str],
    timeout_seconds: int | None = None,
) -> SubprocessSandbox:
    timeout_budget = timeout_seconds or settings.default_timeout_seconds
    requested_mode = (settings.task_sandbox_mode or "auto").strip().lower() or "auto"
    allow_network = bool(settings.task_sandbox_allow_network)
    bubblewrap_available = _bubblewrap_available()

    backend = "rlimit"
    sandbox_cwd = str(workdir)
    file_policy = "cwd-and-rlimit"
    network_policy = "not-enforced"
    preexec_fn = _apply_rlimits(timeout_seconds=timeout_budget, settings=settings, workdir=workdir)
    sandbox_argv = list(argv)
    selection_reason = "rlimit mode selected"
    fallback_used = requested_mode not in {"rlimit"}

    if requested_mode in {"auto", "bubblewrap", "bwrap"}:
        if bubblewrap_available:
            try:
                sandbox_argv = _build_bubblewrap_argv(workdir, argv, allow_network=allow_network)
                backend = "bubblewrap"
                sandbox_cwd = "/work"
                file_policy = "workdir-bind-only"
                network_policy = "unshared" if not allow_network else "best-effort"
                preexec_fn = None
                selection_reason = "bubblewrap selected"
                fallback_used = False
            except Exception as exc:
                logger.warning(
                    "sandbox mode %s requested bubblewrap but the privileged path could not be constructed; falling back to rlimit (%s)",
                    requested_mode,
                    exc,
                )
                selection_reason = f"bubblewrap fallback to rlimit after build failure: {exc}"
        else:
            logger.warning(
                "sandbox mode %s requested bubblewrap but bwrap is unavailable; falling back to rlimit",
                requested_mode,
            )
            selection_reason = "bubblewrap unavailable; falling back to rlimit"
    elif requested_mode == "rlimit":
        selection_reason = "rlimit mode selected explicitly"
        fallback_used = False
    else:
        logger.warning("unknown sandbox mode %s; falling back to rlimit", requested_mode)
        selection_reason = f"unknown sandbox mode '{requested_mode}'; falling back to rlimit"

    return SubprocessSandbox(
        argv=sandbox_argv,
        cwd=sandbox_cwd,
        env=_sandbox_env(sandbox_cwd),
        preexec_fn=preexec_fn,
        backend=backend,
        requested_mode=requested_mode,
        selection_reason=selection_reason,
        fallback_used=fallback_used,
        file_policy=file_policy,
        network_policy=network_policy,
    )
