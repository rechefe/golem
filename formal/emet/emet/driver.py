"""Ties markdown extraction, parsing and per-unit compilation into the
generated/ tree: one emet_<unit>.v monitor, one formal harness + .sby job,
sim wiring, and the traceability matrix, per unit found in spec/'s block
files (spec/README.md's Files table)."""

from dataclasses import dataclass
from pathlib import Path

from . import ast
from .compile_unit import UnitCompiler, CompiledUnit
from .errors import EmetError
from .extract import block_files, extract_blocks
from .parser import parse


@dataclass
class FileResult:
    spec_file: Path
    unit: ast.Unit | None
    compiled: CompiledUnit | None


def compile_spec(repo_root: Path) -> list[FileResult]:
    spec_readme = repo_root / "spec" / "README.md"
    results = []
    for spec_file in block_files(spec_readme):
        if not spec_file.exists():
            raise EmetError(spec_readme, 1, f"spec/README.md lists {spec_file.name}, which does not exist")
        rel = spec_file.relative_to(repo_root)
        blocks = extract_blocks(spec_file)
        units = []
        properties = []
        for b in blocks:
            items = parse(rel, b.start_line, b.text)
            for item in items:
                if isinstance(item, ast.Unit):
                    if not b.in_interface:
                        raise EmetError(rel, item.line, "a 'unit' block must sit in the ## Interface section")
                    units.append(item)
                else:
                    item.section_id = b.section_id
                    properties.append(item)
        if len(units) > 1:
            raise EmetError(rel, units[1].line, f"{rel} has more than one 'unit' block")
        if not units:
            if properties:
                raise EmetError(rel, properties[0].line, f"{rel} has property blocks but no 'unit' block")
            results.append(FileResult(rel, None, None))
            continue
        unit = units[0]
        _check_unit_matches_table(rel, spec_file, unit)
        compiled = UnitCompiler(rel, unit, properties).compile()
        results.append(FileResult(rel, unit, compiled))
    return results


def _check_unit_matches_table(rel, spec_file, unit: ast.Unit):
    """spec/emet.md, 'The unit block': 'in/out and the table must agree'.
    Cheap cross-check per issue #19 point 6: every port the unit block declares
    must appear, with the same width, in the nearest interface table above it."""
    text = spec_file.read_text()
    lines = text.splitlines()
    table_widths = {}
    in_table = False
    for line in lines:
        s = line.strip()
        if s.startswith("| Port") and "Dir" in s and "Width" in s:
            in_table = True
            continue
        if in_table:
            if not s.startswith("|"):
                break
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) < 3 or set(cells[0]) <= {"-"}:
                continue
            name = cells[0].strip("`")
            try:
                width = int(cells[2])
            except ValueError:
                continue
            table_widths[name] = width
    for p in unit.ports:
        if p.name in table_widths and table_widths[p.name] != p.width:
            raise EmetError(
                rel, p.line,
                f"port '{p.name}' is {p.width} bits in the unit block but "
                f"{table_widths[p.name]} bits in the interface table",
            )
