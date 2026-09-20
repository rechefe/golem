"""Lexer for emet v0 (spec/emet.md, "Grammar" and "Expressions")."""

from dataclasses import dataclass

from .errors import EmetError

KEYWORDS = {
    "unit", "property", "clock", "reset", "in", "out", "let", "sample",
    "invariant", "at", "within", "hold", "stable", "after", "until",
    "onehot", "mutex", "cover",
}

# Longest-match-first.
PUNCT = [
    "->", "&&", "||", "==", "!=", "<=", ">=",
    "{", "}", "(", ")", "[", "]", ",", ";", ":", ".",
    "+", "-", "*", "/", "%", "!", "~", "&", "|", "^", "<", ">", "?", "=",
]

SIZED_BASES = "dDbBhHoO"


@dataclass
class Token:
    kind: str    # "kw", "id", "num", "dollar", "punct", "eof"
    text: str
    line: int
    value: int | None = None     # for "num": the literal's value
    width: int | None = None     # for "num": None if unsized


class Lexer:
    def __init__(self, path, base_line, text):
        self.path = path
        self.base_line = base_line  # markdown line number of text's line 1
        self.text = text
        self.pos = 0
        self.line = base_line
        self.n = len(text)

    def error(self, msg):
        raise EmetError(self.path, self.line, msg)

    def tokens(self):
        out = []
        while True:
            tok = self._next()
            out.append(tok)
            if tok.kind == "eof":
                break
        return out

    def _peek_char(self, off=0):
        p = self.pos + off
        return self.text[p] if p < self.n else ""

    def _skip_ws_comments(self):
        while self.pos < self.n:
            c = self.text[self.pos]
            if c == "\n":
                self.line += 1
                self.pos += 1
            elif c.isspace():
                self.pos += 1
            elif c == "/" and self._peek_char(1) == "/":
                while self.pos < self.n and self.text[self.pos] != "\n":
                    self.pos += 1
            else:
                break

    def _next(self):
        self._skip_ws_comments()
        if self.pos >= self.n:
            return Token("eof", "", self.line)
        c = self.text[self.pos]
        start_line = self.line

        if c == "$":
            j = self.pos + 1
            while j < self.n and (self.text[j].isalnum() or self.text[j] == "_"):
                j += 1
            name = self.text[self.pos:j]
            self.pos = j
            if name not in ("$t", "$n"):
                self.error(f"unknown identifier '{name}' ($t and $n are the only $-names)")
            return Token("dollar", name, start_line)

        if c.isdigit():
            return self._number(start_line)

        if c.isalpha() or c == "_":
            j = self.pos
            while j < self.n and (self.text[j].isalnum() or self.text[j] == "_"):
                j += 1
            name = self.text[self.pos:j]
            self.pos = j
            kind = "kw" if name in KEYWORDS else "id"
            return Token(kind, name, start_line)

        for p in PUNCT:
            if self.text.startswith(p, self.pos):
                self.pos += len(p)
                return Token("punct", p, start_line)

        self.error(f"unexpected character {c!r}")

    def _number(self, start_line):
        start_pos = self.pos
        j = self.pos
        while j < self.n and (self.text[j].isdigit() or self.text[j] == "_"):
            j += 1
        first = self.text[self.pos:j]
        # sized literal: <size>'<base><digits>
        if j < self.n and self.text[j] == "'":
            size = int(first.replace("_", ""))
            k = j + 1
            if k >= self.n or self.text[k] not in SIZED_BASES:
                self.error("expected a base letter (d/b/h/o) after '")
            base_ch = self.text[k].lower()
            k += 1
            d0 = k
            while k < self.n and (self.text[k].isalnum() or self.text[k] == "_"):
                k += 1
            digits = self.text[d0:k].replace("_", "")
            if digits == "":
                self.error("sized literal has no digits")
            base = {"d": 10, "b": 2, "h": 16, "o": 8}[base_ch]
            try:
                value = int(digits, base)
            except ValueError:
                self.error(f"invalid base-{base} digits {digits!r}")
            self.pos = k
            return Token("num", self.text[start_pos:k], start_line, value=value, width=size)

        value = int(first.replace("_", ""))
        self.pos = j
        return Token("num", first, start_line, value=value, width=None)
