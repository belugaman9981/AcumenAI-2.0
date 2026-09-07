from __future__ import annotations
from pathlib import Path
from .base import Tool, ToolResult

class FileReadTool(Tool):
    name = "file_read"
    description = "Read a UTF-8 text file."

    def run(self, argument: str) -> ToolResult:
        try:
            p = Path(argument).expanduser()
            if not p.exists() or not p.is_file():
                return ToolResult(False, "File not found.")
            if p.stat().st_size > 2_000_000:
                return ToolResult(False, "File is too large for the simple reader.")
            text = p.read_text(encoding="utf-8", errors="ignore")
            return ToolResult(True, text)
        except Exception as e:
            return ToolResult(False, f"File read error: {e}")
