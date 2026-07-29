// Order Field Latch (Table 15 doorbell -> Stable Order Command).
// Owner: Hanyu

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

  logic accept_order;

  // TX_READY is advisory flow control for the PS. It deliberately remains a
  // direct reflection of downstream availability during reset.
  assign tx_ready = !frame_builder_busy;
  assign accept_order = doorbell_pulse && !frame_builder_busy;

  // No queue is present. A doorbell that arrives while busy is discarded, and
  // the last accepted command remains stable for the entire builder busy window.
  //
  // cmd_valid is registered rather than combinational: frame_builder_busy is
  // required to rise combinationally from cmd_valid, so a combinational
  // cmd_valid = doorbell_pulse & !frame_builder_busy would close a loop through
  // the builder. The clock enable is accept_order (cmd_valid one cycle early) so
  // that cmd_* and cmd_valid change on the same edge.
  
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      cmd_valid    <= 1'b0;
      cmd_order_id <= '0;
      cmd_symbol   <= '0;
      cmd_side     <= '0;
      cmd_qty      <= '0;
      cmd_price    <= '0;
    end else begin
      cmd_valid <= accept_order;
      if (accept_order) begin
        cmd_order_id <= ord_id;
        cmd_symbol   <= ord_symbol;
        cmd_side     <= ord_side;
        cmd_qty      <= ord_qty;
        cmd_price    <= ord_price;
      end
    end
  end

endmodule
