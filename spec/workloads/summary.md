# Workload study — summary: the minimum ISA and MAC units

Proposal for the owner. **Not requirements.** See `README.md` for the baseline machine B0, the
notation and the identifier scheme.

Five workloads were written as pseudo-assembly against B0: `uart.md`, `spi.md`, `i2c.md`,
`swd.md`, `usb_ls.md`. This file collects what they could not express into one instruction set
and one set of MAC-assist units, and records the questions only the owner can settle.

## Result in one paragraph

The five programs need **eight instructions** in a 16-bit word, **two scratch registers**, two
32-bit shift registers, side-set, pin direction control, and a per-sequencer tick divider. That
ISA is close enough to the RP2040 PIO's that the honest statement is: *the workloads re-derive
PIO*. Golem's value is entirely in the four things PIO has not got, and every one of them was
forced by a workload rather than assumed: a **MAC chain that sits in the clock-enable path as
well as the data path** (USB bit stuffing), a **deadline timer that can break a blocked `WAIT`**
(I2C clock stretching), a **conditional-branch pin index carried in the instruction** (I2C's
simultaneous `WAIT` on SCL and `JMP` on SDA), and a **fractional tick divider with edge resync**
(UART RX and USB RX). The tightest deadline in the set is USB low speed's 2-to-7.5-bit-time
response window — 64 to 240 cycles at 48 MHz — and it is met with 4.75 bit times of margin only
because the CRC residue check is a one-tick branch on a hardware flag.

## Deadlines

| Workload | Tightest deadline | At 48 MHz | Imposed by |
|----------|-------------------|-----------|------------|
| **USB LS** | response 2–7.5 bit times after EOP | **64–240 cycles** | USB 2.0 §7.1.18 |
| UART RX  | epilogue after the stop-bit sample < 0.5 bit time | 8 cycles @3 Mbaud (3 of 4 ticks used) | back-to-back frames |
| SPI      | MISO round trip before the sample | 3 cycles (fixed) | our own pad + synchroniser |
| SWD      | SWDIO round trip; turnaround < 1 SWCLK period | 3 cycles (fixed) | our own pad + synchroniser |
| I2C      | `tVD;DAT` ≤ 0.9 µs; stretch wait unbounded | 43 cycles; ∞ | UM10204 |

USB is the only workload with a deadline the *bus* imposes. SPI and SWD own their clocks; I2C
may stretch its own; UART has no handshake. This confirms PLAN.md's split: only USB needs the
under-10 µs path on chip, and it needs it by a factor of 40 over an SPI round trip to the host.

## The instruction set

16-bit word: `[15:13] opcode`, `[12:8] delay / side-set`, `[7:0] operands`. Eight opcodes, eight
operand bits each — the encoding is full, with no spare opcode.

| Op | Mnemonic | Operands (8 bits) | First asked for by |
|----|----------|-------------------|---------------------|
| 0 | `JMP cond, addr` | `cond[2:0]`, `addr[4:0]` | B0 |
| 1 | `WAIT pol, src, idx` | `pol`, `src[1:0]`, `idx[4:0]` | UART RX |
| 2 | `IN src, n` | `src[2:0]`, `n[4:0]` (1..32) | B0 |
| 3 | `OUT dst, n` | `dst[2:0]`, `n[4:0]` (1..32) | B0 |
| 4 | `PUSH`/`PULL` | `dir`, `iffull`/`ifempty`, `block` | B0 |
| 5 | `MOV dst, op src` | `dst[2:0]`, `op[1:0]`, `src[2:0]` | I2C |
| 6 | `IRQ set/clear i` | `clear`, `wait`, `i[2:0]` | UART RX |
| 7 | `SET dst, imm` | `dst[2:0]`, `imm[4:0]` | B0 |

**`JMP` conditions.** `cond[2:0]` gives eight encodings; the five workloads use seven.

| Condition | Meaning | UART | SPI | I2C | SWD | USB |
|-----------|---------|------|-----|-----|-----|-----|
| `always`  | —       | ✓ | ✓ | ✓ | ✓ | ✓ |
| `x--`     | branch while X != 0, post-decrement | ✓ | ✓ | ✓ | ✓ | ✓ |
| `!y`      | branch if Y == 0 | | | | | ✓ |
| `x!=y`    | branch if X != Y | | | (multi-master) | ✓ | ✓ |
| `!osre`   | branch while the OSR is not empty | | ✓ | | | ✓ |
| `pin`     | branch if pin `i` == `pol` | ✓ | | ✓ | | |
| `macflag` | branch if MAC flag `i` == `pol` | | | | ✓ | ✓ |
| `!x`      | branch if X == 0 | | | | | |

`!x` fills the eighth encoding for symmetry with `!y`; no program needed it, and it costs
nothing because the register mux is already there. `y--` did not make the cut: Y is only ever a
compare operand, a zero test and a holding register.

**Index field.** `JMP pin` and `JMP macflag` take `{pol, i[2:0]}` from the delay/side-set field
and therefore carry **neither a delay nor a side-set**. Both polarities are needed — USB's
receive loop is `in pins, 1 [6]` followed by `jmp !macflag EOP, rx_bit`, and inverting it would
cost a second instruction in a loop with no spare tick. Every conditional branch in the five
programs complies with the no-delay, no-side-set rule. The alternative — a single configured
"JMP pin" register, as on PIO — is ruled out by `GAP-I2C-003`, where `WAIT` on SCL and `JMP` on
SDA are four ticks apart.

**`SET` / `OUT` destinations**: `pins`, `pindirs`, `x`, `y`, `null`, `maccfg`.
`SET maccfg, imm` writes five MAC control bits: `{reset, crc_en, stuff_en, coder_en, dir}`.
**`IN` sources**: `pins`, `x`, `y`, `null`.
**`MOV`**: dst ∈ {`pins`, `pindirs`, `x`, `y`, `isr`, `osr`}, src ∈ {`pins`, `x`, `y`, `isr`,
`osr`, `crc`, `null`}, op ∈ {none, invert, bit-reverse}. Invert is I2C's open-drain encoding and
USB's complemented CRC; bit-reverse is the LSB-first/MSB-first mismatch between SWD and USB on
one side and I2C and SPI on the other.
**`WAIT` sources**: `pin`, `irq`, `macflag`.

### State

- `PC`, 5 bits — 32 instruction words per sequencer (see `Q-002`).
- `X`, `Y`, 32-bit scratch. Two is enough for all five; USB needed a third only in the
  software-only variant that the MAC units replace.
- `OSR`, `ISR`, 32-bit, each with a shift direction, a shift counter and an autopull/autopush
  threshold. Thresholds are required: USB packets are longer than one FIFO word and the inner
  loop has no room for an explicit `PULL`.
- TX and RX FIFOs, 4 words each, shared with the host over the SPI link.
- No ALU, no data memory, no stack, no indirect or computed branches. None of the five needed
  them.

### Pin configuration (per sequencer, not instructions)

`OUT`, `SET`, `IN` and side-set each have a **base** and a **width** into the pin array
(1–2 pins is enough for all five; JTAG's `out pins, 2` and USB's `{DP, DM}` are the only
multi-pin groups). Per pin: **open-drain** (output data tied low, direction is the line — I2C),
**output invert** and **input invert** (USB low-speed's J/K swap), and **synchroniser depth 1
or 2** (`GAP-SPI-002`). A programmable base plus a width is a barrel shifter, not an 8×8
crossbar; nothing in the five workloads needs arbitrary pin permutation.

## The MAC-assist units

| ID | Unit | UART | SPI | I2C | SWD | USB | Later |
|----|------|------|-----|-----|-----|-----|-------|
| `MAC-CRC-001` | LFSR/CRC: programmable polynomial, init, in/out bit reflection, output complement, residue-match flag | parity (8E1/8O1) | — | — | **odd parity, `x+1`** | **CRC5, CRC16** | CRC32 (`Q-003`) |
| `MAC-STF-001` | bit stuffer/unstuffer, programmable run length, **stalls the sequencer's tick for one bit time** | — | — | — | — | **6-of-1 stuffing** | HDLC, CAN (5) |
| `MAC-COD-001` | line coder: NRZI encode/decode, polarity bit | — | — | — | — | **NRZI** | Manchester (10BASE-T) |
| `MAC-CLK-001` | tick generator: fractional (16.8) divider + edge resync input | **bit period, RX resync** | — | divider only | divider only | **bit clock + resync** | 10BASE-T |
| `MAC-CLK-002` | SOP/EOP detector: declares the bit clock locked, flags SE0 ≥ 2 bit times | — | — | — | — | **SYNC, EOP** | — |
| `MAC-TMR-001` | deadline timer: 24-bit down-counter, on expiry forces the PC to a trap address and raises an IRQ; **must break a blocked `WAIT`, `PUSH` or `PULL`** | — | — | **25 ms stretch timeout** | — | reset/suspend timing | — |

Six units. Three of them (`MAC-CRC-001`, `MAC-STF-001`, `MAC-COD-001`) form the **MAC chain**
that sits between the shift registers and the pins, in this order:

```
TX:  OSR   ->  CRC tap  ->  stuffer  ->  coder  ->  pins
RX:  pins  ->  coder    ->  unstuffer ->  CRC   ->  ISR
```

The order is not free: USB's CRC is computed over un-stuffed data and NRZI is applied after
stuffing. Each unit has a bypass so the other four workloads see a wire.

### The one structural departure

`MAC-STF-001` must **gate the sequencer's tick enable**. A stuffed bit occupies a bit time on
the wire and consumes no bit from the OSR; a cycle-exact sequencer cannot skip a loop iteration
without a branch, and a branch costs its longest arm on every bit. Letting the stuffer stop the
sequencer's notion of time for one bit time keeps the program unchanged and unaware. This makes
the MAC chain part of the clock-enable path, not only the data path, and it is the single place
where Golem must be built differently from a PIO-shaped machine. Its interaction with `WAIT`
and with `MAC-TMR-001` (which counts *real* time) is `Q-009`.

## Program sizes and sequencer count

| Program  | Words | Sequencers |
|----------|-------|------------|
| UART TX  | 7     | 1 |
| UART RX  | 8     | 1 |
| SPI master | 9   | 1 (2 for the 24 MHz split variant) |
| I2C master | 20  | 1 |
| SWD read | 28    | 1 |
| USB LS TX | 24   | 1 |
| USB LS RX | 9    | 1 |

**32 instruction words per sequencer** covers every program and matches the 5-bit `JMP` address,
but only just: SWD is 28 words and a write transfer will be longer still, so 32 is a ceiling the
must tier already touches. **Four sequencers** is the minimum that runs the flagship
(USB needs two, concurrently, with a one-bit-time handoff) alongside a second protocol.

4 × 32 × 16 bits = **2048 bits of instruction memory**. As a rough check against the 6×4 tile
budget: 24 Tiny Tapeout tiles are about 433 000 µm² of tile area, and at a realistic utilisation
maybe 250 000 µm² is usable; an IHP sg13g2 flip-flop is of order 20–30 µm², so a flop-based
instruction memory is 40 000–60 000 µm² before read multiplexing — roughly a fifth of the
budget for instruction storage alone. **These are order-of-magnitude figures from public cell
sizes, not synthesis results**; the designer must confirm them, and the choice between a flop
array, a latch array and a shared memory is `Q-002`.

## Pin budget

Tiny Tapeout gives 8 dedicated inputs (`ui`), 8 dedicated outputs (`uo`) and 8 bidirectional
(`uio`).

| Workload | in | out | bidir | total |
|----------|----|-----|-------|-------|
| UART (full duplex) | 1 | 1 | — | 2 (4 with RTS/CTS) |
| SPI master | 1 | 3 | — | 4 (+1 per extra CS) |
| I2C master | — | — | 2 | 2 |
| SWD | — | 1 | 1 | 2 |
| JTAG | 1 | 3 | — | 4 |
| USB LS | — | 1 | 2 | 3 |

Proposed allocation: the host SPI link on `ui[2:0]` (SCK, MOSI, CSn) and `uo[0]` (MISO); the
eight `uio` as the protocol pin array; `ui[7:3]` and `uo[7:1]` as input-only and output-only
protocol pins. Worst case if every bidirectional protocol were active at once is 5 of the 8
`uio`, so the pin array is not the binding constraint — the instruction memory is.

## Questions for the owner

**`Q-001` — clock frequency: 48 MHz or 50 MHz?**
`info.yaml` says 50 MHz. USB low speed needs 1.5 Mbit/s with no jitter, and 50 MHz gives 33.33
cycles per bit while 48 MHz gives exactly 32. A fractional divider at 50 MHz places edges ±1.5%
of a bit time from nominal, which is the entire low-speed tolerance before the host's own error.
Every other workload is indifferent. If the answer is 48 MHz, `info.yaml` and `spec/top.md`
change and the UART gate block's divisor changes with them — designer work, filed as an
`agent:designer` issue once this study is accepted. See `usb_ls.md` `GAP-USB-001`.

**`Q-002` — instruction memory: how many sequencers, how many words, built from what?**
32 words × 4 sequencers is what the programs need. The rough area arithmetic above puts a
flop-based memory at a fifth of the tile budget. Fewer, deeper sequencers, or a latch array, or
one shared memory with per-sequencer program counters, all trade differently. A designer answer,
but the count is a spec-visible parameter.

**`Q-003` — is `MAC-CRC-001` 16 bits or 32?**
16 covers the must and should tiers (CRC5, CRC16, parity). 10BASE-T's CRC32 needs 32 and roughly
doubles the unit. Tier "could" in PLAN.md, deadline 2027-01-18.

**`Q-004` — what is the real pad-to-`IN` latency?**
The studies assume `L_out` = 1 cycle and `L_in` = 2 cycles, so `L_rt` = 3. This number sets the
maximum SCK and SWCLK directly (10 MHz at `L_rt` = 3, 12 MHz at 2) and appears in three of the
five programs. Only the designer can confirm it, and it should become a spec constant once
known.

**`Q-005` — do two sequencers need to start with a fixed sub-word offset?**
`spi.md`'s 24 MHz split variant needs sequencer B released exactly `L_rt` cycles after A. `IRQ`
gives the handoff but not the alignment. Only SPI wants it, and only for the fast variant;
recorded rather than proposed.

**`Q-006` — is I2C single-master enough for v1?**
Multi-master arbitration needs a per-bit compare of the sampled SDA against the transmitted bit
and a same-bit bus release. Affordable at 10 ticks per bit, but it needs the transmitted bit
kept in a register or a hardware mismatch flag. The study assumes single master.

**`Q-007` — who verifies SWD against a real target?**
`swd.md`'s clock alignment around the two turnarounds is sized for the ISA question and has not
been checked against ADIv5 bit by bit. It will need a real target or a trusted model before it
becomes a requirement.

**`Q-008` — confirm that SWD `WAIT`/`FAULT` retries stay on the host.**
Retrying on chip would need the OSR rewound. SWD has no deadline, so the host can retry for
free; recorded so a later reader does not add an OSR rewind for SWD's sake.

**`Q-009` — what does the stuffer's tick stall do to `WAIT` and to `MAC-TMR-001`?**
`MAC-STF-001` stops the sequencer's tick for one bit time. `MAC-TMR-001` counts real time and
must not stop with it, or an I2C timeout would be wrong; a blocked `WAIT` must not be extended
in a way that breaks the USB response window. This is the first place two proposed units
interact and it needs an explicit rule before either is built.

## What none of the five needed

Worth recording, because each is a thing a general-purpose core would have and every one of them
would cost tiles: add, subtract, AND, OR, XOR or shift as *instructions* (the only arithmetic is
compare-against-zero, compare-against-Y and post-decrement); data memory; a stack or
subroutines; indirect or computed branches; PIO's `MOV EXEC`; a second instruction word length;
DMA. The bit-level work that a CPU would do with XOR is exactly the work the MAC chain does, at
one gate per bit instead of one instruction per bit — which is the thesis in PLAN.md, checked
here for the first time rather than asserted.
