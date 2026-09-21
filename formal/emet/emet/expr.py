"""Expression compiler: typecheck + Verilog codegen in one recursive pass.

Every emet expression carries a *width* (bits, for structural constructs like
concatenation) and a *max_value* (the tightest exact upper bound reachable
through arithmetic, per spec/emet.md "Arithmetic does not wrap" and the
UTX-HSK-003 worked example: `10 * T + 1` is 20 bits because its max value is
655361, not because of Verilog's generic width-growth rules applied to an
8-bit-by-default literal). `width` is always `bits_for(max_value)` except for
concatenation/replication/bit-select/part-select, which are structural and
whose max_value is just `2**width - 1`.
"""

from dataclasses import dataclass, field

from . import ast
from .errors import EmetError


def bits_for(value: int) -> int:
    return max(1, value.bit_length())


@dataclass
class Sym:
    kind: str    # "port", "let", "sample", "dollar"
    width: int
    max_value: int
    vname: str    # the Verilog identifier this name compiles to


@dataclass
class Result:
    text: str
    width: int
    max_value: int
    subs: list = field(default_factory=list)  # [(line, "(a) >= (b)")] pending __range checks


class ExprCompiler:
    def __init__(self, path, scope):
        self.path = path
        self.scope = scope

    def error(self, line, msg):
        raise EmetError(self.path, line, msg)

    def require_bit(self, r: Result, line, what):
        if r.width != 1:
            self.error(line, f"{what} must be 1 bit wide, got {r.width}; compare it explicitly")

    def compile(self, node) -> Result:
        method = getattr(self, f"_c_{type(node).__name__}", None)
        if method is None:
            self.error(getattr(node, "line", 0), f"internal: no compiler for {type(node).__name__}")
        return method(node)

    def _c_EPort(self, node: ast.EPort) -> Result:
        sym = self.scope.get(node.name)
        if sym is None:
            self.error(node.line, f"undefined identifier '{node.name}'")
        return Result(sym.vname, sym.width, sym.max_value)

    def _c_ENum(self, node: ast.ENum) -> Result:
        if node.width is not None:
            if node.value >= (1 << node.width):
                self.error(node.line, f"{node.value} does not fit in {node.width} bits")
            return Result(f"{node.width}'d{node.value}", node.width, node.value)
        # Always emit an explicit size: Verilog gives a bare unsized literal a
        # self-determined width (32 bits) inside a concatenation, which would
        # silently disagree with the width this compiler computed for it.
        w = bits_for(node.value)
        return Result(f"{w}'d{node.value}", w, node.value)

    def _c_EDollar(self, node: ast.EDollar) -> Result:
        sym = self.scope.get(node.name)
        if sym is None:
            self.error(node.line, f"{node.name} is not available in this pattern")
        return Result(sym.vname, sym.width, sym.max_value)

    def _c_EUnop(self, node: ast.EUnop) -> Result:
        r = self.compile(node.operand)
        if node.op == "!":
            self.require_bit(r, node.line, "operand of !")
            return Result(f"(!({r.text}))", 1, 1, r.subs)
        if node.op == "~":
            return Result(f"(~({r.text}))", r.width, (1 << r.width) - 1, r.subs)
        self.error(node.line, f"internal: bad unop {node.op}")

    def _c_EBinop(self, node: ast.EBinop) -> Result:
        l = self.compile(node.left)
        r = self.compile(node.right)
        subs = l.subs + r.subs
        op = node.op
        if op in ("&&", "||"):
            self.require_bit(l, node.line, f"left operand of {op}")
            self.require_bit(r, node.line, f"right operand of {op}")
            return Result(f"(({l.text}) {op} ({r.text}))", 1, 1, subs)
        if op == "->":
            self.require_bit(l, node.line, "left operand of ->")
            self.require_bit(r, node.line, "right operand of ->")
            return Result(f"((!({l.text})) || ({r.text}))", 1, 1, subs)
        if op in ("==", "!=", "<", "<=", ">", ">="):
            return Result(f"(({l.text}) {op} ({r.text}))", 1, 1, subs)
        if op in ("&", "|", "^"):
            w = max(l.width, r.width)
            return Result(f"(({l.text}) {op} ({r.text}))", w, (1 << w) - 1, subs)
        if op == "+":
            mv = l.max_value + r.max_value
            return Result(f"(({l.text}) + ({r.text}))", bits_for(mv), mv, subs)
        if op == "-":
            mv = l.max_value
            subs = subs + [(node.line, f"(({l.text}) >= ({r.text}))")]
            return Result(f"(({l.text}) - ({r.text}))", bits_for(mv), mv, subs)
        if op == "*":
            mv = l.max_value * r.max_value
            return Result(f"(({l.text}) * ({r.text}))", bits_for(mv), mv, subs)
        if op == "/":
            mv = l.max_value
            return Result(f"(({l.text}) / ({r.text}))", bits_for(mv), mv, subs)
        if op == "%":
            mv = (r.max_value - 1) if r.max_value >= 1 else l.max_value
            mv = min(l.max_value, mv) if mv >= 0 else l.max_value
            return Result(f"(({l.text}) % ({r.text}))", bits_for(mv), mv, subs)
        self.error(node.line, f"internal: bad binop {op}")

    def _c_ETernary(self, node: ast.ETernary) -> Result:
        c = self.compile(node.cond)
        self.require_bit(c, node.line, "the '?' condition")
        a = self.compile(node.then)
        b = self.compile(node.els)
        mv = max(a.max_value, b.max_value)
        return Result(f"(({c.text}) ? ({a.text}) : ({b.text}))", bits_for(mv), mv,
                      c.subs + a.subs + b.subs)

    def _c_EConcat(self, node: ast.EConcat) -> Result:
        items = [self.compile(i) for i in node.items]
        w = sum(i.width for i in items)
        subs = []
        for i in items:
            subs += i.subs
        return Result("{" + ", ".join(i.text for i in items) + "}", w, (1 << w) - 1, subs)

    def _c_ERepl(self, node: ast.ERepl) -> Result:
        if node.count < 1:
            self.error(node.line, "replication count must be at least 1")
        r = self.compile(node.expr)
        w = node.count * r.width
        return Result(f"{{{node.count}{{{r.text}}}}}", w, (1 << w) - 1, r.subs)

    def _c_EBitSel(self, node: ast.EBitSel) -> Result:
        base = self.compile(node.base)
        if not (0 <= node.index < base.width):
            self.error(node.line, f"bit index {node.index} out of range for a {base.width}-bit value")
        return Result(f"({base.text}[{node.index}])", 1, 1, base.subs)

    def _c_EPartSel(self, node: ast.EPartSel) -> Result:
        base = self.compile(node.base)
        if not (0 <= node.lo <= node.hi < base.width):
            self.error(node.line, f"part-select [{node.hi}:{node.lo}] out of range for a {base.width}-bit value")
        w = node.hi - node.lo + 1
        return Result(f"({base.text}[{node.hi}:{node.lo}])", w, (1 << w) - 1, base.subs)
