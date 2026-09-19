# Workload: USB low speed (1.5 Mbit/s), device role

Proposal, not requirements. See `README.md` for the baseline machine B0 and the notation.

USB 2.0 low speed, function (device) role. This is the flagship workload of PLAN.md and the
only one of the five with a hard external response deadline. It is also the only one that
cannot be done by instructions alone at any clock we can reach, and the study below is mostly
the argument for why.

Host role is noted where it differs; the response deadline is the same for both.

## Pins

| Name    | Dir   | Count | Notes                                                    |
|---------|-------|-------|-----------------------------------------------------------|
| `DP`    | bidir | 1     | `pins[0]`. In the `OUT`/`IN`/`SET` group *and* `pindirs`. |
| `DM`    | bidir | 1     | `pins[1]`. Same group.                                    |
| `PUEN`  | out   | 1     | Enables the external 1.5 kΩ pull-up on `DM` (attach/detach). |

**3 pins.** `DP` and `DM` must be adjacent and in the same group: the four line states are a
2-bit symbol that must be driven and released together.

Low-speed line states (note that `J` and `K` are inverted with respect to full speed — a
polarity bit in the pin configuration, not a separate coder):

| State | `DM` | `DP` | `pins[1:0]` | Meaning                          |
|-------|------|------|-------------|-----------------------------------|
| `J`   | 1    | 0    | `0b10`      | idle / differential 1             |
| `K`   | 0    | 1    | `0b01`      | differential 0                    |
| `SE0` | 0    | 0    | `0b00`      | end of packet, bus reset          |
| `SE1` | 1    | 1    | `0b11`      | illegal                           |

## Tick length

| Clock  | Cycles per bit | 8 ticks/bit    | Jitter          |
|--------|----------------|----------------|------------------|
| 48 MHz | 32.00          | tick = 4 cycles | **0**            |
| 50 MHz | 33.33          | tick = 4.17 cycles | ±0.5 cycle per tick, ±1.5% of a bit time |

USB 2.0 Table 7-9 gives the low-speed data rate as 1.50 Mb/s ±1.5%. A fractional divider at
50 MHz has the right *average* rate but places individual edges up to ±1.5% of a bit time away
from nominal, which consumes the whole tolerance before the host's own error is counted. At
48 MHz the divide is exact and the jitter is zero. See `GAP-USB-001` and `Q-001`.

Everything below assumes **48 MHz, 8 ticks per bit, 1 tick = 4 cycles, 1 bit = 32 cycles**.

## Packet structure, and what each field costs

| Field    | Bits | NRZI | Stuffed | In CRC |
|----------|------|------|---------|--------|
| `SYNC`   | 8    | yes  | no      | no     |
| `PID`    | 8    | yes  | yes     | no     |
| payload / token fields | 0..64 | yes | yes | yes |
| `CRC5` (tokens) / `CRC16` (data) | 5 / 16 | yes | yes | — |
| `EOP`    | SE0 ×2 then J ×1 | no | no | no |

- **NRZI**: a transmitted `0` is a line transition, a `1` is no transition.
- **Bit stuffing**: after six consecutive `1`s a `0` is inserted before NRZI encoding and
  removed after NRZI decoding. A stuffed bit consumes a bit time on the wire but carries no
  data, so *the data stream and the line stream run at different rates*.
- **CRC5** = `x⁵ + x² + 1` (0x05), init all-ones, transmitted complemented, residue `0b01100`.
  **CRC16** = `x¹⁶ + x¹⁵ + x² + 1` (0x8005), init all-ones, transmitted complemented, residue
  `0x800D`. Both are computed over the un-stuffed data, so the CRC must tap the stream on the
  data side of the stuffer.

That ordering is a real constraint on the MAC chain:

```
TX:  OSR  ->  CRC tap  ->  bit stuffer  ->  NRZI encoder  ->  DP/DM
RX:  DP/DM ->  NRZI decoder ->  bit unstuffer  ->  CRC  ->  ISR
```

## Why instructions alone cannot do it

Budget: **32 clock cycles per bit**, and — because the sequencer is cycle-exact — *every path
through the per-bit loop must be the same length*, so a branch costs its longest arm on every
bit, not on average.

Per received bit, with the extended ISA the other four workloads asked for (`X`, `Y`, `WAIT`,
`JMP pin`, `JMP x!=y`, `MOV`, side-set) and no MAC units:

| Step                    | Cycles | Status |
|-------------------------|--------|--------|
| sample `DP`/`DM`        | ≥1     | fine |
| NRZI decode (line changed?) | ≥6 | needs the previous symbol in a register *and* a way to shift a computed bit into the ISR; `IN` sources are pins/X/Y/NULL, so each arm of the branch must be balanced |
| bit-unstuff (count six `1`s, drop the next bit) | ≥6 | needs a third scratch register; the drop path and the keep path must be padded to equal length |
| CRC16 update (shift + conditional XOR with 0x8005) | — | **impossible**: no XOR, and no 16-bit register left |
| bit-clock resync on a transition | ≥5 | **impossible**: nothing can reload the delay counter from a register |
| shift into ISR + loop   | ≥2     | fine |

Two of the six steps have no expression at all, and the four that do already exceed half the
budget. Adding an XOR instruction and four more scratch registers would fix the arithmetic and
still leave the resync unexpressible. **The MAC-assist units are not an optimisation for USB;
they are the only way it works.**

Doing the CRC after reception instead is worse: an 8-byte data packet is 72 bits of PID plus
payload, and re-reading and CRC-ing those bits at even 2 cycles per bit is 144 cycles out of a
**240-cycle** response budget (see the deadline below), on top of having to receive them first.

## Program: transmit

```
.program usb_ls_tx            ; 1 bit = 8 ticks, tick = 4 cycles at 48 MHz
; OUT/SET group = {DP, DM} (2 pins) and pindirs.  OSR shift right (LSB first).
; MAC chain: OSR -> CRC tap -> stuffer -> NRZI -> pins.
; The host prepends SYNC to the PID, so the first pulled word is {PID, SYNC}.

tx_packet:
    wait  1, irq 0                     ; the RX sequencer says "respond now"   [GAP-USB-008]
    nop                    [11]        ; inter-packet delay: see the deadline below
    pull  block                        ; {PID, SYNC} plus a CRC flag in bit 0
    out   y, 1                         ; Y = 1 if this packet ends with a CRC  [ISA-OUT-001]
    set   maccfg, TX_RESET             ; NRZI state = J, stuff count = 0, CRC = all ones
    set   pindirs, 0b11                ; drive the bus
    set   x, 7
tx_sync:
    out   pins, 1          [6]         ; SYNC: NRZI on, stuffing and CRC off
    jmp   x--, tx_sync
    set   maccfg, TX_STUFF_CRC         ; stuffing and CRC start at the PID
tx_data:
    out   pins, 1          [6]         ; 8 ticks/bit -- unless the stuffer stalls us [MAC-STF-001]
    jmp   !osre, tx_data               ; autopull refills the OSR from the TX FIFO
    jmp   !y, tx_eop                   ; handshake packets are PID only, no CRC
tx_crc:
    set   maccfg, TX_CRC_OUT           ; stop feeding the CRC; keep stuffing
    mov   osr, ~crc                    ; the CRC is transmitted complemented   [MAC-CRC-001]
    set   x, 15
crc_bit:
    out   pins, 1          [6]
    jmp   x--, crc_bit
tx_eop:
    set   maccfg, MAC_OFF              ; EOP is neither coded nor stuffed
    set   pins, 0b00       [7]         ; SE0, bit 1
    set   pins, 0b00       [7]         ; SE0, bit 2
    set   pins, 0b10       [7]         ; J, 1 bit time
    set   pindirs, 0b00                ; release the bus
    jmp   tx_packet
```

24 instruction words.

The `pull block` sits inside the response window, so the handshake word must already be in the
TX FIFO when the token arrives — the host stages ACK, NAK and STALL ahead of time and the
sequencer only picks one. A `PULL` that stalls here misses the deadline outright.

## Program: receive

```
.program usb_ls_rx            ; 1 bit = 8 ticks
; IN group = {DP, DM}.  ISR shift right (LSB first), autopush at 8.
; MAC chain: pins -> NRZI decode -> unstuffer -> CRC -> ISR.
; The bit clock comes from MAC-CLK-001 and resynchronises on every line transition.

rx_packet:
    set   pindirs, 0b00                ; never drive while receiving
    set   maccfg, RX_RESET
    wait  1, macflag SOP               ; SYNC seen and the bit clock locked   [GAP-USB-005]
rx_bit:
    in    pins, 1          [6]         ; decoded, unstuffed bit -> ISR
    jmp   !macflag EOP, rx_bit         ; SE0 for 2 bit times ends the packet  [GAP-USB-004]
    jmp   !macflag CRCOK, rx_bad       ; residue check, 1 tick                [MAC-CRC-001]
    irq   set 0                        ; hand off to the TX sequencer         [GAP-USB-008]
    jmp   rx_packet
rx_bad:
    irq   set 4                        ; CRC error: stay silent, the host retries
    jmp   rx_packet
```

9 instruction words. Address and endpoint filtering for tokens is an `out x, 7` of the received
address followed by `jmp x!=y` against the assigned address held in `Y` — three more
instructions, comfortably inside the deadline computed below.

## Tightest timing deadline

> **A device must begin its response between 2 and 7.5 bit times after the end of the received
> packet's EOP** (USB 2.0 §7.1.18). At 1.5 Mbit/s that is **1.33 µs to 5.00 µs**, or
> **64 to 240 clock cycles at 48 MHz**.

This is the tightest deadline of all five workloads and the number PLAN.md's "under ~10 µs runs
on chip" rule is really about. The host's response to a device's data packet has the same
window, so the host role does not relax it.

Measured on the programs above, from the tick at which the unstuffer/EOP detector raises `EOP`:

| Step                                     | Ticks |
|------------------------------------------|-------|
| `jmp !macflag EOP` resolves              | 1     |
| `jmp !macflag CRCOK` (residue check)     | 1     |
| `irq set 0`                              | 1     |
| TX's `wait 1, irq 0` releases            | 1     |
| `nop [11]` — the inter-packet pad        | 12    |
| `pull`, `out y`, `set maccfg`, `set pindirs`, `set x` | 5 |
| first `out pins, 1` drives the first SYNC symbol | 1 |
| **total**                                | **22 ticks = 2.75 bit times = 88 cycles** |

Without the pad the path is 10 ticks = 1.25 bit times, which violates the 2-bit-time *minimum*:
the sequencer is too fast, not too slow. With it the response lands at 2.75 bit times, leaving
**4.75 bit times (152 cycles) of margin** against the 7.5-bit-time maximum. That margin is the
whole budget for token decode, address compare and endpoint lookup, and it is only available
because the CRC residue check is a single-tick branch on a hardware flag.

Two further USB timings are far outside anything the sequencer can count and belong to the
deadline timer or the host:

- **Bus reset**: SE0 held for ≥ 10 ms (480 000 cycles).
- **Low-speed keep-alive**: the host sends an EOP every 1 ms (48 000 cycles); a device that
  sees no keep-alive for 3 ms may suspend.

## Gaps against B0

**`GAP-USB-001` — 1.5 Mbit/s is not an integer divide of the current clock.**
50 MHz gives 33.33 cycles per bit. A fractional divider's ±0.5-cycle edge placement is ±1.5% of
a bit time, which is the entire low-speed tolerance. 48 MHz gives exactly 32.
*Proposed*: **run the chip at 48 MHz** (24 or 96 MHz also divide exactly). This contradicts
`info.yaml`, which says 50 MHz, and is the one recommendation in this study that costs the
designer work. → `Q-001`.
*Also proposed regardless*: the tick divider of `MAC-CLK-001` carries a fractional part, because
UART at 115200 needs it and it costs ~16 flops.

**`GAP-USB-002` — no line coding.**
NRZI encode and decode are a one-bit state machine, but they sit *between* the shift register
and the pins, where no instruction can reach. Doing it in the program needs an XOR and costs
≥6 of the 32 cycles per bit.
*Proposed*: a **line coder** unit in the pin path, configurable NRZI now and Manchester later
for 10BASE-T, with an invert bit for the LS/FS `J`/`K` swap. → `MAC-COD-001`.

**`GAP-USB-003` — no bit stuffing, and no way for a MAC unit to stall the sequencer.**
This is the deepest architectural consequence in the study. A stuffed bit occupies a bit time on
the wire but consumes no bit from the OSR, and a removed stuff bit consumes a bit time from the
wire but supplies none to the ISR. A cycle-exact sequencer executing `out pins, 1 [6]` every 8
ticks has no way to skip an iteration without a branch, and a branch costs the same on every
bit.
*Proposed*: the stuffer **gates the sequencer's tick enable for one bit time** when it inserts
or removes a bit. The sequencer's program is unchanged and unaware; its notion of time simply
stops. This makes the MAC chain part of the clock-enable path, not just the data path, and it
is the one place where Golem must depart structurally from a PIO-shaped machine.
The run length is programmable (6 for USB, 5 for HDLC and CAN). → `MAC-STF-001`.
*Consequence to verify*: every other workload must be unaffected when the stuffer is bypassed,
and the stall must not extend a `WAIT` or corrupt a deadline timer that is counting real time.
→ `Q-009`.

**`GAP-USB-004` — the line state is a 2-bit symbol with four meanings.**
`SE0`, `J` and `K` are conditions on two pins at once. `JMP pin` tests one pin, and testing two
costs two branches at two different ticks, which is not an atomic view of the line.
*Proposed*: the EOP/SOP detectors live in the MAC chain and expose **MAC flags**, tested with
`JMP macflag i` / `JMP !macflag i` and waited on with `WAIT pol, macflag i`. This also gives the
CRC residue and the FIFO levels a uniform branch source. → `ISA-JMP-004`, `ISA-WAIT-001`.

**`GAP-USB-005` — the receive bit clock cannot be recovered.**
The device's clock and the host's differ by up to ±1.5% plus our own error. Over a maximum
low-speed packet (about 90 bits) an uncorrected 1.5% error accumulates to 1.35 bit times — more
than a whole bit. The receiver must re-centre its sampling point on every line transition, and
nothing in any instruction set can reload a delay counter mid-instruction.
*Proposed*: `MAC-CLK-001` generates the sequencer's tick enable and takes an optional
**resync input**: a line transition on a nominated pin group reloads the divider to its
half-bit phase. UART RX would use the same mechanism instead of its `WAIT`-and-count-1.5-bits
opening, and 10BASE-T would need it too. → `MAC-CLK-001`, `MAC-CLK-002` (the SOP detector that
declares the clock locked after `SYNC`).

**`GAP-USB-006` — no CRC.**
CRC5 on every token, CRC16 on every data packet, generated on transmit and checked on receive
inside the 7.5-bit-time window. Argued above: impossible in software, both in-line and after
the fact.
*Proposed*: `MAC-CRC-001`, a programmable LFSR: polynomial, initial value, input/output bit
reflection, output complement, and a residue-match flag. The same unit is SWD's parity
(`x + 1`) and UART's parity. 16 bits covers the must and should tiers; 10BASE-T's CRC32 would
need 32. → `MAC-CRC-001`, `Q-003`.

**`GAP-USB-007` — no compare.**
Token decode needs the received 7-bit address compared against the assigned address, and the
4-bit endpoint used as a selector, inside the response window.
*Proposed*: `OUT x, 7` and `JMP x!=y, addr` — both already asked for by `spi.md` and `swd.md`.
No new mechanism.

**`GAP-USB-008` — no sequencer-to-sequencer handoff.**
RX and TX cannot be the same program: RX must be armed at all times, and the handoff has a
one-bit-time budget. Going through the host's SPI link would blow the 5 µs deadline by orders of
magnitude, which is precisely the split PLAN.md describes.
*Proposed*: `IRQ set/clear i` and `WAIT pol, irq i`, with the flags shared between sequencers
and visible to the host. Measured cost of the handoff above: 2 ticks. → `ISA-IRQ-001`.
**USB alone makes the sequencer count a correctness parameter, not a throughput one.**

**`GAP-USB-009` — millisecond timing.**
Bus reset (10 ms), keep-alive (1 ms) and suspend (3 ms) are 10⁴–10⁶ cycles.
*Proposed*: the deadline timer `MAC-TMR-001` that `i2c.md` already needs for the stretch
timeout, widened to 24 bits (349 ms at 48 MHz). Keep-alive *generation* in host mode can stay on
the host, since 1 ms is far outside the 10 µs rule. → `MAC-TMR-001`.

## What USB did *not* need

No arithmetic beyond compare-with-zero and compare-with-Y; no memory; no indirect addressing;
no instruction that reads a MAC unit's internal state (only its flags and, once per packet, its
residue via `MOV osr, ~crc`). The USB program is *shorter* than the SWD program. Every hard
thing it does lives in the MAC chain, which is exactly the thesis in PLAN.md — and this study is
the first place it is checked rather than asserted.
