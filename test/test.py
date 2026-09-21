# SPDX-License-Identifier: Apache-2.0
# cocotb tests for the Tiny Tapeout top (spec/top.md) through the real pins.
# Runs on RTL (`make sim`) and on the gate-level netlist (GATES=yes, in the gds workflow).

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "formal" / "emet" / "generated"))
from covers import COVERS  # noqa: E402  (generated; see formal/emet/compile.py)

CYCLES_PER_BIT = 434  # TOP-PIN-001: divisor 433 -> 115200 baud at 50 MHz
CLOCK_NS = 20  # 50 MHz


def assert_emet_ok(dut):
    """issue #19, point 3: emet_fail is sticky, so checking once here (rather
    than at the edge it rises) still catches a failure anywhere earlier in
    this test. Not present under GATES=yes (see tb.v: RTL only)."""
    fail = getattr(dut, "emet_any_fail", None)
    if fail is not None:
        assert int(fail.value) == 0, "an emet property failed during this test"


def tx(dut):
    return int(dut.uo_out.value) & 1


def ready(dut):
    return (int(dut.uo_out.value) >> 1) & 1


async def reset(dut):
    cocotb.start_soon(Clock(dut.clk, CLOCK_NS, unit="ns").start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


async def send_and_capture(dut, byte):
    """Present `byte` with valid for one cycle, then sample tx mid-bit for 10 bits."""
    await FallingEdge(dut.clk)
    dut.ui_in.value = byte
    dut.uio_in.value = 1
    await FallingEdge(dut.clk)
    dut.uio_in.value = 0
    dut.ui_in.value = 0  # UTX-FRM-002: changing data after accept must not matter
    await ClockCycles(dut.clk, CYCLES_PER_BIT // 2)
    bits = []
    for _ in range(10):
        bits.append(tx(dut))
        await ClockCycles(dut.clk, CYCLES_PER_BIT)
    return bits


@cocotb.test()
async def test_reset_idle(dut):
    """TOP-CLK-001 / UTX-RST-001: after reset the line idles high and ready is set."""
    await reset(dut)
    assert tx(dut) == 1
    assert ready(dut) == 1
    assert int(dut.uio_oe.value) == 0
    assert int(dut.uio_out.value) == 0
    assert int(dut.uo_out.value) >> 2 == 0
    assert_emet_ok(dut)


@cocotb.test()
async def test_frames_on_pins(dut):
    """TOP-PIN-001: bytes appear on uo_out[0] as 8N1 frames at 434 cycles per bit."""
    await reset(dut)
    for byte in (0x55, 0xA5, 0x00, 0xFF, 0x3C):
        bits = await send_and_capture(dut, byte)
        start, data_bits, stop = bits[0], bits[1:9], bits[9]
        value = sum(b << i for i, b in enumerate(data_bits))
        assert start == 0, f"start bit for {byte:#04x}"
        assert value == byte, f"sent {byte:#04x}, line carried {value:#04x}"
        assert stop == 1, f"stop bit for {byte:#04x}"
        await ClockCycles(dut.clk, CYCLES_PER_BIT)
        assert ready(dut) == 1, "ready after the frame"
    assert_emet_ok(dut)


@cocotb.test()
async def test_busy_ignores_valid(dut):
    """UTX-HSK-001/004: valid held high through a frame is not queued mid-frame; the next
    byte goes out only after ready returns, back to back."""
    await reset(dut)
    await FallingEdge(dut.clk)
    dut.ui_in.value = 0x81
    dut.uio_in.value = 1
    await FallingEdge(dut.clk)
    dut.ui_in.value = 0x7E  # valid stays high with new data during the whole first frame
    await ClockCycles(dut.clk, CYCLES_PER_BIT // 2)
    bits = []
    for _ in range(20):
        bits.append(tx(dut))
        await ClockCycles(dut.clk, CYCLES_PER_BIT)
    dut.uio_in.value = 0

    def decode(frame):
        assert frame[0] == 0 and frame[9] == 1, f"framing {frame}"
        return sum(b << i for i, b in enumerate(frame[1:9]))

    assert decode(bits[:10]) == 0x81, "first frame unaffected by the held valid"
    assert decode(bits[10:]) == 0x7E, "second byte sent right after the first"
    assert_emet_ok(dut)


@cocotb.test()
async def test_emet_coverage_report(dut):
    """issue #19, point 3: report which emet cover scenarios this run hit.
    Defined last so it sees the covers accumulated by every test above --
    cocotb runs a module's tests in definition order against one continuing
    simulation, and the `_hit` flags are sticky for the whole run."""
    await reset(dut)
    for inst, label in COVERS:
        monitor = getattr(dut, inst, None)
        hit = bool(getattr(monitor, f"{label}_hit").value) if monitor is not None else None
        dut._log.info("emet cover %s.%s: %s", inst, label, "hit" if hit else "MISSED")
    assert_emet_ok(dut)
