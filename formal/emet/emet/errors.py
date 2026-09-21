"""Diagnostics that point at the Markdown source, not the generated Verilog."""


class EmetError(Exception):
    def __init__(self, path, line, message):
        self.path = path
        self.line = line
        self.message = message
        super().__init__(f"{path}:{line}: error: {message}")
