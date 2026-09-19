# Golem MAS (micro-architecture specification)

This directory is the single source of truth for Golem's behaviour. Every agent builds and
checks against it; nothing here is inferred from the RTL.

## Files

| File          | Block                                          |
|---------------|------------------------------------------------|
| `uart_tx.md`  | UART transmitter (Hardcaml gate block)         |
| `top.md`      | Tiny Tapeout top-level pin mapping             |

## Conventions

**Requirement IDs** have the form `<BLOCK>-<AREA>-<NNN>`, e.g. `UTX-FRM-001`. IDs are
permanent: a removed requirement is marked **Withdrawn** with the date, never deleted or
renumbered.

**Every requirement** has three parts:

- **ID** and a one-line title.
- **Statement**: one behaviour, in terms of the block's named ports.
- **Acceptance**: the observable check that proves it.

**Timing** is cycle-exact and uses these terms:

- *Edge e*: the e-th rising edge of `clock`.
- *Value at edge e*: the value a flip-flop clocked by `clock` captures at edge e.
- *Accept edge*: defined per block (for a handshake, the edge where `valid & ready`).

**Reset**: all blocks use a synchronous, active-high `clear`. "After clear" means at every
edge following an edge at which `clear = 1` was sampled, until the block's state changes.

**emet**: property blocks written in emet (from milestone 2026-10-10) sit directly under the
requirement they check. Until then, each requirement's Acceptance line is the property.
