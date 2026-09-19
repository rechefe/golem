# UART transmitter (`UTX`)

Status: **v1, gate block.** Temporary fixed-function block used to prove the Hardcaml → formal →
GDS flow end to end. It will be replaced by a sequencer program once the sequencer exists.

Transmits one byte as an 8N1 frame (1 start bit, 8 data bits LSB first, 1 stop bit, no parity)
with a programmable bit period.

## Interface

Module name: `golem_uart_tx`.

| Port      | Dir | Width | Description                                              |
|-----------|-----|-------|----------------------------------------------------------|
| `clock`   | in  | 1     | Rising-edge clock.                                       |
| `clear`   | in  | 1     | Synchronous reset, active high.                          |
| `data`    | in  | 8     | Byte to transmit.                                        |
| `valid`   | in  | 1     | Request to transmit `data`.                              |
| `divisor` | in  | 16    | Bit period minus one, in clock cycles.                   |
| `tx`      | out | 1     | Serial output. Idle high.                                |
| `ready`   | out | 1     | High when the block can accept a byte.                   |

**Definitions**

- *Accept edge*: an edge at which `valid = 1`, `ready = 1` and `clear = 0` are sampled.
- *T*: the bit period in cycles, `T = divisor + 1`, using the `divisor` value sampled at the
  accept edge. `T` ranges from 1 to 65536.
- *Frame bits*: `F[0] = 0` (start), `F[1..8] = data[0..7]` sampled at the accept edge,
  `F[9] = 1` (stop).

## Requirements

### UTX-RST-001 — Reset state

**Statement**: At the first edge after an edge where `clear = 1` was sampled, `tx = 1` and
`ready = 1`. This holds whatever the block was doing, including mid-frame.

**Acceptance**: for every edge e with `clear = 1` sampled at e and `clear = 0` at e+1:
`tx = 1` and `ready = 1` at edge e+1.

### UTX-IDL-001 — Idle line is high

**Statement**: Whenever `ready = 1`, `tx = 1`.

**Acceptance**: at every edge, `ready = 1` implies `tx = 1`.

### UTX-HSK-001 — Single acceptance

**Statement**: A byte is accepted only at an accept edge. `valid` while `ready = 0` has no
effect and is not queued.

**Acceptance**: a frame (start bit after idle) begins only one edge after an accept edge.

### UTX-HSK-002 — Busy during a frame

**Statement**: For an accept edge k and no `clear`, `ready = 0` at edges k+1 through k+10T.

**Acceptance**: as stated, for every accepted byte and every T.

### UTX-HSK-003 — Ready after the frame

**Statement**: For an accept edge k and no `clear`, `ready = 1` at edge k+10T+1.

**Acceptance**: as stated. The earliest next accept edge is therefore k+10T+1, which leaves
exactly one extra idle-high cycle between back-to-back frames.

### UTX-HSK-004 — Ready holds while idle

**Statement**: Once `ready = 1`, it stays 1 at every following edge up to and including the
next accept edge, unless `clear` intervenes.

**Acceptance**: at every edge where no frame is in progress (no accept edge k with the edge
inside k+1 .. k+10T since the last `clear`), `ready = 1`.

### UTX-FRM-001 — Frame waveform

**Statement**: For an accept edge k and no `clear`, at edge k+n for n = 1 .. 10T,
`tx = F[(n-1) div T]`.

**Acceptance**: as stated, for every byte value and every T.

### UTX-FRM-002 — Inputs latched at acceptance

**Statement**: Changes to `data`, `divisor` or `valid` after the accept edge do not alter the
frame in progress.

**Acceptance**: UTX-FRM-001 and UTX-HSK-002/003 hold with `data`, `divisor` and `valid`
unconstrained after the accept edge.
