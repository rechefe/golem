## How it works

Golem is a reprogrammable protocol-emulator ASIC: tiny cycle-exact sequencers plus bit-stream
MAC units (CRC, bit stuffing, line coding) that implement UART, SPI, I2C, JTAG/SWD and USB
low-speed in firmware. See `PLAN.md` in the repository.

This build is the **gate build**: a fixed UART transmitter (8N1, 115200 baud at 48 MHz) that
proves the Hardcaml → formal verification → GDS flow end to end. Its behaviour is specified in
`spec/uart_tx.md` and proven with SymbiYosys for every byte value and every bit period.

## How to test

1. Clock the design at 48 MHz and pulse `rst_n` low.
2. Put a byte on `ui_in[7:0]` and raise `uio_in[0]` (VALID) for one clock cycle while
   `uo_out[1]` (READY) is high.
3. The byte appears on `uo_out[0]` (UART_TX) as an 8N1 frame at 115200 baud. Connect it to a
   USB-UART adapter's RX pin to see it on a terminal.

## External hardware

A 3.3 V USB-UART adapter on `uo_out[0]`.
