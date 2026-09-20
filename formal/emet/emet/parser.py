"""Recursive-descent parser for emet v0 (spec/emet.md, "Grammar")."""

from . import ast
from .errors import EmetError
from .lexer import Lexer

REQ_ID_RE = __import__("re").compile(r"^[A-Z]{2,4}-[A-Z]{2,4}-[0-9]{3}$")
TAG_RE = __import__("re").compile(r"^[a-z0-9_]+$")
IDENT_RE = __import__("re").compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Binary operator precedence, loosest first. Each level is left-associative
# except implication and ternary, handled separately.
PREC_LEVELS = [
    ["||"],
    ["&&"],
    ["|"],
    ["^"],
    ["&"],
    ["==", "!="],
    ["<", "<=", ">", ">="],
    ["+", "-"],
    ["*", "/", "%"],
]


class Parser:
    def __init__(self, path, tokens):
        self.path = path
        self.toks = tokens
        self.i = 0

    def peek(self, off=0):
        return self.toks[min(self.i + off, len(self.toks) - 1)]

    def error(self, msg, tok=None):
        tok = tok or self.peek()
        raise EmetError(self.path, tok.line, msg)

    def advance(self):
        tok = self.toks[self.i]
        if self.i < len(self.toks) - 1:
            self.i += 1
        return tok

    def expect_punct(self, p):
        tok = self.peek()
        if tok.kind != "punct" or tok.text != p:
            self.error(f"expected {p!r}, got {tok.text!r}")
        return self.advance()

    def expect_kw(self, kw):
        tok = self.peek()
        if tok.kind != "kw" or tok.text != kw:
            self.error(f"expected {kw!r}, got {tok.text!r}")
        return self.advance()

    def expect_id(self):
        tok = self.peek()
        if tok.kind != "id":
            self.error(f"expected an identifier, got {tok.text!r}")
        return self.advance()

    def at_punct(self, p):
        tok = self.peek()
        return tok.kind == "punct" and tok.text == p

    def at_kw(self, kw):
        tok = self.peek()
        return tok.kind == "kw" and tok.text == kw

    # ---- top level -----------------------------------------------------

    def parse_block(self):
        items = []
        while self.peek().kind != "eof":
            if self.at_kw("unit"):
                items.append(self.parse_unit())
            elif self.at_kw("property"):
                items.append(self.parse_property())
            else:
                self.error(f"expected 'unit' or 'property', got {self.peek().text!r}")
        return items

    def parse_unit(self):
        tok = self.expect_kw("unit")
        name = self.expect_id().text
        module = self.expect_id().text
        self.expect_punct("{")
        clock = None
        reset = None
        ports = []
        lets = []
        while not self.at_punct("}"):
            if self.at_kw("clock"):
                self.advance()
                # spec/emet.md, Grammar: "a port named `clock` is fine" -- the
                # only place the identifier and the keyword can collide.
                tok = self.peek()
                if tok.kind == "id" or (tok.kind == "kw" and tok.text == "clock"):
                    clock = self.advance().text
                else:
                    self.error(f"expected the clock port's name, got {tok.text!r}")
                self.expect_punct(";")
            elif self.at_kw("reset"):
                self.advance()
                reset = self.parse_expr()
                self.expect_punct(";")
            elif self.at_kw("in") or self.at_kw("out"):
                direction = self.advance().text
                pname = self.expect_id().text
                wtok = self.peek()
                if wtok.kind != "num" or wtok.width is not None:
                    self.error("expected a plain integer width")
                width = self.advance().value
                self.expect_punct(";")
                ports.append(ast.Port(pname, width, direction, wtok.line))
            elif self.at_kw("let"):
                lets.append(self.parse_let())
            else:
                self.error(f"unexpected token in unit block: {self.peek().text!r}")
        self.expect_punct("}")
        if clock is None:
            self.error("unit block is missing 'clock'", tok)
        return ast.Unit(name, module, clock, reset, ports, lets, tok.line)

    def parse_let(self):
        tok = self.expect_kw("let")
        name = self.expect_id().text
        self.expect_punct("=")
        # '=' is not in PUNCT list (only used here); consume '=' specially.
        expr = self.parse_expr()
        self.expect_punct(";")
        return ast.LetDecl(name, expr, tok.line)

    def parse_property(self):
        tok = self.expect_kw("property")
        name_tok = self.peek()
        name = self._parse_prop_name()
        if "." in name:
            req_id, tag = name.split(".", 1)
        else:
            req_id, tag = name, None
        if not REQ_ID_RE.match(req_id):
            self.error(f"{req_id!r} is not a requirement ID (BLOCK-AREA-NNN)", name_tok)
        if tag is not None and not TAG_RE.match(tag):
            self.error(f"{tag!r} is not a valid tag (lower-case, digits, underscore)", name_tok)
        self.expect_punct("{")
        decls = []
        while self.at_kw("let") or self.at_kw("sample"):
            if self.at_kw("let"):
                decls.append(self.parse_let())
            else:
                decls.append(self.parse_sample())
        pattern = None
        if not self.at_kw("cover") and not self.at_punct("}"):
            pattern = self.parse_pattern()
        covers = []
        while self.at_kw("cover"):
            covers.append(self.parse_cover())
        self.expect_punct("}")
        return ast.Property(name, req_id, tag, decls, pattern, covers, tok.line)

    def _parse_prop_name(self):
        # req-id ::= upper{2,4} "-" upper{2,4} "-" digit{3} -- hyphenated, so
        # it isn't a single `ident` token; stitch it back together here.
        area1 = self.expect_id()
        self.expect_punct("-")
        area2 = self.expect_id()
        self.expect_punct("-")
        numtok = self.peek()
        if numtok.kind != "num" or numtok.width is not None or len(numtok.text) != 3 or not numtok.text.isdigit():
            self.error("expected a 3-digit requirement number")
        self.advance()
        name = f"{area1.text}-{area2.text}-{numtok.text}"
        if self.at_punct("."):
            self.advance()
            tagtok = self.peek()
            if tagtok.kind not in ("id",):
                self.error("expected a tag after '.'")
            self.advance()
            name = name + "." + tagtok.text
        return name

    def parse_sample(self):
        tok = self.expect_kw("sample")
        name = self.expect_id().text
        self.expect_punct("=")
        expr = self.parse_expr()
        self.expect_punct(";")
        return ast.SampleDecl(name, expr, tok.line)

    def parse_pattern(self):
        tok = self.peek()
        if self.at_kw("invariant"):
            self.advance()
            cond = self.parse_expr()
            self.expect_punct(";")
            return ast.PInvariant(cond, tok.line)
        if self.at_kw("at") or self.at_kw("within") or self.at_kw("hold"):
            kw = self.advance().text
            count = self.parse_expr()
            self.expect_kw("after")
            trigger = self.parse_expr()
            self.expect_punct(":")
            cond = self.parse_expr()
            self.expect_punct(";")
            cls = {"at": ast.PAt, "within": ast.PWithin, "hold": ast.PHold}[kw]
            return cls(count, trigger, cond, tok.line)
        if self.at_kw("stable"):
            self.advance()
            expr = self.parse_expr()
            self.expect_kw("after")
            trigger = self.parse_expr()
            self.expect_kw("until")
            release = self.parse_expr()
            self.expect_punct(";")
            return ast.PStable(expr, trigger, release, tok.line)
        if self.at_kw("onehot") or self.at_kw("mutex"):
            kw = self.advance().text
            self.expect_punct("{")
            conds = [self.parse_expr()]
            while self.at_punct(","):
                self.advance()
                conds.append(self.parse_expr())
            self.expect_punct("}")
            self.expect_punct(";")
            if len(conds) < 2:
                self.error(f"{kw} needs two or more entries", tok)
            cls = ast.POnehot if kw == "onehot" else ast.PMutex
            return cls(conds, tok.line)
        self.error(f"expected a pattern, got {tok.text!r}")

    def parse_cover(self):
        tok = self.expect_kw("cover")
        tagtok = self.expect_id()
        if not TAG_RE.match(tagtok.text):
            self.error(f"{tagtok.text!r} is not a valid cover tag", tagtok)
        self.expect_punct(":")
        expr = self.parse_expr()
        self.expect_punct(";")
        return ast.Cover(tagtok.text, expr, tok.line)

    # ---- expressions -----------------------------------------------------

    def parse_expr(self):
        return self.parse_implies()

    def parse_implies(self):
        left = self.parse_ternary()
        if self.at_punct("->"):
            tok = self.advance()
            right = self.parse_implies()  # right-associative
            return ast.EBinop("->", left, right, tok.line)
        return left

    def parse_ternary(self):
        cond = self.parse_binop(0)
        if self.at_punct("?"):
            tok = self.advance()
            then = self.parse_implies()
            self.expect_punct(":")
            els = self.parse_implies()
            return ast.ETernary(cond, then, els, tok.line)
        return cond

    def parse_binop(self, level):
        if level >= len(PREC_LEVELS):
            return self.parse_unary()
        left = self.parse_binop(level + 1)
        while self.peek().kind == "punct" and self.peek().text in PREC_LEVELS[level]:
            tok = self.advance()
            right = self.parse_binop(level + 1)
            left = ast.EBinop(tok.text, left, right, tok.line)
        return left

    def parse_unary(self):
        tok = self.peek()
        if tok.kind == "punct" and tok.text in ("!", "~"):
            self.advance()
            operand = self.parse_unary()
            return ast.EUnop(tok.text, operand, tok.line)
        return self.parse_postfix()

    def parse_postfix(self):
        expr = self.parse_primary()
        while self.at_punct("["):
            tok = self.advance()
            hi = self._const_int()
            if self.at_punct(":"):
                self.advance()
                lo = self._const_int()
                self.expect_punct("]")
                expr = ast.EPartSel(expr, hi, lo, tok.line)
            else:
                self.expect_punct("]")
                expr = ast.EBitSel(expr, hi, tok.line)
        return expr

    def _const_int(self):
        tok = self.peek()
        if tok.kind != "num":
            self.error("expected a constant integer index")
        self.advance()
        return tok.value

    def parse_primary(self):
        tok = self.peek()
        if tok.kind == "num":
            self.advance()
            return ast.ENum(tok.value, tok.width, tok.line)
        if tok.kind == "dollar":
            self.advance()
            return ast.EDollar(tok.text, tok.line)
        if tok.kind == "id":
            self.advance()
            return ast.EPort(tok.text, tok.line)
        if tok.kind == "punct" and tok.text == "(":
            self.advance()
            expr = self.parse_expr()
            self.expect_punct(")")
            return expr
        if tok.kind == "punct" and tok.text == "{":
            self.advance()
            first = self.parse_expr()
            # replication: {n{expr}}
            if self.at_punct("{"):
                if not isinstance(first, ast.ENum):
                    self.error("replication count must be a constant integer")
                self.advance()
                inner = self.parse_expr()
                self.expect_punct("}")
                self.expect_punct("}")
                return ast.ERepl(first.value, inner, tok.line)
            items = [first]
            while self.at_punct(","):
                self.advance()
                items.append(self.parse_expr())
            self.expect_punct("}")
            return ast.EConcat(items, tok.line)
        self.error(f"unexpected token {tok.text!r}")


def parse(path, base_line, text):
    toks = Lexer(path, base_line, text).tokens()
    return Parser(path, toks).parse_block()
