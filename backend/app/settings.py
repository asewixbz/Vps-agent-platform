from functools import lru_cache
import json
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "vps-agent-control-plane"
    db_path: str = "/data/app.db"
    work_dir: str = "/data/work"
    artifact_dir: str = "/data/artifacts"
    redis_url: str = "redis://redis:6379/0"
    task_queue_name: str = "agent_tasks"
    worker_poll_seconds: int = 5
    worker_once: bool = False
    allowed_shell_commands: str = "echo,ls,pwd,cat,grep,python"
    default_timeout_seconds: int = 60
    task_timeout_hard_limit_seconds: int = 300
    runtime_max_steps_hard_limit: int = 10
    tool_policy_overrides_json: str = "{}"
    require_approval_for_draft: bool = True
    browser_runner_enabled: bool = False
    model_runner_enabled: bool = False
    model_adapter_name: str = "unconfigured"
    model_default_alias: str = "general"
    model_request_timeout_seconds: int = 120
    model_adapter_options_json: str = "{}"
    task_sandbox_mode: str = "auto"
    task_sandbox_allow_network: bool = False
    task_sandbox_memory_mb: int = 256
    task_sandbox_max_processes: int = 8
    task_sandbox_max_open_files: int = 64
    task_sandbox_max_file_size_mb: int = 16

    @property
    def allowed_shell_command_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_shell_commands.split(",") if item.strip()]

    @property
    def model_adapter_options(self) -> dict[str, Any]:
        try:
            parsed = json.loads(self.model_adapter_options_json or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
