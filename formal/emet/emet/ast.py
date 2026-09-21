"""AST for emet v0. Every node carries the source line it came from, so
diagnostics and generated-Verilog comments can point back at the Markdown."""

from dataclasses import dataclass, field


# ---- Expressions -----------------------------------------------------------

@dataclass
class EPort:
    name: str
    line: int


@dataclass
class ENum:
    value: int
    width: int | None  # None if unsized
    line: int


@dataclass
class EDollar:
    name: str  # "$t" or "$n"
    line: int


@dataclass
class EUnop:
    op: str
    operand: object
    line: int


@dataclass
class EBinop:
    op: str
    left: object
    right: object
    line: int


@dataclass
class ETernary:
    cond: object
    then: object
    els: object
    line: int


@dataclass
class EConcat:
    items: list
    line: int


@dataclass
class ERepl:
    count: int  # compile-time constant
    expr: object
    line: int


@dataclass
class EBitSel:
    base: object
    index: int  # compile-time constant
    line: int


@dataclass
class EPartSel:
    base: object
    hi: int
    lo: int
    line: int


# ---- Declarations -----------------------------------------------------------

@dataclass
class LetDecl:
    name: str
    expr: object
    line: int


@dataclass
class SampleDecl:
    name: str
    expr: object
    line: int


@dataclass
class Port:
    name: str
    width: int
    direction: str  # "in" or "out"
    line: int


@dataclass
class Unit:
    name: str          # requirement-ID prefix, e.g. "UTX"
    module: str         # Verilog module watched
    clock: str
    reset: object | None  # expr, or None
    ports: list          # list[Port] in declaration order
    lets: list             # list[LetDecl]
    line: int


# ---- Patterns -----------------------------------------------------------

@dataclass
class PInvariant:
    cond: object
    line: int


@dataclass
class PAt:
    count: object
    trigger: object
    cond: object
    line: int


@dataclass
class PWithin:
    count: object
    trigger: object
    cond: object
    line: int


@dataclass
class PHold:
    count: object
    trigger: object
    cond: object
    line: int


@dataclass
class PStable:
    expr: object
    trigger: object
    release: object
    line: int


@dataclass
class POnehot:
    conds: list
    line: int


@dataclass
class PMutex:
    conds: list
    line: int


@dataclass
class Cover:
    tag: str
    expr: object
    line: int


@dataclass
class Property:
    name: str        # full name, e.g. "UTX-HSK-002" or "UTX-RST-001.tx"
    req_id: str        # base requirement id, "UTX-HSK-002"
    tag: str | None
    decls: list           # list[LetDecl | SampleDecl], in order
    pattern: object | None
    covers: list
    line: int
    section_id: str | None = None
