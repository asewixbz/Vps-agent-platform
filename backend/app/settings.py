from functools import lru_cache
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
    require_approval_for_draft: bool = True
    browser_runner_enabled: bool = False
    model_runner_enabled: bool = False

    @property
    def allowed_shell_command_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_shell_commands.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
