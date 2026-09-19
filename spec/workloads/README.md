# Workload study — protocols as pseudo-assembly

Status: **proposal for the owner. Not requirements.** Nothing in `spec/workloads/` constrains
the RTL. No requirement ID appears here, and the designer and verifier build nothing from these
files until the owner accepts a follow-up MAS section.

## Why

PLAN.md says the sequencer ISA is *workload-driven*: "UART, SPI, I2C, SWD and USB-LS are first
written as pseudo-assembly, and the ISA is the minimum those programs need." This directory is
that exercise. Each protocol is written against a deliberately under-powered baseline machine
(**B0**, below); everything the program cannot express is recorded as a numbered gap, and
`summary.md` collects the gaps into the smallest instruction set and set of MAC-assist units
that cover all five.

| File          | Workload                                                   |
|---------------|------------------------------------------------------------|
| `uart.md`     | UART transmitter and receiver, 8N1                          |
| `spi.md`      | SPI master, mode 0                                          |
| `i2c.md`      | I2C master, fast mode, with clock stretching                |
| `swd.md`      | SWD (and a note on JTAG)                                    |
| `usb_ls.md`   | USB low speed, 1.5 Mbit/s, device role                      |
| `summary.md`  | The minimum ISA and MAC units; coverage matrix; open questions |

## Identifiers

Proposal identifiers, **not** requirement IDs. They are local to `spec/workloads/` and are
expected to disappear when the owner turns the accepted parts into a MAS section.

- `GAP-<WL>-nnn` — something a workload needs that B0 cannot express.
- `ISA-<MNEMONIC>-nnn` — a proposed instruction or instruction field.
- `MAC-<UNIT>-nnn` — a proposed MAC-assist unit.
- `Q-nnn` — a question only the owner can settle (collected in `summary.md`).

## The baseline machine, B0

B0 is the straw man the studies push against. It is deliberately the smallest thing that could
be called a pin sequencer, so that "the sequencer lacks X" means something precise: *X is not
in B0 and at least one workload needs it*.

**State**: a program counter; a 32-bit output shift register `OSR`; a 32-bit input shift
register `ISR`; one 4-word TX FIFO and one 4-word RX FIFO shared with the host.

**Pins**: one output group (driven levels only — no direction control) and one input group,
both at a fixed base with a fixed width.

**Instructions** (five):

| Mnemonic        | Meaning                                                        |
|-----------------|-----------------------------------------------------------------|
| `SET dst, imm`  | 5-bit immediate to `pins`                                       |
| `OUT dst, n`    | shift `n` bits out of `OSR` to `pins`                           |
| `IN src, n`     | shift `n` bits from `pins` into `ISR`                           |
| `JMP addr`      | unconditional branch                                            |
| `PUSH` / `PULL` | `ISR` → RX FIFO, TX FIFO → `OSR`; both block while the FIFO is not ready |

**Timing**: the sequencer advances one *tick* per instruction. Every instruction carries a
delay field written `[d]`, which stalls the sequencer for `d` further ticks, so an instruction
written `[d]` occupies `d + 1` ticks. B0's delay field is 4 bits, `d = 0..15`. In B0 one tick is
one clock cycle.

**Not in B0**: scratch registers, conditional branches, `WAIT`, `MOV`, `IRQ`, side-set, pin
direction control, any clock divider, and any bit-stream processing whatsoever.

## Notation

- `side v` — a value driven on the side-set pin(s) in the same tick as the instruction, as on
  the RP2040 PIO. Not in B0; proposed by several workloads.
- `nop [d]` — assembler alias for `jmp <next instruction> [d]`. Expressible in B0.
- Cycle counts in the listings are **ticks**, and each program states its tick length in clock
  cycles. Where a program is annotated `; tick 12`, that is the tick index counted from a named
  event in the program's timing section.
- "Cycles" always means clock cycles of the ASIC clock.

## Reference clock

The studies quote cycle counts at **48 MHz** and, where it matters, at the 50 MHz that was in
`info.yaml` when they were written. The choice is not neutral: USB low speed needs an integer,
jitter-free divide and 48 MHz gives one while 50 MHz does not. The owner has since settled the
clock at 48 MHz, so every cycle count here is the live one. See `usb_ls.md` (`GAP-USB-001`)
and `summary.md` `Q-001`.

## Sources

Protocol timing is taken from the public standards: USB 2.0 (chapter 7), the NXP I2C-bus
specification UM10204 rev 7.0, and the Arm ADIv5/ADIv6 debug interface specification. Where a
number is a design choice rather than a standard's requirement, the text says so. The machine
model borrows heavily and openly from the RP2040 PIO; `summary.md` states where the workloads
push Golem away from it.
