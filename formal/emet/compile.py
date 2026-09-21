#!/usr/bin/env python3
"""The emet compiler CLI: `make emet` runs this to regenerate everything
under formal/emet/generated/ from the emet blocks in spec/*.md.

See spec/emet.md for the language and formal/emet/README.md for the
compiler's own design decisions.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from emet import output
from emet.driver import compile_spec
from emet.errors import EmetError


def main():
    repo_root = Path(__file__).resolve().parents[2]
    generated = repo_root / "formal" / "emet" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    for old in generated.iterdir():
        if old.is_file():
            old.unlink()

    try:
        results = compile_spec(repo_root)
    except EmetError as e:
        print(e, file=sys.stderr)
        return 1

    for r in results:
        if r.compiled is None:
            continue
        output.write_monitor(generated, r.compiled)
        (generated / f"{r.compiled.module_name}_formal.v").write_text(
            output.formal_harness(r.unit, r.compiled)
        )
        (generated / f"{r.compiled.module_name}.sby").write_text(
            output.sby_job(r.unit, r.compiled, r.spec_file)
        )

    (generated / "tb_emet.vh").write_text(output.tb_include(results))
    (generated / "sim_sources.mk").write_text(output.sim_sources_mk(results))
    (generated / "covers.py").write_text(output.covers_py(results))
    (generated / "traceability.md").write_text(output.traceability_md(results))

    n_units = sum(1 for r in results if r.compiled is not None)
    n_props = sum(len(r.compiled.properties) for r in results if r.compiled is not None)
    print(f"emet: compiled {n_units} unit(s), {n_props} requirement(s) with properties")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
