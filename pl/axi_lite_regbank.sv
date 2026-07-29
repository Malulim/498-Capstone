// TX-side slice of the shared AXI4-Lite register bank (Table 15, 0x40-0x54).
// Owner: TBD

module axi_lite_regbank #(
  parameter int AXI_ADDR_WIDTH = 8,
  parameter int AXI_DATA_WIDTH = 32
)(
  input  logic clk,
  input  logic rst_n,

  // AXI4-Lite slave port (PS -> PL)
  input  logic [AXI_ADDR_WIDTH-1:0] s_axi_awaddr,
  input  logic                      s_axi_awvalid,
  output logic                      s_axi_awready,
  input  logic [AXI_DATA_WIDTH-1:0] s_axi_wdata,
  input  logic                      s_axi_wvalid,
  output logic                      s_axi_wready,
  output logic [1:0]                s_axi_bresp,
  output logic                      s_axi_bvalid,
  input  logic                      s_axi_bready,
  input  logic [AXI_ADDR_WIDTH-1:0] s_axi_araddr,
  input  logic                      s_axi_arvalid,
  output logic                      s_axi_arready,
  output logic [AXI_DATA_WIDTH-1:0] s_axi_rdata,
  output logic [1:0]                s_axi_rresp,
  output logic                      s_axi_rvalid,
  input  logic                      s_axi_rready,

  // Plain register interface toward tx_order_latcher (0x40-0x4C unpacked)
  output logic [15:0] ord_symbol,
  output logic [7:0]  ord_side,
  output logic [31:0] ord_qty,
  output logic [31:0] ord_price,
  output logic [31:0] ord_id,

  // 0x50 DOORBELL: write-1-to-pulse, no persistent stored state
  output logic         doorbell_pulse,

  // 0x54 TX_READY: fed back from tx_order_latcher, exposed read-only to PS
  input  logic          tx_ready
);

  // TODO(owner):
  // - [ ] Hand-write AXI4-Lite write FSM (AW/W/B) and read FSM (AR/R), no wizard.
  // - [ ] Address decode: 0x40 ORD_SYMBOL_SIDE, 0x44 ORD_QTY, 0x48 ORD_PRICE,
  //       0x4C ORD_ID, 0x50 DOORBELL, 0x54 TX_READY.
  // - [ ] Split ORD_SYMBOL_SIDE into ord_symbol[15:0] / ord_side[23:16].
  // - [ ] DOORBELL: write-1-to-pulse, 1 cycle, no stored/clearable bit.
  //       A write of 0 produces no pulse.
  // - [ ] TX_READY read data = {31'b0, tx_ready}.
  // - [ ] Reset (rst_n low): awready/wready/arready = 0, bvalid/rvalid = 0,
  //       doorbell_pulse = 0, ord_* = 0.
  // - [ ] Unmapped address: respond, don't hang. bresp/rresp = OKAY (2'b00),
  //       reads return 0.

endmodule
