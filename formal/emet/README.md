# The emet compiler

Reads the emet blocks out of the block specs (`spec/README.md`'s Files table) and writes
one plain-Verilog monitor module per `unit` block, used by both SymbiYosys and cocotb. The
language is `spec/emet.md`'s (frozen at the 2026-10-10 milestone); this file is the compiler's
own design decisions, issue #19.

Written in Python rather than OCaml/Hardcaml: it parses Markdown and emits text, it has no use
for Hardcaml's circuit-description API, and `test/` (this lane's other half) is already Python.
`formal/emet/emet/` is a small hand-written recursive-descent compiler (lexer, parser, an
expression compiler that does width/value-range inference and Verilog codegen together) with
no dependencies beyond the standard library; `formal/emet/test/` is its pytest suite.

## Status: waiting on spec PRs #18 and #21

`spec/emet.md` (#18) and the emet conversion of `spec/uart_tx.md` (#21) are open but not yet
merged to `spec-provisional`, so on `main` today there is no `unit` block anywhere in `spec/`
and `make emet` legitimately compiles zero units — `formal/emet/generated/` is committed in
that empty state. The compiler was developed and proof-tested against `spec/uart_tx.md` as
PR #21 converts it (copied verbatim into `formal/emet/test/fixtures/uart_tx_emet.md` — see that
file's header) and against real formal/sim runs with that content overlaid locally
(never committed to `spec/`, which is outside this lane). Once #18 and #21 land, `make emet`
picks the real content up with no further change here.

## 1. Reaching a unit that is not the top module

`test/tb.v` reaches a block's ports through a hierarchical reference `user_project.<module>.
<port>` (`user_project` is `tb.v`'s existing instance of `tt_um_rechefe_golem`), generated into
`formal/emet/generated/tb_emet.vh` and `` `include``d from `tb.v`. This relies on a convention
that holds today but isn't enforced anywhere: a Hardcaml-generated top level instantiates a
block using the block's own module name as the instance name (`rtl/`: `golem_uart_tx
golem_uart_tx (...)` inside `tt_um_rechefe_golem`). Some of a unit's ports (e.g. UTX's
`divisor`, tied to a constant inside the top level) aren't top-level pins at all, so watching
the top-level unit instead was not an option, and Icarus's lack of a usable `bind` rules that
mechanism out too (`emet.md` already says as much).

If a future block's instance name ever diverges from its module name, `make sim` fails loudly
(`` `include``d hierarchical path unresolved) rather than silently watching the wrong signals;
the fix is a one-line rename in `rtl/`, not a change here. Verified against the real
Hardcaml-generated `src/golem.v`: a monitor instantiated this way elaborates, runs clean
through several frames with `emet_any_fail` never rising, and (mutation-tested by hand: negate
`golem_uart_tx`'s `tx` output) reliably catches a real fault at the edge it happens.

Formal does not have this problem: `formal/emet/generated/emet_<unit>_formal.v` instantiates
the block module directly, the same way the hand-written `formal/uart_tx.sby` does, never going
through the pin-mapped top.

## 2. Build integration

- The compiler lives in `formal/emet/`, invoked by `make emet` (root `Makefile`), which writes
  `formal/emet/generated/`: one `emet_<unit>.v` monitor, one `emet_<unit>_formal.v` harness +
  `emet_<unit>.sby` job, `tb_emet.vh` (sim wiring), `sim_sources.mk` (a fragment `test/Makefile`
  includes), `covers.py` (cover-flag labels for cocotb) and `traceability.md` per unit found.
- `check-emet-generated` (`git diff --quiet` after a fresh `make emet`, the same shape as
  `check-generated` for `src/golem.v`) fails CI when a spec edit wasn't recompiled.
- Ordering in `make ci`: `rtl unit check-generated emet check-emet-generated sim formal` --
  `emet` before `sim`/`formal` because both harnesses consume its output.
- `SBY_JOBS` picks up `formal/emet/generated/*.sby` alongside the hand-written `formal/*.sby`;
  `make formal`'s recipe now `cd`s to each job's own directory (`dirname`) rather than assuming
  every job lives flat in `formal/`.
- `make clean` no longer deletes every top-level directory under `formal/` (that would delete
  this compiler's own source tree, `formal/emet/`, along with SymbiYosys's work directories);
  it excludes `formal/emet` and separately sweeps `formal/emet/generated/`'s own work dirs.

## 3. What the two harnesses do with the monitor

- **Simulation**: `emet_fail` is checked once, at the end of each cocotb test
  (`test/test.py`'s `assert_emet_ok`), not at the edge it rises. It's sticky, so this still
  catches a failure anywhere earlier in the test; checking at the rising edge would only add a
  slightly more precise failure message cocotb's own assertion traceback already gives (the
  test that was running, roughly where in it). Not present under `GATES=yes`: a gate-level
  netlist doesn't preserve the block-level instance names p.1's hierarchical references need,
  so `test/Makefile` only defines `EMET_SIM` and compiles the generated monitors in for RTL sim.
- The `<LABEL>_cover_<tag>_hit` flags (and every `__fired`) are reported by a dedicated
  `test_emet_coverage_report` cocotb test, defined last in `test/test.py` so it runs after
  (and therefore sees the accumulated hits of) every test above it in the same continuing
  simulation. It reads `formal/emet/generated/covers.py` (generated: the label list, scraped
  from the compiled Verilog rather than plumbed a second time through `compile_unit.py`'s
  return value) and logs hit/missed for each. Informational only (it still fails via
  `assert_emet_ok` if a check itself failed); turning a miss into a hard CI failure is future
  work once there's a real coverage target to hold blocks to.
- **Formal**: one generated `.sby` job per unit, `prove`/`cover` tasks, modeled on
  `formal/uart_tx.sby` (`abc pdr` unbounded, `cover` at depth 40). The harness additionally
  `assume`s the unit's `reset` expression at the first sampled edge -- emet itself has no
  `assume` (a property must mean the same thing to both harnesses), but a *harness*-level
  assumption about the environment's start state is exactly what the hand-written harness
  already does, and without it PDR finds a trivial "reset never happened" counterexample against
  `UTX_IDL_001` in frame 0.

## 4. Proof feasibility of the emitted counters

Confirmed the concern the issue raised. Against `spec/uart_tx.md` as #21 converts it:

- The hand-written `formal/uart_tx_props.v` (the `(bit, sub)` pair `emet.md` mentions) proves
  the whole block unbounded in ~53s (`abc pdr`).
- The emet-compiled monitor's flat `UTX-HSK-003` counter (`10 * T + 1`, 20 bits, the exact
  example the issue names) does **not** converge: isolated to that one property alone, `abc pdr`
  neither proves nor refutes it within 5 minutes; the full 7-property monitor was killed at the
  8-minute mark still expanding frames, no proof and no counterexample either way. (The `cover`
  task is unaffected -- BMC-based reachability, not PDR -- and passes in under a second,
  including every `__fired` non-vacuity check.)

This is exactly the fallback PLAN.md names: "proven to a stated depth, justified in the spec."
The compiler emits the counter literally as `emet.md` specifies it (the spec's pseudocode is
the language's semantics, not an implementation suggestion the compiler is free to improve on),
so closing this gap is not a compiler fix -- it would mean either a `smtbmc` bounded run with a
depth `spec/uart_tx.md` states and justifies (e.g. "40 > one full frame at divisor 3", the
style `formal/uart_tx.sby`'s own comment already uses), or a language change (letting a property
suggest an internal encoding) that is explicitly not the verifier's call under emet v0's freeze.
Reported on issue #19 itself with this evidence, per the issue's own instruction; until it's
resolved, a unit whose counters are this wide should keep its hand-written `formal/*.sby`
alongside the generated one rather than replace it.

## 5. Traceability

`formal/emet/generated/traceability.md`: requirement ID -> unit -> property labels, one row per
requirement, regenerated by `make emet`. Mutation-kill status is *not* wired up for emet
monitors yet: `mcy` today mutates `src/golem.v` and checks it against `formal/*.sby`; a
generated `.sby` job is picked up by the same mechanism with no changes needed, so participation
is really "point `mcy`'s config at `formal/emet/generated/*.sby` too" plus a per-property (not
just per-job) kill breakdown, which is more than this issue's scope. Left as a follow-up rather
than half-built into the matrix now.

## 6. Diagnostics

Every compiler error is `path/to/spec-file.md:<line>: error: ...`, pointing at the Markdown
line inside the `` ```emet `` fence, not generated Verilog -- the extractor
(`emet/extract.py`) records each block's starting line, and the lexer/parser/expression
compiler carry that offset through every token and AST node, so a mistake three levels into an
expression still resolves to a real source line a spec author can jump to.

The `unit` block vs. interface table cross-check is cheap and implemented
(`driver.py:_check_unit_matches_table`): for every `in`/`out` port the `unit` block declares,
if the interface table above it lists that same port name, their widths must agree. It does
not check *presence* both ways (a port only in the table, or only in the block, isn't caught)
since matching table rows to block ports by position rather than name would be brittle across
edits; matching what's cheap and leaving the rest to the reviewer, as the issue allows.
