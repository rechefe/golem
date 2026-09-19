# Workload: SWD (and a note on JTAG)

Proposal, not requirements. See `README.md` for the baseline machine B0 and the notation.

Serial Wire Debug, host (debugger) role, as defined by Arm ADIv5. A transfer is:

1. **Request**, 8 bits driven by the host, LSB first: `Start(1)`, `APnDP`, `RnW`, `A[2]`,
   `A[3]`, `Parity`, `Stop(0)`, `Park(1)`. The parity bit covers the four middle bits and is
   supplied by the host SDK inside the byte, so it costs the sequencer nothing.
2. **Turnaround**, 1 clock, bus released.
3. **ACK**, 3 bits driven by the target, LSB first: `OK` = 0b001, `WAIT` = 0b010,
   `FAULT` = 0b100.
4. **Data**, 32 bits LSB first plus one **odd parity** bit. Driven by the target for a read;
   for a write there is a further turnaround first and the host drives.
5. For a read, a final turnaround.

The host drives SWDIO on the falling edge of SWCLK and the target samples it on the rising
edge; the target drives on the rising edge and the host samples on the falling edge.

## Pins

| Name    | Dir   | Count | Notes                                          |
|---------|-------|-------|-------------------------------------------------|
| `SWCLK` | out   | 1     | Side-set. Host-generated; no external timing.   |
| `SWDIO` | bidir | 1     | `OUT`/`IN` group plus `pindirs` for turnaround. |

**2 pins.** JTAG needs 4 (`TCK`, `TMS`, `TDI`, `TDO`); see the note at the end.

## Tick length

SWCLK is entirely ours, so the tick is a free choice. At 4 ticks per bit (2 low, 2 high) and
tick = 1 cycle, SWCLK is **12 MHz at 48 MHz**. The ceiling is the same `L_rt` = 3-cycle round
trip derived in `spi.md`: the host samples a target-driven bit 3 cycles after the rising edge
that produced it, which at 4 cycles per bit lands one cycle after the falling edge — exactly
where ADIv5 says to sample.

## Program: SWD read transfer

```
.program swd_read             ; tick = 1 clock cycle, 4 ticks per SWCLK bit
.side_set 1                   ; SWCLK
; OUT/IN/SET group = SWDIO (1 pin), also as pin directions.
; OSR shift right (LSB first); ISR shift left (see the ACK decode below).

swd_req:
    pull  block         side 0          ; OSR <- 8-bit request byte
    set   pindirs, 1    side 0          ; drive SWDIO
    set   x, 7          side 0
req_bit:
    out   pins, 1       side 0  [1]     ; cycles 0-1: SWDIO <- bit, SWCLK low
    jmp   x--, req_bit  side 1  [1]     ; cycles 2-3: SWCLK high, target samples

    set   pindirs, 0    side 0  [1]     ; turnaround: release SWDIO, SWCLK low
    set   x, 2          side 1  [1]     ; SWCLK high: target drives ACK bit 0
ack_bit:
    nop                 side 0          ; cycle 0
    in    pins, 1       side 0          ; cycle 1: sample, 3 cycles after the rise
    jmp   x--, ack_bit  side 1  [1]     ; cycles 2-3: SWCLK high, next bit

    mov   y, isr        side 0          ; ACK in Y                        [GAP-SWD-002]
    set   x, 4          side 0          ; OK = 0b001 LSB-first, left-shifted into ISR = 0b100
    jmp   x!=y, swd_bad side 0          ; WAIT or FAULT                   [GAP-SWD-002]

    set   x, 31         side 0          ; 32 data bits
rd_bit:
    nop                 side 0
    in    pins, 1       side 0          ; sample, 3 cycles after the rise
    jmp   x--, rd_bit   side 1  [1]
    nop                 side 0
    in    pins, 1       side 0          ; the target's parity bit         [GAP-SWD-003]
    nop                 side 1  [1]     ; cycles 2-3: last SWCLK high
    set   pindirs, 1    side 0  [1]     ; turnaround, host drives again
    jmp   !macflag 0, swd_parity        ; MAC-CRC-001 residue check       [GAP-SWD-003]
    push  block         side 0          ; 32 data bits -> RX FIFO
    jmp   swd_req       side 0

swd_bad:
    irq   set 2         side 0          ; WAIT or FAULT: the host retries  [GAP-SWD-004]
    jmp   swd_req       side 0
swd_parity:
    irq   set 3         side 0
    jmp   swd_req       side 0
```

28 instruction words — the largest of the five programs, and the one that sizes the instruction
memory. A **write** transfer is the same program with one more turnaround after
the ACK and the data loop replaced by `out pins, 1` / `jmp x--` (as in `req_bit`), with the
parity bit taken from `MAC-CRC-001` instead of checked against it. The exact clock alignment of
both turnarounds must be re-derived against ADIv5 when this becomes a requirement; the listing
above is sized for the ISA question, not verified against a target (`Q-007`).

**ACK decode.** The ISR shifts left, so the three LSB-first ACK bits land reversed in
`ISR[2:0]`: `OK` (`ACK[0] = 1`) reads as `0b100 = 4`, `WAIT` as `0b010 = 2`, `FAULT` as
`0b001 = 1`. Comparing against a 5-bit `SET` immediate works, but the reversal is exactly the
kind of hidden inversion the spec is supposed to eliminate — `MOV` with bit-reverse
(`ISA-MOV-001`, first asked for by `i2c.md`) lets the program compare against the value in the
Arm document instead.

## Tightest timing deadline

SWD imposes **no response deadline** on the host. It owns SWCLK and may stop it between any two
bits; a target that is not ready answers `WAIT` rather than stretching the clock. This is the
most forgiving of the five workloads.

The numbers that do bind:

> **SWDIO read round trip: 3 clock cycles (62.5 ns at 48 MHz)** — the same `L_rt` as SPI, and
> the reason SWCLK tops out near 12 MHz for a single sequencer.

> **Turnaround: the host must stop driving SWDIO within one SWCLK period** of the park bit, and
> must resume within one period after the read's trailing turnaround. At 4 ticks per bit this
> is a 4-tick budget and the `set pindirs` costs 1.

Because there is no deadline, SWD is the workload that most cleanly separates *what the ISA
needs* from *what the schedule needs*: every gap below is about expressiveness.

## Gaps against B0

**`GAP-SWD-001` — the bus cannot be turned around.**
SWDIO is driven by the host for the request and by the target for the ACK and read data. B0
drives levels only.
*Proposed*: already covered by `ISA-SET-002` / `ISA-OUT-002` (`pindirs` as a destination),
first raised by `i2c.md`. SWD adds no new mechanism, which is itself worth recording: one
direction-control primitive serves open drain and bus turnaround.

**`GAP-SWD-002` — no compare-and-branch.**
The ACK is a three-valued field that selects three different continuations. Decoding it with
`JMP pin` needs the three bits sampled at three separate, exactly-spaced ticks and three
branches; decoding it from the ISR needs an equality test that B0 has not got.
*Proposed*: `MOV dst, src` (to get the ISR into a scratch register) and `JMP x!=y, addr`.
`JMP x!=y` also serves USB's device-address compare, so two workloads pay for it.
→ `ISA-MOV-001`, `ISA-JMP-003`.

**`GAP-SWD-003` — odd parity over 32 bits cannot be computed in-line.**
The read path must check parity over the 32 data bits; the write path must generate it. There
is no XOR instruction, and adding one would still cost at least two ticks per bit inside a loop
that is 4 ticks long — a 50% throughput loss on the only thing SWD does.
*Proposed*: route the `IN`/`OUT` bit stream through the CRC/LFSR MAC unit configured with the
polynomial `x + 1`, which is a one-bit parity accumulator, and expose its residue as a branch
condition (`JMP macflag`/`JMP !macflag`) and as an `OUT`/`IN` source for generation.
→ `MAC-CRC-001`, `ISA-JMP-004`.
This is the same unit USB needs for CRC5 and CRC16 and UART would need for 8E1/8O1. **SWD is
the cheapest evidence that the CRC unit must be a general LFSR with a programmable polynomial
rather than a fixed USB CRC block.**

**`GAP-SWD-004` — a transfer cannot be retried on chip.**
An `ACK = WAIT` means "re-issue the identical request". The request has already been shifted out
of the OSR and B0 cannot rewind it, so the retry must come back from the host — and at that
point the 5 µs-class latency budget of PLAN.md's deadline split is irrelevant, because SWD has
no deadline. *Recommendation*: **the host retries.** No hardware. Recorded so that a later
reader does not add an OSR rewind for SWD's sake. → `Q-008`.

**`GAP-SWD-005` — the line reset sequence is data, not control.**
Connecting needs ≥50 SWCLK cycles with SWDIO high, the JTAG-to-SWD select sequence `0xE79E`, and
another line reset. All of it is bits the host pushes through `req_bit`; the only requirement is
that `PULL` can be told to supply all-ones rather than stalling, so the host need not push eight
identical words. *Proposed*: `OUT` from a `NULL` source (shifts in zeros) plus `MOV osr, ~osr`
covers it with no new mechanism. No new gap.

## JTAG

JTAG is SWD's four-pin cousin and adds nothing to the ISA:

- `TCK` side-set, `TDI` and `TMS` in a **2-pin `OUT` group** (`out pins, 2` drives both in one
  tick — the TAP state walk needs `TMS` to change per bit alongside `TDI`), `TDO` in the `IN`
  group.
- No parity, no CRC; the IR/DR lengths come from the host.
- Same `L_rt` ceiling on TCK.

It costs **4 pins** and roughly 20 instruction words, and it is the reason the `OUT` pin group
width must be configurable rather than fixed at 1.
