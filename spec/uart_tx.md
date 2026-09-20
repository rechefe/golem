# UART transmitter (`UTX`)

Status: **v1, gate block.** Temporary fixed-function block used to prove the Hardcaml → formal →
GDS flow end to end. It will be replaced by a sequencer program once the sequencer exists.

Transmits one byte as an 8N1 frame (1 start bit, 8 data bits LSB first, 1 stop bit, no parity)
with a programmable bit period.

Checks in this file are written in emet (`emet.md`); the two requirements that keep a prose
**Acceptance** line are `UTX-RST-002` and `UTX-FRM-002`, and each says below why it must. Both
are about the harness rather than the block. **Note** paragraphs are explanatory and never
checks, as `README.md` defines them.

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

### UTX-RST-002 — Traces begin in reset

**Statement**: In every trace presented to a checker of this block, `clear = 1` is sampled at
edge 1 and at edge 2. A harness may hold `clear` for longer; the anchor is those two edges.

**Acceptance**: every harness for this block constrains `clear` so, and therefore rejects a
substitute design that holds `ready = 0` and `tx = 0` at edges 1, 2 and 3 whatever its inputs
and follows the rest of this file from edge 4 on. A harness under which that design passes has
not anchored the trace and does not check this block.

**This requirement has no emet block, and must not be given one.** It constrains the traces a
harness may present, not the behaviour of the block within a trace, and emet has no `assume`
(`emet.md`, "What emet is, and what it is not"). `README.md`, "Initial-state anchor", says why
every block spec with emet properties carries a requirement of this shape.

**Note**: *edge 2*, and not edge 1 alone, is what emet needs. No firing happens at edge 1
(`emet.md`, "The execution model"), so `clear` at edge 1 alone triggers nothing and UTX-RST-001
never fires. With `clear` at edges 1 and 2, UTX-RST-001 fires at edge 2 and its check lands at
the first edge after the last edge of the initial `clear` run — edge 3 if the harness releases
`clear` there.

**Note**: this is what gives UTX-HSK-004 a base case, and with it the whole file. UTX-RST-001
puts `ready = 1` at the first edge after the initial `clear` run; UTX-HSK-004 arms there and
pins `ready` to the next accept edge; UTX-HSK-002 and UTX-HSK-003 carry it across a frame and
hand it back at k+10T+1, where UTX-HSK-004 re-arms. Every edge after the initial `clear` run is
covered, so "a design that holds `ready = 0` until the first `clear`" — which satisfies every
emet property in this file on its own — is rejected by UTX-RST-001 instead.

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
  cover back_to_back: $t == $n && valid;
}
```

**Note**: the earliest next accept edge is therefore k+10T+1, which leaves exactly one extra
idle-high cycle between back-to-back frames. The firing retires at its check edge, so that
back-to-back accept edge is not an overlap. `cover back_to_back` asks for that trace: `$t ==
$n` is the check edge k+10T+1, where this property asserts `ready`, and `valid` there makes it
an accept edge. It asserts nothing; it is the witness that the retire-at-the-check-edge rule
leaves back-to-back frames reachable.

### UTX-HSK-004 — Ready holds while idle

**Statement**: Once `ready = 1`, it stays 1 at every following edge up to and including the
next accept edge, unless `clear` intervenes.

```emet
property UTX-HSK-004 {
  stable ready after (ready && !accept && !clear) until accept;
}
```

**Note**: each idle edge re-arms the firing, so `ready` is pinned high from wherever it last
went high through the next accept edge. UTX-RST-001 anchors it at the first edge after a
`clear` edge and UTX-HSK-003 restores it at k+10T+1, where this property re-arms. So from any
edge at which `ready = 1`, every later edge at which no frame is in progress is covered.

**Note**: *from any edge at which `ready = 1`* is the whole of the claim, so this property is
only as strong as the guarantee that such an edge exists. Every trigger in this file requires
`ready = 1`, directly or through `accept`; UTX-RST-001 supplies one only at an edge that
follows a `clear` edge, and emet has no `assume` with which to require that a trace contains
one (`emet.md`, "Limitations of v0"). The edge is supplied instead by UTX-RST-002, which puts
`clear` at edges 1 and 2 of every trace: UTX-RST-001 fires at edge 2, so `ready = 1` at the
first edge after the initial `clear` run — edge 3 if the harness releases `clear` there. That
anchor is an obligation on the harness, stated as a requirement so that it is traceable and
cannot be dropped silently; `README.md`, "Initial-state anchor", says why it lives there rather
than in emet. Carrying it forward when `formal/uart_tx_props.v` retires is issue #23 — note
that UTX-RST-002 asks for two edges of `clear`, where that harness assumes one
(`formal/uart_tx_props.v:32`), because it asserts `ready` directly and does not need a firing.

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
