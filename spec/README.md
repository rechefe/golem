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

**Initial-state anchor**: an emet check can only constrain edges a trace actually reaches, and
emet has no way to require that a trace reaches any particular edge (`emet.md`, "Limitations of
v0"). A property set whose triggers all require some state to have been reached is therefore
satisfied vacuously by a design that never reaches it. Closing that hole is an obligation on
the **harness** and not on the block: every harness that checks a block spec, formal or
simulation, must begin every trace with that block's reset asserted.

The obligation is written down and not left to each harness to remember. **Every block spec
that carries emet properties states it as its own requirement** — an ID in the block's `RST`
area, a Statement that says at which edges the block's reset port is asserted, and a prose
**Acceptance** line. It never carries an emet block, for the reason `UTX-FRM-002` does not: it
constrains the harness rather than the trace, and emet has no `assume`. `UTX-RST-002` in
`uart_tx.md` is the worked example.

**The floor is edges 1 and 2, in every block spec.** Two, not one, because no firing happens at
edge 1 (`emet.md`, "The execution model"): a reset asserted only at edge 1 triggers an
`at 1 after <reset>` anchor property nowhere, so nothing is anchored. Edge 1 constrains the
state that edge 2 — the first checked edge — reads. A block whose anchor needs a longer run
says so and says why; none may ask for less.

A block spec with emet properties and no anchor requirement is a spec bug; so is a harness that
drops the constraint. Because the anchor is a requirement it will appear in the traceability
matrix (`PLAN.md`), so dropping it removes a requirement's only check and the reviewer reads it
as a weakening.

A block spec with no emet properties — `top.md` today — needs no anchor requirement: it has no
triggered check for an unreached state to make vacuous. It acquires one when it acquires a
`unit` block.

**emet**: the property language, defined in `emet.md`. A property block is a fenced ```` ```emet ````
block sitting directly under the requirement it checks; each property in it is named after that
requirement's ID, and the compiler in `formal/emet/` turns it into the one Verilog monitor that
both SymbiYosys and the cocotb simulation use. Where emet cannot express a check — a pin map, a
flow constraint, a prohibition on what the harness may assume, the initial-state anchor it must
establish — the requirement keeps a prose **Acceptance** line instead. Requirements written
before emet still carry Acceptance lines; they are converted file by file, and until a file is
converted its Acceptance lines are its checks.
