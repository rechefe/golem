# Golem

**Clay until you write the word.** Golem is a reprogrammable protocol-emulator ASIC: silicon
that becomes a UART, an SPI or I2C bus, a JTAG/SWD probe or a USB low-speed device, depending
on the program you load into it. Built for the
[Jane Street protocol emulator ASIC competition](https://blog.janestreet.com/protocol-emulator-asic-competition/)
on IHP 130nm CMOS5L via [Tiny Tapeout](https://tinytapeout.com), 6x4 tiles.

In Jewish folklore a golem is shaped from clay and animated by a word written on it:
**אמת**, *emet*, "truth". Our verification layer carries that name. Every behaviour in the
spec is a requirement with an ID, every requirement is a property, and every property is
proven against the RTL.

## How it's built

- **Spec first.** `spec/` is the micro-architecture specification: numbered requirements with
  cycle-exact acceptance criteria.
- **RTL in [Hardcaml](https://github.com/janestreet/hardcaml)** (`rtl/`), generated to Verilog
  in `src/`.
- **Independent verification.** `formal/` holds SymbiYosys proofs and `test/` cocotb tests,
  written from the spec without reading the RTL.
- **Built by agents.** A spec agent, a designer, a verifier and a reviewer work from GitHub
  issues, in separate contexts, each in its own lane. The owner approves spec changes and
  steps in when something is stuck. Roles are in `agents/`, the plan in `PLAN.md`, and
  [`agents/README.md`](agents/README.md) explains the dispatch machinery with diagrams.

## Status

Gate build: an 8N1 UART transmitter, proven unbounded against `spec/uart_tx.md` and hardened
through the Tiny Tapeout flow. Next milestone: MAS v1 and the emet property language
(2026-10-10). Full milestones are in `PLAN.md`.

## Build

Requirements: OCaml 5.3 with Hardcaml v0.17 (opam), [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build),
Python with `test/requirements.txt`.

```
make rtl              # Hardcaml -> src/golem.v
make unit             # Hardcaml expect tests
make check-generated  # fails if src/golem.v is stale or hand-edited
make sim              # cocotb on the generated Verilog
make formal           # SymbiYosys proofs and covers
make ci               # everything
make clean            # remove build, sim and formal artefacts
```

## License

Apache-2.0
