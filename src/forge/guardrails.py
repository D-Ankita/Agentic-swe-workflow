from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Sequence


class PolicyViolation(RuntimeError):
    pass


class ApprovalRequired(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CommandPolicy:
    prohibited: tuple[str, ...] = (
        r"(^|\s)rm\s+-rf\s+[/~]",
        r"(^|\s)(sudo|su)(\s|$)",
        r"git\s+push\s+.*(--force|-f)(\s|$)",
        r"(curl|wget).*[|]\s*(sh|bash)",
        r"mkfs\.",
    )
    approval_required: tuple[str, ...] = (
        r"\bgit\s+push\b",
        r"\b(kubectl|helm)\s+(apply|delete|upgrade)\b",
        r"\b(terraform|tofu)\s+(apply|destroy)\b",
        r"\bdeploy\b",
    )

    def check(self, command: str | Sequence[str], approved: bool = False) -> None:
        command = command if isinstance(command, str) else shlex.join(command)
        if any(re.search(pattern, command, re.IGNORECASE) for pattern in self.prohibited):
            raise PolicyViolation(f"Command blocked by policy: {command}")
        if not approved and any(re.search(pattern, command, re.IGNORECASE) for pattern in self.approval_required):
            raise ApprovalRequired(f"Human approval required: {command}")
