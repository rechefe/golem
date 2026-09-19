# Workload: I2C master, fast mode, with clock stretching

Proposal, not requirements. See `README.md` for the baseline machine B0 and the notation.

Fast mode, 400 kHz. Single master. 7-bit addressing. Clock stretching by the slave is supported
and is the feature that shapes this workload.

## Pins

| Name  | Dir   | Count | Notes                                                      |
|-------|-------|-------|-------------------------------------------------------------|
| `SDA` | bidir | 1     | Open drain. `OUT`/`SET`/`IN` group, and a `JMP` condition.   |
| `SCL` | bidir | 1     | Open drain. Side-set group, and a `WAIT` condition.          |

**2 pins**, both bidirectional, both with external pull-ups. Neither is ever driven high.

**Open-drain encoding.** The output *data* register for both pins is tied to 0 and the line is
controlled entirely by the pin *direction*: direction 1 drives low, direction 0 releases and the
pull-up gives a 1. So a transmitted data bit of 1 must become a direction of 0 — the OUT path is
inverted with respect to the wire. The program handles this with one `MOV osr, ~osr` per byte
rather than a hardware inverter.

## Tick length

| Quantity                      | Fast mode (UM10204) | Ticks at 10 ticks/bit |
|-------------------------------|---------------------|------------------------|
| bit period                    | ≥ 2.5 µs            | 10                     |
| `tLOW` (SCL low)              | ≥ 1.3 µs            | 6 (1.5 µs)             |
| `tHIGH` (SCL high)            | ≥ 0.6 µs            | 4 (1.0 µs)             |
| `tHD;STA`, `tSU;STO`          | ≥ 0.6 µs            | 4                      |
| `tBUF` (bus free)             | ≥ 1.3 µs            | 6                      |
| `tVD;DAT` (SCL low → SDA valid) | ≤ 0.9 µs          | 3 (0.75 µs)            |

At 10 ticks per bit and 400 kHz the tick is 250 ns = 12 cycles at 48 MHz. Unlike USB, I2C's
numbers are **minima and maxima, not a frequency to match**: running at 384 kHz (13 cycles per
tick) is fully legal, so I2C never needs a fractional divider. Standard mode (100 kHz) and fast
mode plus (1 MHz) are the same program with a different divider.

## Program: I2C master

```
.program i2c_master           ; 1 bit = 10 ticks
.side_set 1 pindirs           ; SCL direction: 1 = drive low, 0 = release
; OUT/SET/IN group = SDA (1 pin), also as pin directions.  Shift direction: left (MSB first).
; Both pins configured open drain: output data = 0, the direction is the line.  [GAP-I2C-001]

i2c_start:                                  ; SDA falls while SCL is released
    set   pindirs, 1       side 0  [3]      ; drive SDA low; tHD;STA = 4 ticks
                                            ; falls through, SCL taken low by the next line

i2c_byte:
    pull  block            side 1           ; OSR <- byte, SCL low
    mov   osr, ~osr        side 1           ; 1 = release, 0 = drive low     [GAP-I2C-002]
    set   x, 7             side 1
i2c_bit:
    out   pindirs, 1       side 1  [4]      ; ticks 0-4: SDA <- bit, SCL low (tLOW = 6)
    nop                    side 0           ; tick 5:    release SCL
    wait  1, pin SCL               [1]      ; ticks 6-7: clock stretching + rise time [GAP-I2C-004]
    in    pins, 1          side 0           ; tick 8:    sample SDA (read data, and see GAP-I2C-005)
    jmp   x--, i2c_bit     side 0           ; tick 9:    SCL high (tHIGH = 4)

i2c_ack:                                    ; 9th clock: release SDA, read the slave
    set   pindirs, 0       side 1  [4]      ; release SDA, SCL low
    nop                    side 0           ; release SCL
    wait  1, pin SCL               [1]      ; stretching again
    jmp   pin SDA, i2c_nak                  ; SDA high at the 9th clock = NAK  [GAP-I2C-003]
                                            ; no side-set: the pin index uses that field, and
                                            ; SCL stays released from the `nop side 0` above
    push  block            side 0           ; ACK: hand the byte just read to the host
    jmp   i2c_byte         side 1

i2c_nak:
    irq   set 1            side 0           ; tell the host; fall into STOP
i2c_stop:                                   ; SDA rises while SCL is released
    set   pindirs, 1       side 1  [4]      ; drive SDA low, SCL low
    nop                    side 0  [3]      ; release SCL; tSU;STO = 4 ticks
    set   pindirs, 0       side 0  [5]      ; release SDA = STOP; tBUF = 6 ticks
    jmp   i2c_start        side 0
```

20 instruction words. A repeated START is `i2c_stop` without the final SDA release, then
`i2c_start`; it reuses the same words with one extra entry point.

**Where the tick budget goes.** Each bit is 10 ticks: SDA setup with SCL low (5), release SCL
(1), stretch wait (2 minimum), sample (1), SCL high (1). `tVD;DAT` is satisfied because SDA is
written in the first tick after SCL falls, 0 of the allowed 3 ticks.

## Clock stretching

A slave holds SCL low to stall the master. The master must not count SCL high time until SCL is
*observed* high. `wait 1, pin SCL` does exactly that, and it is the only instruction in any of
the five workloads whose duration is unbounded:

- A stretch of any length simply lengthens the bit. The rest of the program is unaffected,
  because every later delay is relative to the `WAIT`, not to an absolute tick count.
- A slave that never releases SCL hangs the sequencer forever. SMBus bounds this at
  `tTIMEOUT` = 25 ms; there is no equivalent in plain I2C, so 25 ms is the right default.
  25 ms at 48 MHz is **1.2 million cycles** — four orders of magnitude beyond any delay field
  and beyond a 5-bit `SET` immediate into a scratch register. Nothing in B0, and nothing in a
  PIO-shaped ISA, can express it. See `GAP-I2C-004`.
- A stretch that begins *before* the master releases SCL is indistinguishable from a normal low
  period, which is correct behaviour.

## Tightest timing deadline

I2C imposes no response deadline on the master; it owns SCL and may stretch it itself. The two
numbers worth recording:

> **`tVD;DAT` ≤ 0.9 µs (43 clock cycles at 48 MHz) from SCL falling to the next SDA data bit
> being valid** — the only hard *maximum* in the master's path, and met with 3 ticks to spare.

> **Clock stretching is unbounded**, so the only real constraint is the ability to abandon a
> wait after 25 ms without the host polling.

Compared with the other four workloads I2C is slow (a tick is 12 cycles) and tolerant (every
timing is a minimum). Its contribution to the ISA is entirely about *pin direction* and
*waiting*, not about speed.

## Gaps against B0

**`GAP-I2C-001` — no pin direction control.**
Open drain cannot be emulated by driving levels: driving SDA or SCL high fights the other
master or the slave's stretch, and on a bus with 3.3 V pull-ups it is electrically wrong.
*Proposed*: `SET pindirs, imm` and `OUT pindirs, n` — every destination that reaches `pins` must
also reach `pindirs`; plus a per-pin **open-drain** configuration bit that ties the output data
register low so only the direction matters. → `ISA-SET-002`, `ISA-OUT-002`, `ISA-PINCFG-001`.

**`GAP-I2C-002` — no way to invert a word.**
The direction is the complement of the data. Inverting per bit costs an instruction in the
inner loop; inverting in the host costs nothing on chip but makes the host SDK protocol-aware
in a way that will not survive contact with the other workloads.
*Proposed*: `MOV dst, src` with an operation field — `none`, `invert`, `bit-reverse`. The
bit-reverse case pays for itself in SWD and USB, which are LSB-first while I2C and SPI are
MSB-first. → `ISA-MOV-001`.

**`GAP-I2C-003` — `JMP` on a pin and `WAIT` on a pin must name different pins.**
`wait 1, pin SCL` and `jmp pin SDA` are live at the same instant, four ticks apart. A single
configured "the JMP pin" (the PIO arrangement) cannot serve both, and swapping the configuration
mid-program costs an instruction inside the ACK window.
*Proposed*: the pin index is a field of the instruction in both `WAIT` and `JMP`, not a
configuration register. → `ISA-JMP-002`, `ISA-WAIT-001`.

**`GAP-I2C-004` — no bounded wait.**
`WAIT` on a stretched SCL can hang forever and the host cannot recover the sequencer without a
reset, which loses the bus state. The timeout is 25 ms = 1.2 M cycles, far outside any
instruction field.
*Proposed*: a per-sequencer **deadline timer** — a down-counter loaded from a configuration
register, which on expiry forces the program counter to a configured trap address and raises an
IRQ. It must interrupt a blocked `WAIT`, `PULL` or `PUSH`, which no instruction-level mechanism
can. → `MAC-TMR-001`.

**`GAP-I2C-005` — arbitration loss cannot be detected.**
A multi-master implementation compares what it reads on SDA with what it drove, per bit, and
must drop off the bus within the same bit if they differ. The `in pins, 1` above already samples
SDA at the right tick, but comparing it against the transmitted bit needs a per-bit compare and
a branch inside a loop with no slack.
*Recommendation*: **single master only for v1.** Multi-master would need either `JMP x!=y`
inside the bit loop (affordable at 10 ticks per bit, but it also needs the transmitted bit kept
in a register) or a hardware mismatch flag. Recorded, not proposed. → `Q-006`.

## What I2C did *not* need

No MAC-assist unit. No arithmetic. No CRC (PEC is SMBus-only and would fall out of
`MAC-CRC-001` for free if ever wanted). Its whole contribution is `pindirs`, indexed `WAIT`/`JMP`
pins, `MOV` with invert, and the deadline timer — and the deadline timer is the one piece no
existing PIO-shaped machine has.
