# Tiny Tapeout top level (`TOP`)

Status: **v1, gate wiring.** Exposes the UART transmitter directly on pins so the flow can
be tested on a real board. Replaced by the SPI host interface and sequencer pins at MAS v1.

Module name: `tt_um_rechefe_golem` (Tiny Tapeout standard ports).

## Requirements

### TOP-CLK-001 — Clock and reset

**Statement**: `clk` drives every block's `clock`. Every block's `clear` is `not rst_n`.

**Acceptance**: holding `rst_n = 0` for one edge puts the UART into its UTX-RST-001 state.

### TOP-PIN-001 — Gate pin map

**Statement**: The UART transmitter is wired as follows, with `divisor = 433`
(115200 baud at a 50 MHz clock).

| Pin          | Signal         |
|--------------|----------------|
| `ui_in[7:0]` | UART `data`    |
| `uio_in[0]`  | UART `valid`   |
| `uo_out[0]`  | UART `tx`      |
| `uo_out[1]`  | UART `ready`   |

All other `uo_out` bits are 0. `uio_oe = 0` (all bidirectional pins are inputs) and
`uio_out = 0`.

**Acceptance**: a byte presented on `ui_in` with `uio_in[0] = 1` appears on `uo_out[0]` as
an 8N1 frame at 434 cycles per bit.
