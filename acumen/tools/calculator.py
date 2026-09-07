from __future__ import annotations
import ast
import operator as op
from .base import Tool, ToolResult

OPS = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv, ast.Mod: op.mod, ast.Pow: op.pow,
    ast.USub: op.neg, ast.UAdd: op.pos,
}

def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.operand))
    raise ValueError("Unsupported expression")

class CalculatorTool(Tool):
    name = "calculator"
    description = "Safely evaluate arithmetic expressions."

    def run(self, argument: str) -> ToolResult:
        try:
            tree = ast.parse(argument, mode="eval")
            result = _eval(tree)
            return ToolResult(True, str(result))
        except Exception as e:
            return ToolResult(False, f"Calculator error: {e}")
