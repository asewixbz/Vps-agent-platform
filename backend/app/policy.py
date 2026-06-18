from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any

from .settings import Settings

DANGEROUS_SNIPPETS = (
    "rm -rf /",
    "rm -rf ~",
    "sudo ",
    "shutdown",
    "reboot",
    "mkfs",
    "curl | sh",
    "wget | sh",
    "chmod 777 /",
    "dd if=",
    "nc ",
    "netcat",
    "ssh ",
    "scp ",
)


@dataclass
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    reason: str


def evaluate(tool: dict[str, Any], payload: dict[str, Any], settings: Settings, *, approved: bool = False) -> PolicyDecision:
    if not approved and tool["status"] != "trusted" and settings.require_approval_for_draft:
        return PolicyDecision(
            allowed=False,
            requires_approval=True,
            reason=f'tool "{tool["name"]}" is not trusted yet ({tool["status"]})',
        )

    kind = tool["kind"]
    if kind == "shell":
        command = (payload.get("command") or "").strip()
        if not command:
            return PolicyDecision(False, False, "shell payload is missing the command field")
        lowered = command.lower()
        for snippet in DANGEROUS_SNIPPETS:
            if snippet in lowered:
                return PolicyDecision(False, False, f"blocked shell snippet: {snippet}")
        first_token = shlex.split(command)[0]
        if first_token not in settings.allowed_shell_command_list:
            return PolicyDecision(
                False,
                False,
                f'shell command "{first_token}" is not in the allowlist',
            )

    if kind == "browser":
        if not settings.browser_runner_enabled:
            return PolicyDecision(False, False, "browser runner is not enabled in phase 1")

    if kind == "model":
        adapter_configured = settings.model_adapter_name not in {"", "unconfigured", None}
        if not settings.model_runner_enabled and not adapter_configured:
            return PolicyDecision(False, False, "model adapter is not configured")

    return PolicyDecision(True, False, "policy passed")
