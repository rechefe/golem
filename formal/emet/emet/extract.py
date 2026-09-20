"""spec/emet.md, "Where emet lives in the MAS": the fenced-block convention.

Reads the block files out of spec/README.md's Files table, then pulls every
` ```emet ` fenced block out of each one, tagged with the nearest `###` requirement
heading above it (a property's section) and whether it sits under the `## Interface`
heading (where the `unit` block belongs).
"""

import re
from dataclasses import dataclass
from pathlib import Path

REQ_ID_RE = re.compile(r"\b([A-Z]{2,4}-[A-Z]{2,4}-[0-9]{3})\b")
FILE_ROW_RE = re.compile(r"^\|\s*`([^`]+\.md)`\s*\|")


@dataclass
class EmetBlock:
    spec_file: Path       # path to the .md file, relative to repo root
    start_line: int        # 1-based line number of the first line *inside* the fence
    text: str               # the block's raw emet source
    section_id: str | None  # nearest ### heading's requirement ID, or None
    in_interface: bool      # nearest ## heading (if any) is "Interface"


def block_files(spec_readme: Path) -> list[Path]:
    """The Files table in spec/README.md, excluding README.md and emet.md themselves
    (spec/emet.md, "the block files of the Files table ... every spec/*.md except
    README.md and this file")."""
    spec_dir = spec_readme.parent
    files = []
    in_table = False
    for line in spec_readme.read_text().splitlines():
        if line.strip().startswith("| File"):
            in_table = True
            continue
        if in_table:
            if not line.strip().startswith("|"):
                break
            m = FILE_ROW_RE.match(line.strip())
            if m:
                name = m.group(1)
                if name not in ("README.md", "emet.md"):
                    files.append(spec_dir / name)
    return files


def extract_blocks(spec_file: Path) -> list[EmetBlock]:
    blocks = []
    section_id = None
    in_interface = False
    lines = spec_file.read_text().splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.startswith("## "):
            in_interface = line[3:].strip() == "Interface"
            section_id = None
        elif line.startswith("### "):
            m = REQ_ID_RE.search(line)
            section_id = m.group(1) if m else None
        if line == "```emet":
            start = i + 1  # 1-based line number of the first content line
            body_lines = []
            i += 1
            closed = False
            while i < n:
                if lines[i] == "```":
                    closed = True
                    break
                body_lines.append(lines[i])
                i += 1
            if not closed:
                raise SystemExit(f"{spec_file}:{start}: error: unterminated ```emet block")
            blocks.append(
                EmetBlock(
                    spec_file=spec_file,
                    start_line=start + 1,
                    text="\n".join(body_lines),
                    section_id=section_id,
                    in_interface=in_interface,
                )
            )
        i += 1
    return blocks
