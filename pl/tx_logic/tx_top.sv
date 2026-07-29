// Top module for the PL TX Order-Egress path (README 3.1.3.2).
// Wires: axi_lite_regbank -> tx_order_latcher -> tx_frame_builder -> (TEMAC, external)
// TEMAC itself is a Xilinx vendor IP instantiated outside this module (at the
// system/board top level) -- this module's scope ends at producing a valid
// AXI4-Stream master interface.

module tx_top (
  input  logic clk,
  input  logic rst_n,

  // AXI4-Lite slave, PS -> PL (TX-side register window: 0x40-0x54 of Table 15)
  input  logic [7:0]  s_axi_awaddr,
  input  logic        s_axi_awvalid,
  output logic        s_axi_awready,
  input  logic [31:0] s_axi_wdata,
  input  logic        s_axi_wvalid,
  output logic        s_axi_wready,
  output logic [1:0]  s_axi_bresp,
  output logic        s_axi_bvalid,
  input  logic        s_axi_bready,
  input  logic [7:0]  s_axi_araddr,
  input  logic        s_axi_arvalid,
  output logic        s_axi_arready,
  output logic [31:0] s_axi_rdata,
  output logic [1:0]  s_axi_rresp,
  output logic        s_axi_rvalid,
  input  logic        s_axi_rready,

  // AXI4-Stream master, toward TEMAC TX (vendor IP, instantiated at a higher level)
  output logic [7:0] m_axis_tdata,
  output logic       m_axis_tvalid,
  output logic       m_axis_tlast,
  input  logic       m_axis_tready
);

  logic [15:0] ord_symbol;
  logic [7:0]  ord_side;
  logic [31:0] ord_qty, ord_price, ord_id;
  logic        doorbell_pulse, tx_ready;

  logic        cmd_valid, frame_builder_busy;
  logic [31:0] cmd_order_id, cmd_qty, cmd_price;
  logic [15:0] cmd_symbol;
  logic [7:0]  cmd_side;

  axi_lite_regbank u_regbank (
    .clk, .rst_n,
    .s_axi_awaddr, .s_axi_awvalid, .s_axi_awready,
    .s_axi_wdata,  .s_axi_wvalid,  .s_axi_wready,
    .s_axi_bresp,  .s_axi_bvalid,  .s_axi_bready,
    .s_axi_araddr, .s_axi_arvalid, .s_axi_arready,
    .s_axi_rdata,  .s_axi_rresp,   .s_axi_rvalid, .s_axi_rready,
    .ord_symbol, .ord_side, .ord_qty, .ord_price, .ord_id,
    .doorbell_pulse,
    .tx_ready
  );

  tx_order_latcher u_latcher (
    .clk, .rst_n,
    .ord_symbol, .ord_side, .ord_qty, .ord_price, .ord_id,
    .doorbell_pulse,
    .tx_ready,
    .cmd_valid, .cmd_order_id, .cmd_symbol, .cmd_side, .cmd_qty, .cmd_price,
    .frame_builder_busy
  );

  tx_frame_builder u_frame_builder (
    .clk, .rst_n,
    .cmd_valid, .cmd_order_id, .cmd_symbol, .cmd_side, .cmd_qty, .cmd_price,
    .frame_builder_busy,
    .m_axis_tdata, .m_axis_tvalid, .m_axis_tlast, .m_axis_tready
  );

endmodule
