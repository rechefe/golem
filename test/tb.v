`default_nettype none
`timescale 1ns / 1ps

/* This testbench just instantiates the module and makes some convenient wires
   that can be driven / tested by the cocotb test.py.
*/
module tb ();

  // Dump the signals to a FST file. You can view it with gtkwave or surfer.
  initial begin
    $dumpfile("tb.fst");
    $dumpvars(0, tb);
    #1;
  end

  // Wire up the inputs and outputs:
  reg clk;
  reg rst_n;
  reg ena;
  reg [7:0] ui_in;
  reg [7:0] uio_in;
  wire [7:0] uo_out;
  wire [7:0] uio_out;
  wire [7:0] uio_oe;

  // Top module under test (spec/top.md):
  tt_um_rechefe_golem user_project (
      .ui_in  (ui_in),    // Dedicated inputs
      .uo_out (uo_out),   // Dedicated outputs
      .uio_in (uio_in),   // IOs: Input path
      .uio_out(uio_out),  // IOs: Output path
      .uio_oe (uio_oe),   // IOs: Enable path (active high: 0=input, 1=output)
      .ena    (ena),      // enable - goes high when design is selected
      .clk    (clk),      // clock
      .rst_n  (rst_n)     // not reset
  );

  // emet monitors (issue #19): one per unit with an emet block in spec/, reaching
  // into user_project's block instances by hierarchical reference. See
  // formal/emet/README.md, "Reaching a unit that is not the top module".
  // RTL sim only: a gate-level netlist doesn't preserve block-level instance
  // names, so the hierarchical paths below wouldn't resolve (test/Makefile
  // only defines EMET_SIM, and only compiles the generated monitors in, for
  // GATES != yes).
`ifdef EMET_SIM
  `include "../formal/emet/generated/tb_emet.vh"
`endif

endmodule
