from __future__ import annotations
from dataclasses import dataclass

@dataclass
class ToolResult:
    ok: bool
    output: str
    metadata: dict | None = None

class Tool:
    name = "tool"
    description = ""

    def run(self, argument: str) -> ToolResult:
        raise NotImplementedError
