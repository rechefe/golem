# UART transmitter (`UTX`)

Status: **v1, gate block.** Temporary fixed-function block used to prove the Hardcaml → formal →
GDS flow end to end. It will be replaced by a sequencer program once the sequencer exists.

Transmits one byte as an 8N1 frame (1 start bit, 8 data bits LSB first, 1 stop bit, no parity)
with a programmable bit period.

Checks in this file are written in emet (`emet.md`); `UTX-FRM-002` is the one requirement that
keeps a prose **Acceptance** line, and says below why it must. A **Note** paragraph under a
requirement explains how to read its check; it is never itself a check.

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

```emet
unit UTX golem_uart_tx {
  clock clock;
  reset clear;

  in  clear   1;
  in  data    8;
  in  valid   1;
  in  divisor 16;
  out tx      1;
  out ready   1;

  // The accept edge, from "Definitions" below.
  let accept = valid && ready && !clear;
}
```

One `in`/`out` line per row of the table above, in the table's order; `clock` is the `clock`
row. The table and this block must agree — a mismatch is a spec bug.

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

```emet
property UTX-RST-001.tx    { at 1 after clear: tx; }
property UTX-RST-001.ready { at 1 after clear: ready; }
```

**Note**: the trigger is the reset itself, and a firing is cancelled when `clear` is still
true at the next edge, so the check lands on the first edge after the *last* edge of a run of
`clear` — which is what the statement means by "the first edge after".

### UTX-IDL-001 — Idle line is high

**Statement**: Whenever `ready = 1`, `tx = 1`.

```emet
property UTX-IDL-001 { invariant ready -> tx; }
```

### UTX-HSK-001 — Single acceptance

**Statement**: A byte is accepted only at an accept edge. `valid` while `ready = 0` has no
effect and is not queued.

```emet
property UTX-HSK-001 {
  stable tx after (ready && !accept && !clear) until accept;
}
```

**Note**: `tx` is pinned to its idle value from every idle edge through the next accept edge
inclusive, so the start bit can first appear one edge after an accept edge and nowhere else.
An unqueued `valid` is the same claim read at the end of a frame: at the edge where `ready`
returns with `valid = 0`, `tx` is pinned high until a real accept edge arrives.

### UTX-HSK-002 — Busy during a frame

**Statement**: For an accept edge k and no `clear`, `ready = 0` at edges k+1 through k+10T.

```emet
property UTX-HSK-002 {
  sample T = divisor + 1;
  hold 10 * T after accept: !ready;
  cover shortest_bit: $t == $n && T == 1;
}
```

### UTX-HSK-003 — Ready after the frame

**Statement**: For an accept edge k and no `clear`, `ready = 1` at edge k+10T+1.

```emet
property UTX-HSK-003 {
  sample T = divisor + 1;
  at 10 * T + 1 after accept: ready;
}
```

**Note**: the earliest next accept edge is therefore k+10T+1, which leaves exactly one extra
idle-high cycle between back-to-back frames. The firing retires at its check edge, so that
back-to-back accept edge is not an overlap.

### UTX-HSK-004 — Ready holds while idle

**Statement**: Once `ready = 1`, it stays 1 at every following edge up to and including the
next accept edge, unless `clear` intervenes.

```emet
property UTX-HSK-004 {
  stable ready after (ready && !accept && !clear) until accept;
}
```

**Note**: each idle edge re-arms the firing, so `ready` is pinned high from wherever it last
went high through the next accept edge. With UTX-RST-001 to anchor it after `clear` and
UTX-HSK-003 to restore it at k+10T+1, this covers every edge at which no frame is in progress.

### UTX-FRM-001 — Frame waveform

**Statement**: For an accept edge k and no `clear`, at edge k+n for n = 1 .. 10T,
`tx = F[(n-1) div T]`.

```emet
property UTX-FRM-001 {
  sample T = divisor + 1;
  sample F = {1'b1, data, 1'b0};      // F[0] start, F[1..8] data LSB first, F[9] stop
  hold 10 * T after accept:
    tx == ($t <= 1*T ? F[0] :
           $t <= 2*T ? F[1] :
           $t <= 3*T ? F[2] :
           $t <= 4*T ? F[3] :
           $t <= 5*T ? F[4] :
           $t <= 6*T ? F[5] :
           $t <= 7*T ? F[6] :
           $t <= 8*T ? F[7] :
           $t <= 9*T ? F[8] :
                       F[9]);
  cover byte_a5: $t == $n && F == 10'b1_1010_0101_0;
  cover clear_midframe: $t > 4*T && clear;
}
```

**Note**: the division is a comparison chain — bit i applies while `i*T < $t <= (i+1)*T` —
because a divider by a runtime value puts an unbounded proof out of reach.

### UTX-FRM-002 — Inputs latched at acceptance

**Statement**: Changes to `data`, `divisor` or `valid` after the accept edge do not alter the
frame in progress.

**Acceptance**: UTX-FRM-001 and UTX-HSK-002/003 hold with `data`, `divisor` and `valid`
unconstrained after the accept edge.

**This requirement has no emet block, and must not be given one.** It is a prohibition on what
a harness may assume, not a property of a trace: the check is the *absence* of a constraint on
`data`, `divisor` and `valid` after the accept edge. emet has no `assume` (`emet.md`,
"What emet is, and what it is not"), so there is nothing to write, and the `sample`s in
UTX-FRM-001 and UTX-HSK-002/003 are the mechanism by which the properties above already carry
it. A block added here could only restate one of those properties, and would then be a second
normative copy of it.
