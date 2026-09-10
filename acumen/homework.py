import re

def _extract_math(text):
    low = text.lower()
    # Common prefixes.
    for prefix in ("solve", "calculate", "evaluate"):
        i = low.find(prefix)
        if i >= 0:
            expr = text[i + len(prefix):].strip(" :")
            if expr:
                return expr
    return None

def solve_math(text):
    expr = _extract_math(text)
    if not expr:
        return None
    try:
        import sympy as sp
        expr = expr.replace("^", "**")
        if "=" in expr:
            left, right = expr.split("=", 1)
            x = sp.Symbol("x")
            equation = sp.Eq(sp.sympify(left), sp.sympify(right))
            solution = sp.solve(equation, x)
            return {
                "ok": True,
                "answer": f"x = {solution[0]}" if len(solution) == 1 else f"Solutions: {solution}",
                "sources": [{"title": "Acumen symbolic math engine", "url": "local://sympy"}],
                "confidence": .99,
            }
        value = sp.simplify(sp.sympify(expr))
        return {
            "ok": True,
            "answer": str(value),
            "sources": [{"title": "Acumen symbolic math engine", "url": "local://sympy"}],
            "confidence": .99,
        }
    except Exception:
        return None
