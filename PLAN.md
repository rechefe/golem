# Golem — project plan

Golem is our entry to the [Jane Street protocol emulator ASIC competition](https://blog.janestreet.com/protocol-emulator-asic-competition/):
a reprogrammable protocol-emulator ASIC on IHP 130nm CMOS5L via Tiny Tapeout, 6x4 tiles
(1289 x 711 um). Submission deadline: **2027-01-18**.

This file records decisions. Agents treat it as settled; changing it is the owner's call.

## Thesis

PIO-style state machines are precise but weak at bit-level stream work (CRC, bit stuffing,
NRZI, Manchester); PRU-style cores are flexible but spend a whole CPU per few pins. Golem
splits the problem:

- **PHY sequencers**: tiny cycle-exact cores that read/write pins, count cycles and branch on
  received data. Their ISA is *workload-driven*: UART, SPI, I2C, SWD and USB-LS are first
  written as pseudo-assembly, and the ISA is the minimum those programs need.
- **MAC-assist units**: configurable LFSR/CRC, bit stuff/unstuff and line coders chained behind
  the sequencers.
- **Deadline split**: anything with a response deadline under ~10 us (ACK/NAK, handshakes,
  CRC checks, framing) runs on chip. Buffering, enumeration and the user API run on the host
  (the RP2040 on the Tiny Tapeout demo board), talking to Golem over **SPI**. The host SDK is
  co-simulated against the RTL.
- Sequencer count and FIFO depth are parameters, so 8x4 tiles (if it arrives) is a config change.

## Protocol tiers

| Tier   | Protocols                  |
|--------|----------------------------|
| Must   | UART, SPI, I2C, JTAG/SWD   |
| Should | USB low-speed (flagship)   |
| Could  | 10BASE-T (external AFE)    |

## Design and verification method

- **RTL**: Hardcaml (OCaml), emitted to Verilog in `src/`. Fallback to SystemVerilog if the
  Hardcaml gate fails.
- **Spec (MAS)**: structured Markdown in `spec/`, every requirement carries an ID
  (e.g. `UTX-FRM-001`), plus an executable OCaml reference model.
- **emet**: a small property language (5-8 pattern types) embedded in the MAS. It compiles to
  Verilog monitors for SymbiYosys and to simulation checkers, so one property serves formal
  and sim. Until emet exists, properties are hand-written Verilog monitors in `formal/`.
- **Traceability matrix**, generated: requirement ID → properties/tests → mutation-kill status
  (Yosys `mcy`).

### Definition of done (per block)

1. Every requirement ID in the block's spec is covered by at least one property or test.
2. Properties are proven unbounded, or to a stated depth justified in the spec.
3. Mutation-kill rate >= 95%; every surviving mutant is explained.
4. The reviewer agent has grilled it and passed it.
5. CI is green through GDS.

## Agents

| Agent        | Model                                  | Writes to                              |
|--------------|----------------------------------------|----------------------------------------|
| spec         | Opus                                   | `spec/` (via `spec-provisional`)       |
| designer     | Sonnet; Opus after 2 red CI runs       | `rtl/`, `src/` (generated)             |
| verifier     | Sonnet; Opus after 2 red CI runs       | `formal/`, `test/`                     |
| reviewer     | Opus                                   | PR reviews only                        |
| orchestrator | Sonnet                                 | issues and labels only                 |

Designer and verifier work from the same spec in separate runs and never read each other's
lane. Mismatches become spec clarifications. Role instructions live in `agents/`.

### Owner gates (the only things that reach the owner)

- Behaviour-changing spec PRs to `main` (enforced by CODEOWNERS on `spec/`).
- An issue stuck after 3 failed attempts (label `status:stuck`).
- Weakened or deleted properties: listed in the weekly digest, no ping.

### Budget

Half of a $100 Max plan's weekly usage; the orchestrator paces to ~1/7 of that per day.
CI runs on free GitHub-hosted runners (public repo).

## Milestones

`main` always holds a submittable GDS.

| Date       | Milestone                                                  |
|------------|------------------------------------------------------------|
| 2026-09-26 | Hardcaml gate: UART TX in Hardcaml, proven, hardened in CI |
| 2026-10-10 | MAS v1 and emet frozen                                     |
| 2026-10-24 | Must tier done                                             |
| 2026-11-07 | USB low-speed                                              |
| 2026-11-21 | Submittable v1, draft writeup                              |
| 2027-01-18 | 10BASE-T attempt, 8x4 if offered, polish, submit           |

## FPGA

Nexys Video (Artix-7 200T), run manually by the owner at home; never wired to CI. Protocol
pins on Pmod headers; the FPGA clock matches the ASIC target.

## Submission package

The chip; the MAS and emet; the traceability matrix with mutation scores; the agent
development log with reviewer transcripts; a video of the FPGA running a protocol written
after the spec freeze.
