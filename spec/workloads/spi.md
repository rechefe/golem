# Workload: SPI master (mode 0)

Proposal, not requirements. See `README.md` for the baseline machine B0 and the notation.

CPOL = 0, CPHA = 0: SCK idles low, the master changes MOSI on the falling edge, both ends
sample on the rising edge. Full duplex. Word size 8 or 32 bits, CS asserted across a multi-word
transfer.

## Pins

| Name   | Dir | Count | Notes                                              |
|--------|-----|-------|-----------------------------------------------------|
| `SCK`  | out | 1     | Best driven as side-set: it must change in the same tick as MOSI. |
| `MOSI` | out | 1     | `OUT` group.                                        |
| `MISO` | in  | 1     | `IN` group.                                         |
| `CSn`  | out | 1     | `SET` group. One per slave.                         |

**4 pins** for one slave, +1 per extra chip select.

## The round trip is the whole story

SPI is the first workload where the sequencer's own I/O latency, not the protocol, sets the
speed limit. Model, to be confirmed by the designer (`Q-004`):

- `L_out` = 1 cycle — a value written at cycle *c* is on the pad during cycle *c+1* (output
  register).
- `L_in` = 2 cycles — a pad value during cycle *c* is readable by `IN` at cycle *c+2*
  (two-stage metastability synchroniser).
- `L_rt` = `L_out + L_in` = **3 cycles**, before the slave's own clock-to-out.

So the `IN` that captures the slave's response to an SCK rising edge driven at cycle *c* must
execute no earlier than cycle *c+3*. In mode 0 the slave holds each bit from one falling edge to
the next, so the sampling *window* is a whole SCK period wide; the constraint is that the bit
period must be long enough for the 3-cycle shift to still land inside the right bit's window.

## Program: SPI master, mode 0

```
.program spi_master           ; tick = 1 clock cycle
.side_set 1                   ; SCK
; OUT group = MOSI, IN group = MISO, SET group = CSn.  Shift direction: left (MSB first).

spi_word:
    pull  block        side 0         ; OSR <- word
    set   x, 7         side 0         ; 8 bits
    set   pins, 0      side 0  [1]    ; CSn low; tCSS
spi_bit:
    out   pins, 1      side 0  [1]    ; cycles 0-1: MOSI <- bit n, SCK low
    nop                side 1         ; cycle 2:    SCK rises
    in    pins, 1      side 1         ; cycle 3:    sample MISO = bit n  (L_rt = 3)
    jmp   x--, spi_bit side 1         ; cycle 4:    SCK high
    push  block        side 0         ; received word -> RX FIFO
    set   pins, 1      side 0         ; CSn high
    jmp   spi_word     side 0
```

9 instruction words. **5 cycles per bit → SCK = 10 MHz at 48 MHz** (low 2 cycles, high 3).

Multi-word transfers with CS held low need the transfer length in the program, which means
pulling a header word into a counter — see `GAP-SPI-003`.

## Faster variants

| Variant                                                  | Cycles/bit | SCK @48 MHz |
|----------------------------------------------------------|------------|-------------|
| As listed, one sequencer                                  | 5          | 10 MHz      |
| One-stage synchroniser on the MISO group (`L_rt` = 2)     | 4          | 12 MHz      |
| TX and RX split across two sequencers, RX started 3 cycles later | 2   | 24 MHz      |

The split variant is worth spelling out, because it is the first evidence that "sequencer count
is a parameter" buys throughput and not just more protocols:

```
; sequencer A (drive)                    ; sequencer B (sample), released 3 cycles later
a_bit:                                   b_bit:
    out pins, 1   side 0                     nop
    jmp !osre, a_bit side 1                  in  pins, 1
                                             jmp x--, b_bit    ; 2 cycles, aligned to A's SCK
```

B must start exactly `L_rt` cycles after A and stay locked to it for the whole word. `IRQ` gives
the handoff but not the sub-cycle alignment; a "start together with offset *k*" mechanism is
listed as `Q-005` rather than proposed, because only SPI wants it so far.

## Tightest timing deadline

SPI imposes no response deadline on the master — it owns the clock and can stop it between any
two bits. The tight number is internal:

> **MISO round trip: 3 clock cycles (62.5 ns at 48 MHz) between driving SCK high and being able
> to read the answer.**

This is the deadline that decides the maximum SCK, and it is fixed by the pad register and the
input synchroniser, not by the program. Every workload that reads a pin it has just clocked
(SPI, SWD, JTAG, I2C's ACK bit) pays it.

Slave-side constraints that the program must respect but that are loose at these rates: tCSS
(CS setup, typically 10 ns = 1 cycle, covered by `[1]` on the `set pins, 0`) and tCSH.

## Gaps against B0

**`GAP-SPI-001` — SCK cannot be driven in the same tick as MOSI.**
With `SET`/`OUT` as the only way to move a pin, toggling SCK costs a separate instruction per
edge: 4 instructions per bit minimum on top of `OUT`/`IN`, and the SCK edge lands one tick away
from the MOSI change, violating mode 0 setup.
*Proposed*: **side-set** — a per-instruction field driving 1-2 pins in the instruction's own
tick, stealing bits from the delay field. → `ISA-SIDE-001`.

**`GAP-SPI-002` — the input round trip is invisible to the program.**
Nothing in B0 or in the listing above tells the sequencer that `IN` reads a 3-cycle-old pin. The
program has to be written around it by hand, and the correct offset changes if the designer
changes the synchroniser depth.
*Proposed*, in order of cost: (a) a per-pin-group configuration field selecting a **1- or
2-stage synchroniser** (1 stage is defensible for a pin whose source is clocked by our own SCK);
(b) the split-sequencer variant above. Not proposed: an `OUT`+`IN` fused instruction — it fixes
the offset in silicon at the wrong value for other rates. → `ISA-PINCFG-001`, `Q-004`.

**`GAP-SPI-003` — a word count cannot be loaded from the FIFO.**
Holding CS low across *n* words needs *n* from the host. B0 can only move FIFO data to pins.
*Proposed*: `OUT x, n` / `OUT y, n` — `OUT` must be able to target a scratch register, not only
pins. → `ISA-OUT-001`.

**`GAP-SPI-004` — no way to hold CS across a program restart.**
`SET pins` writes the whole group, so CS and MOSI cannot share one `SET` group without clobber.
*Proposed*: separate `OUT` and `SET` pin bases, each with its own width (PIO does this), so
`SET pins` reaches CS only. Configuration, not an instruction. → `ISA-PINCFG-001`.

## What SPI did *not* need

No MAC-assist unit of any kind: no CRC, no line coding, no stuffing. SPI is pure shift-and-clock
and is fully covered by the ISA. It contributes side-set, `OUT` to a register, and the pin
configuration fields — and it sets the realistic ceiling on every clocked-read protocol.
