// Formal properties for golem_uart_tx (spec/uart_tx.md).
// Black-box harness: a reference model of the frame, built from the spec alone, runs beside
// the DUT and every requirement is an assertion named after its ID.
`default_nettype none

module uart_tx_formal (
    input wire        clock,
    input wire        clear,
    input wire [7:0]  data,
    input wire        valid,
    input wire [15:0] divisor
);
  wire tx, ready;

  golem_uart_tx dut (
      .clock  (clock),
      .clear  (clear),
      .data   (data),
      .valid  (valid),
      .divisor(divisor),
      .tx     (tx),
      .ready  (ready)
  );

  // The first sampled edge applies clear, so the DUT starts from a defined state.
  reg past_valid = 1'b0;
  reg past_clear = 1'b0;
  always @(posedge clock) begin
    past_valid <= 1'b1;
    past_clear <= clear;
  end
  always @(*) if (!past_valid) assume (clear);

  // ---------------------------------------------------------------------------
  // Reference model (spec "Definitions"): T = divisor + 1 latched at the accept edge,
  // frame bits F[0] = start, F[1..8] = data LSB first, F[9] = stop.
  // After accept edge k, model state at edge k+n encodes bit = (n-1) div T, sub = (n-1) mod T.
  // ---------------------------------------------------------------------------
  wire accept = valid && ready && !clear;

  reg        active = 1'b0;
  reg [7:0]  m_data = 8'd0;
  reg [15:0] m_div  = 16'd0;
  reg [3:0]  m_bit  = 4'd0;
  reg [15:0] m_sub  = 16'd0;
  reg        m_done = 1'b0;  // high exactly at edge k+10T+1

  wire last_cycle = active && (m_bit == 4'd9) && (m_sub == m_div);

  always @(posedge clock) begin
    m_done <= 1'b0;
    if (clear) begin
      active <= 1'b0;
    end else if (active) begin
      if (m_sub == m_div) begin
        m_sub <= 16'd0;
        if (m_bit == 4'd9) begin
          active <= 1'b0;
          m_done <= 1'b1;
        end else begin
          m_bit <= m_bit + 4'd1;
        end
      end else begin
        m_sub <= m_sub + 16'd1;
      end
    end else if (accept) begin
      active <= 1'b1;
      m_data <= data;
      m_div  <= divisor;
      m_bit  <= 4'd0;
      m_sub  <= 16'd0;
    end
  end

  wire [9:0] m_frame = {1'b1, m_data, 1'b0};  // F[9..0]
  wire [9:0] m_shifted = m_frame >> m_bit;
  wire expected_bit = m_shifted[0];

  // ---------------------------------------------------------------------------
  // Requirements
  // ---------------------------------------------------------------------------
  always @(posedge clock) begin
    if (past_valid) begin
      // UTX-RST-001: first edge after clear sampled => idle and ready.
      if (past_clear) begin
        UTX_RST_001_tx:    assert (tx);
        UTX_RST_001_ready: assert (ready);
      end

      // UTX-IDL-001: ready implies idle-high line.
      if (ready) UTX_IDL_001: assert (tx);

      // UTX-HSK-002: busy for edges k+1 .. k+10T.
      if (active) UTX_HSK_002: assert (!ready);

      // UTX-FRM-001 / UTX-FRM-002: tx = F[(n-1) div T]; inputs unconstrained after accept.
      if (active) UTX_FRM_001: assert (tx == expected_bit);

      // UTX-HSK-003: ready at edge k+10T+1.
      if (m_done) UTX_HSK_003: assert (ready);

      // UTX-HSK-004 / UTX-HSK-001: no frame in progress => ready, so no frame starts
      // without an accept edge.
      if (!active && !past_clear) UTX_HSK_004: assert (ready);
    end
  end

  // ---------------------------------------------------------------------------
  // Covers: every property's trigger is reachable (non-vacuity).
  // ---------------------------------------------------------------------------
  reg [1:0] frames_done = 2'd0;
  always @(posedge clock) begin
    if (clear) frames_done <= 2'd0;
    else if (m_done && frames_done != 2'd3) frames_done <= frames_done + 2'd1;
  end

  always @(posedge clock) begin
    if (past_valid) begin
      COVER_frame_a5_div2: cover (m_done && m_data == 8'hA5 && m_div == 16'd2);
      COVER_frame_div0:    cover (m_done && m_div == 16'd0);
      COVER_back_to_back:  cover (frames_done == 2'd2 && active && m_bit == 4'd0 && m_sub == 16'd0);
      COVER_clear_midframe: cover (active && m_bit == 4'd4 && clear);
    end
  end

endmodule
