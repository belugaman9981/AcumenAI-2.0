import ast,operator as op
OPS={ast.Add:op.add,ast.Sub:op.sub,ast.Mult:op.mul,ast.Div:op.truediv,ast.FloorDiv:op.floordiv,ast.Mod:op.mod,ast.Pow:op.pow,ast.USub:op.neg,ast.UAdd:op.pos}
def _e(n):
    if isinstance(n,ast.Expression):return _e(n.body)
    if isinstance(n,ast.Constant) and isinstance(n.value,(int,float)):return n.value
    if isinstance(n,ast.BinOp) and type(n.op) in OPS:return OPS[type(n.op)](_e(n.left),_e(n.right))
    if isinstance(n,ast.UnaryOp) and type(n.op) in OPS:return OPS[type(n.op)](_e(n.operand))
    raise ValueError('unsupported expression')
def calculate(s): return str(_e(ast.parse(s,mode='eval')))
