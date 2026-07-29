// Order Field Latch (Table 15 doorbell -> Stable Order Command).
// Owner: TBD

module tx_order_latcher (
  input  logic clk,
  input  logic rst_n,

  // from axi_lite_regbank
  input  logic [15:0] ord_symbol,
  input  logic [7:0]  ord_side,
  input  logic [31:0] ord_qty,
  input  logic [31:0] ord_price,
  input  logic [31:0] ord_id,
  input  logic        doorbell_pulse,

  // to axi_lite_regbank (TX_READY register source)
  output logic         tx_ready,

  // to tx_frame_builder -- Stable Order Command
  output logic         cmd_valid,
  output logic [31:0]  cmd_order_id,
  output logic [15:0]  cmd_symbol,
  output logic [7:0]   cmd_side,
  output logic [31:0]  cmd_qty,
  output logic [31:0]  cmd_price,

  input  logic          frame_builder_busy
);

  // TODO(owner):
  // - [ ] No FSM. tx_ready = !frame_builder_busy.
  // - [ ] cmd_valid = doorbell_pulse & !frame_builder_busy.
  // - [ ] cmd_* : enabled registers, clock-enable = cmd_valid, data = ord_*.
  // - [ ] Reset (rst_n low): cmd_valid = 0, cmd_* = 0. tx_ready follows
  //       !frame_builder_busy at all times including reset.

endmodule
