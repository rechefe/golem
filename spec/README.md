# Golem MAS (micro-architecture specification)

This directory is the single source of truth for Golem's behaviour. Every agent builds and
checks against it; nothing here is inferred from the RTL.

## Files

| File          | Block                                          |
|---------------|------------------------------------------------|
| `uart_tx.md`  | UART transmitter (Hardcaml gate block)         |
| `top.md`      | Tiny Tapeout top-level pin mapping             |
| `emet.md`     | emet: the property language checks are written in (not a block) |

## Conventions

**Requirement IDs** have the form `<BLOCK>-<AREA>-<NNN>`, e.g. `UTX-FRM-001`. IDs are
permanent: a removed requirement is marked **Withdrawn** with the date, never deleted or
renumbered.

**Every requirement** has three parts:

- **ID** and a one-line title.
- **Statement**: one behaviour, in terms of the block's named ports.
- **Check**: the observable check that proves it — an **emet** block (`emet.md`) sitting
  directly under the requirement, or, only where emet cannot express the check, a prose
  **Acceptance** line. Never both, never neither.

A requirement may also carry one or more **Note** paragraphs: prose that says how to read its
check, or records a consequence of it. A Note is explanatory and is **never itself a check** —
nothing in it is proven. A claim that needs proving belongs in a Statement and a check, in this
requirement or another one.

**Timing** is cycle-exact and uses these terms:

- *Edge e*: the e-th rising edge of `clock`.
- *Value at edge e*: the value a flip-flop clocked by `clock` captures at edge e.
- *Accept edge*: defined per block (for a handshake, the edge where `valid & ready`).

**Reset**: all blocks use a synchronous, active-high `clear`. "After clear" means at every
edge following an edge at which `clear = 1` was sampled, until the block's state changes.

**emet**: the property language, defined in `emet.md`. A property block is a fenced ```` ```emet ````
block sitting directly under the requirement it checks; each property in it is named after that
requirement's ID, and the compiler in `formal/emet/` turns it into the one Verilog monitor that
both SymbiYosys and the cocotb simulation use. Where emet cannot express a check — a pin map, a
flow constraint, a prohibition on what the harness may assume — the requirement keeps a prose
**Acceptance** line instead. Requirements written before emet still carry Acceptance lines;
they are converted file by file, and until a file is converted its Acceptance lines are its
checks.
