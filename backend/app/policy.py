from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any, Sequence

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

SHELL_CONTROL_SNIPPETS = (
    "&&",
    "||",
    ";",
    "|",
    "`",
    "$(",
    ">",
    "<",
)


@dataclass
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    reason: str


class ShellPolicyError(ValueError):
    pass


def parse_shell_command(command: str, allowed_commands: Sequence[str]) -> list[str]:
    normalized = (command or "").strip()
    if not normalized:
        raise ShellPolicyError("shell payload is missing the command field")

    lowered = normalized.lower()
    for snippet in DANGEROUS_SNIPPETS:
        if snippet in lowered:
            raise ShellPolicyError(f"blocked shell snippet: {snippet}")

    for operator in SHELL_CONTROL_SNIPPETS:
        if operator in normalized:
            raise ShellPolicyError(f"blocked shell operator: {operator}")

    if "\n" in normalized or "\r" in normalized:
        raise ShellPolicyError("blocked shell operator: multiline input")

    try:
        argv = shlex.split(normalized)
    except ValueError as exc:
        raise ShellPolicyError("shell command could not be parsed safely") from exc

    if not argv:
        raise ShellPolicyError("shell payload is missing the command field")

    if argv[0] not in allowed_commands:
        raise ShellPolicyError(f'shell command "{argv[0]}" is not in the allowlist')

    return argv


def evaluate(tool: dict[str, Any], payload: dict[str, Any], settings: Settings, *, approved: bool = False) -> PolicyDecision:
    if not approved and tool["status"] != "trusted" and settings.require_approval_for_draft:
        return PolicyDecision(
            allowed=False,
            requires_approval=True,
            reason=f'tool "{tool["name"]}" is not trusted yet ({tool["status"]})',
        )

    kind = tool["kind"]
    if kind == "shell":
        command = payload.get("command") or ""
        try:
            parse_shell_command(command, settings.allowed_shell_command_list)
        except ShellPolicyError as exc:
            return PolicyDecision(False, False, str(exc))

    if kind == "browser":
        if not settings.browser_runner_enabled:
            return PolicyDecision(False, False, "browser runner is not enabled in phase 1")

    if kind == "model":
        if not settings.model_runner_enabled:
            return PolicyDecision(False, False, "model runner is not enabled in phase 1")

    return PolicyDecision(True, False, "policy passed")
