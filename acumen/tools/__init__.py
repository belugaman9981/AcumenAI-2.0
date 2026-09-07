from .calculator import CalculatorTool
from .files import FileReadTool

def build_tools():
    return {
        "calculator": CalculatorTool(),
        "file_read": FileReadTool(),
    }
