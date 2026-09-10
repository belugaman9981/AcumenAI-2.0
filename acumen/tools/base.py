from dataclasses import dataclass

@dataclass
class ToolResult:
    ok: bool
    output: str
    metadata: dict | None = None
