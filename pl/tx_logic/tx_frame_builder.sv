// Payload Build + Frame Build merged (Stable Order Command -> AXI4-Stream to TEMAC).
// Owner: TBD

// 8-bit m_axis_tdata is an assumption, not a confirmed fact -- see the
// TEMAC open questions in pl_tx_logic/README.md before implementing.
module tx_frame_builder (
  input  logic clk,
  input  logic rst_n,

  // from tx_order_latcher -- Stable Order Command
  input  logic         cmd_valid,
  input  logic [31:0]  cmd_order_id,
  input  logic [15:0]  cmd_symbol,
  input  logic [7:0]   cmd_side,
  input  logic [31:0]  cmd_qty,
  input  logic [31:0]  cmd_price,
  output logic          frame_builder_busy,

  // AXI4-Stream master, toward TEMAC TX
  output logic [7:0] m_axis_tdata,
  output logic       m_axis_tvalid,
  output logic       m_axis_tlast,
  input  logic       m_axis_tready
);

  // Assumes TEMAC is configured with FCS insertion AND frame padding enabled
  // (see README). We emit 58 bytes and stop -- no CRC32, no pad bytes.
  //
  // TODO(owner):
  // - [ ] Counter-driven byte serializer FSM (not 1-cycle, not fixed-step).
  // - [ ] Pick (A) local 480-bit frame copy at cmd_valid, or (B) combinational
  //       mux over constant header ROM + live cmd_* fields, no copy.
  // - [ ] Eth+IP+UDP header (42B): synthesis-time constant ROM, incl.
  //       precomputed IP header checksum (no runtime adder).
  // - [ ] Header fields big-endian; Table 7 payload fields little-endian.
  // - [ ] Table 7 payload (16B): order_id(4), symbol(2), side(1), qty(4),
  //       price(4), pad=0x00(1). symbol comes from cmd_symbol, not hardcoded.
  // - [ ] Length fields EXCLUDE TEMAC's pad: IP total length = 44 (20+8+16),
  //       UDP length = 24 (8+16). Ethernet padding sits below IP and is not
  //       counted by either header.
  // - [ ] Serialize bytes 0-57 onto m_axis_tdata, 1B/cycle while
  //       m_axis_tready high; hold tdata/tvalid when m_axis_tready low.
  // - [ ] m_axis_tlast on byte 57. TEMAC appends pad + FCS after that.
  // - [ ] frame_builder_busy: assert COMBINATIONALLY in the same cycle as
  //       cmd_valid (not registered/next-cycle), else a doorbell landing in
  //       the gap slips past the latcher's mask. Deassert after
  //       (tvalid && tready && tlast).
  // - [ ] Reset (rst_n low): m_axis_tvalid = 0 (AXI4-Stream requires this),
  //       m_axis_tlast = 0, frame_builder_busy = 0, byte counter = 0.

endmodule
