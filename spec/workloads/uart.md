# Workload: UART transmitter and receiver (8N1)

Proposal, not requirements. See `README.md` for the baseline machine B0 and the notation.

One start bit (0), 8 data bits LSB first, no parity, one stop bit (1). Line idle is high.
Target baud rates: 115200 default, up to 3 Mbaud.

## Pins

| Name  | Dir | Count | Notes                                                       |
|-------|-----|-------|--------------------------------------------------------------|
| `TX`  | out | 1     | Driven level. Idle high.                                      |
| `RX`  | in  | 1     | Sampled level. Needs a `WAIT` condition and a `JMP` condition. |

Optional and not studied here: `RTS`/`CTS` (2 more pins, no new sequencer feature — `CTS` is
another `WAIT` source, `RTS` another driven level).

Total for a full-duplex port: **2 pins** (4 with hardware flow control). TX and RX are separate
programs and, because both must be armed at all times, **separate sequencers**.

## Tick length

At 8 ticks per bit the tick is `f_clk / (8 * baud)` clock cycles:

| Baud    | Cycles per bit @48 MHz | Cycles per tick | Exact? |
|---------|------------------------|-----------------|--------|
| 115200  | 416.67                 | 52.08           | no — needs a fractional divider |
| 1000000 | 48                     | 6               | yes    |
| 3000000 | 16                     | 2               | yes    |

8N1 tolerates roughly ±2% of accumulated error over a 10-bit frame, so an integer tick is
acceptable at 115200 (52 cycles gives 115385 baud, +0.16%). A fractional divider removes even
that. See `GAP-UART-001`.

## Program: UART TX

```
.program uart_tx              ; 1 bit = 8 ticks
; OUT/SET pin group: TX (1 pin).  Shift direction: right (LSB first).

tx_loop:
    pull  block                   ; OSR <- TX FIFO; stalls with TX at its last level (idle 1)
    set   pins, 0                 ; start bit begins here          |
    set   x, 7             [6]    ; 7 ticks; start bit = 8 ticks   |  [GAP-UART-002]
tx_bit:
    out   pins, 1          [6]    ; 7 ticks: data bit, LSB first
    jmp   x--, tx_bit             ; 1 tick   -> 8 ticks per data bit   [GAP-UART-002]
    set   pins, 1          [7]    ; stop bit, 8 ticks
    jmp   tx_loop                 ; TX stays high; idle
```

7 instruction words. Frame length 8 + 64 + 8 = 80 ticks = 10 bit times exactly. Between frames
the program spends at least 2 further ticks in `jmp`/`pull` with TX high, which only lengthens
the stop bit and is always legal.

**Cycle accounting.** Start bit: `set pins, 0` (1) + `set x, 7 [6]` (7) = 8. Each data bit:
`out pins, 1 [6]` (7) + `jmp x--` (1) = 8, and the eighth iteration costs the same 8 because the
not-taken `jmp x--` still occupies its tick. Stop bit: 8.

## Program: UART RX

```
.program uart_rx              ; 1 bit = 8 ticks
; IN pin group: RX (1 pin).  WAIT pin = RX.  JMP pin = RX.  Shift direction: right.

rx_loop:
    wait  0, pin RX               ; tick 0:  falling edge of the start bit    [GAP-UART-003]
    set   x, 7             [10]   ; ticks 1-11
rx_bit:
    in    pins, 1          [6]    ; ticks 12+8k .. 18+8k: sample bit k at its centre
    jmp   x--, rx_bit             ; tick 19+8k
    jmp   pin RX, rx_good         ; tick 76: centre of the stop bit           [GAP-UART-004]
    irq   set 0                   ; tick 77: framing error                    [GAP-UART-005]
    jmp   rx_loop                 ; tick 78
rx_good:
    push  block                   ; tick 77
    jmp   rx_loop                 ; tick 78
```

9 instruction words.

**Sample alignment.** Tick 0 is the tick at which `WAIT` observes RX low. Bit *k* is sampled at
tick `12 + 8k`, i.e. at `1.5 + k` bit times after the edge — the centre of each data bit. The
stop bit is sampled at tick 76 = 9.5 bit times, which is exactly the next free tick after the
loop; no filler instruction is needed, and none would fit.

**Edge-detection error.** `WAIT` resolves on a tick boundary, so the detected edge is up to one
tick (1/8 bit) late, on top of the input synchroniser delay. At 8 ticks per bit the total is
well inside the ±0.5 bit sampling margin, but it is the reason the tick must be a *fraction* of
a bit rather than a whole bit.

## Tightest timing deadline

Neither direction has a response deadline: UART has no handshake the line imposes. The binding
constraint is on the receiver's epilogue.

> **RX epilogue: 3 ticks used of 4 available (0.375 of 0.5 bit time).**

After sampling the stop bit at tick 76, the program executes `jmp pin`, `push` and `jmp` and
re-arms `WAIT` at tick 79. The earliest legal next start edge is tick 80 (the stop bit ends at
10 bit times). The margin is **1 tick = 1/8 bit time**, which at 3 Mbaud is **2 clock cycles**.
Any instruction added to the RX epilogue drops back-to-back frames.

Consequences: RX cannot also compute parity, check a FIFO level or drive `RTS` in-line; parity
must come from a MAC unit that updates as bits are shifted (`MAC-CRC-001`), and flow control
must live in another sequencer or on the host.

## Gaps against B0

**`GAP-UART-001` — the bit period does not fit the delay field.**
115200 baud at 48 MHz is 417 cycles per bit; B0's delay field reaches 15 ticks and one tick is
one cycle. Expressing the period by looping burns a scratch register and instruction words in
the inner loop, where UART RX has no room.
*Proposed*: a per-sequencer **tick divider**, fractional (16.8 fixed point, as PIO), generating
the sequencer's clock enable. → `MAC-CLK-001`.

**`GAP-UART-002` — no scratch register and no counted loop.**
Both programs need to repeat a one-instruction body exactly 8 times. Unrolling costs 8 words in
TX and 8 in RX, and does not generalise to USB's 32-bit fields.
*Proposed*: scratch registers `X`, `Y`; `SET x, imm`; `JMP x--, addr` (branch while non-zero,
post-decrement). → `ISA-SET-001`, `ISA-JMP-001`.

**`GAP-UART-003` — no way to block on a pin.**
RX must start on the falling edge of the start bit with tick-accurate alignment. Polling with
`IN` plus a conditional branch costs at least 2 ticks per poll and quantises the detected edge
to 2 ticks.
*Proposed*: `WAIT pol, pin idx` — stall until pin `idx` reads `pol`. → `ISA-WAIT-001`.

**`GAP-UART-004` — no conditional branch on a pin.**
The stop-bit check is a branch on a pin level at one exact tick.
*Proposed*: `JMP pin idx, addr`. The pin is **indexed by the instruction**, not fixed in
configuration; see `GAP-I2C-003` for the workload that forces this. → `ISA-JMP-002`.

**`GAP-UART-005` — no way to report an error.**
A framing error has no data to push and must not stall the RX FIFO.
*Proposed*: `IRQ set/clear i` with host-visible flags, also usable for sequencer-to-sequencer
handoff. → `ISA-IRQ-001`.

**`GAP-UART-006` — parity cannot be computed in-line.** (Only if 8E1/8O1 is wanted; 8N1 does
not need it.) TX would need to accumulate the XOR of 8 bits and append it; RX would need the
same and a compare, in an epilogue that has 1 tick of slack.
*Proposed*: cover it with the CRC/LFSR MAC unit configured with the polynomial `x + 1`.
→ `MAC-CRC-001`.

## What UART did *not* need

No arithmetic, no memory, no indirect addressing, no side-set, no pin direction control, no
compare-and-branch. UART alone justifies a four-instruction machine plus a divider; it is the
right shape for the Hardcaml gate block and a poor guide to the rest of the ISA.
