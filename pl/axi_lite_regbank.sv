// TX-side slice of the shared AXI4-Lite register bank (Table 15, 0x40-0x54).
// Owner: Lucy

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
  // araddr[1:0] is intentionally unused: 32-bit-only slave, word decode
  /* verilator lint_off UNUSEDSIGNAL */
  input  logic [AXI_ADDR_WIDTH-1:0] s_axi_araddr,
  /* verilator lint_on UNUSEDSIGNAL */
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

  // ---------------------------------------------------------------------------
  // Address map (Table 15)
  // ---------------------------------------------------------------------------
  // This is a 32-bit-only AXI4-Lite slave, so addr[1:0] is ignored and decode
  // runs on the word index addr[AXI_ADDR_WIDTH-1:2]. The whole map fits in
  // 0x00-0x54, which is why the default address width is 8.
  localparam int WORD_W = AXI_ADDR_WIDTH - 2;

  localparam logic [WORD_W-1:0] REG_ORD_SYMBOL_SIDE = WORD_W'('h40 >> 2);
  localparam logic [WORD_W-1:0] REG_ORD_QTY         = WORD_W'('h44 >> 2);
  localparam logic [WORD_W-1:0] REG_ORD_PRICE       = WORD_W'('h48 >> 2);
  localparam logic [WORD_W-1:0] REG_ORD_ID          = WORD_W'('h4C >> 2);
  localparam logic [WORD_W-1:0] REG_DOORBELL        = WORD_W'('h50 >> 2);
  localparam logic [WORD_W-1:0] REG_TX_READY        = WORD_W'('h54 >> 2);

  localparam logic [1:0] RESP_OKAY = 2'b00;

  // Unmapped addresses (including the RX window 0x00-0x2C, which the RX owner
  // will fill in) must still complete: OKAY response, reads return 0. A slave
  // that stalls on a stray access hangs the PS's AXI master, which is a far
  // worse failure than silently ignoring a bad write.
  assign s_axi_bresp = RESP_OKAY;
  assign s_axi_rresp = RESP_OKAY;

  // ---------------------------------------------------------------------------
  // Write path: AW / W / B
  // ---------------------------------------------------------------------------
  // AW and W are independent channels; AXI does not order them against each
  // other, so the slave has to be able to sit holding one while waiting for the
  // other. That requirement is the entire reason this FSM exists.
  typedef enum logic [1:0] {
    W_IDLE,       // accepting either channel
    W_WAIT_DATA,  // address latched, waiting for W
    W_WAIT_ADDR,  // data latched, waiting for AW
    W_RESP        // both seen, driving BVALID
  } wr_state_e;

  wr_state_e wr_state;

  logic [AXI_ADDR_WIDTH-1:0] wr_addr_q;
  logic [AXI_DATA_WIDTH-1:0] wr_data_q;

  // Ready is combinational off the state register (never off *valid), so no
  // valid->ready path exists. AXI permits deasserting READY before a transfer,
  // which is what happens when we leave W_IDLE with only one channel accepted.
  // Gated by rst_n so nothing is accepted while in reset.
  assign s_axi_awready = rst_n && ((wr_state == W_IDLE) || (wr_state == W_WAIT_ADDR));
  assign s_axi_wready  = rst_n && ((wr_state == W_IDLE) || (wr_state == W_WAIT_DATA));

  // The cycle in which address and data are both known -- either both arrived
  // together in W_IDLE, or the second half just landed in a wait state.
  logic                      wr_commit;
  /* verilator lint_off UNUSEDSIGNAL */  // [1:0]: word decode, see araddr above
  logic [AXI_ADDR_WIDTH-1:0] wr_commit_addr;
  /* verilator lint_on UNUSEDSIGNAL */
  logic [AXI_DATA_WIDTH-1:0] wr_commit_data;

  always_comb begin
    wr_commit      = 1'b0;
    wr_commit_addr = wr_addr_q;
    wr_commit_data = wr_data_q;

    case (wr_state)
      W_IDLE: begin
        if (s_axi_awvalid && s_axi_wvalid) begin
          wr_commit      = 1'b1;
          wr_commit_addr = s_axi_awaddr;
          wr_commit_data = s_axi_wdata;
        end
      end
      W_WAIT_DATA: begin
        if (s_axi_wvalid) begin
          wr_commit      = 1'b1;
          wr_commit_data = s_axi_wdata;   // address came from wr_addr_q
        end
      end
      W_WAIT_ADDR: begin
        if (s_axi_awvalid) begin
          wr_commit      = 1'b1;
          wr_commit_addr = s_axi_awaddr;  // data came from wr_data_q
        end
      end
      default: ;  // W_RESP: nothing accepted until B is taken
    endcase
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wr_state       <= W_IDLE;
      wr_addr_q      <= '0;
      wr_data_q      <= '0;
      s_axi_bvalid   <= 1'b0;
      ord_symbol     <= '0;
      ord_side       <= '0;
      ord_qty        <= '0;
      ord_price      <= '0;
      ord_id         <= '0;
      doorbell_pulse <= 1'b0;
    end else begin
      // DOORBELL has no stored state: the pulse defaults back to 0 every cycle,
      // which is what makes it exactly one cycle wide no matter how long the PS
      // takes to accept B.
      doorbell_pulse <= 1'b0;

      case (wr_state)
        W_IDLE: begin
          if (s_axi_awvalid && s_axi_wvalid) begin
            wr_state <= W_RESP;
          end else if (s_axi_awvalid) begin
            wr_addr_q <= s_axi_awaddr;
            wr_state  <= W_WAIT_DATA;
          end else if (s_axi_wvalid) begin
            wr_data_q <= s_axi_wdata;
            wr_state  <= W_WAIT_ADDR;
          end
        end
        W_WAIT_DATA: if (s_axi_wvalid)   wr_state <= W_RESP;
        W_WAIT_ADDR: if (s_axi_awvalid)  wr_state <= W_RESP;
        W_RESP:      if (s_axi_bready) begin
                       wr_state     <= W_IDLE;
                       s_axi_bvalid <= 1'b0;
                     end
      endcase

      if (wr_commit) begin
        s_axi_bvalid <= 1'b1;

        case (wr_commit_addr[AXI_ADDR_WIDTH-1:2])
          // Unpacked here so nothing downstream ever sees the packed word.
          // Bits [31:24] are reserved and deliberately dropped.
          REG_ORD_SYMBOL_SIDE: begin
            ord_symbol <= wr_commit_data[15:0];
            ord_side   <= wr_commit_data[23:16];
          end
          REG_ORD_QTY:   ord_qty   <= wr_commit_data;
          REG_ORD_PRICE: ord_price <= wr_commit_data;
          REG_ORD_ID:    ord_id    <= wr_commit_data;
          // Write-1-to-pulse. Only bit 0 is defined; a write of 0 is a legal
          // no-op and must not launch an order.
          REG_DOORBELL:  doorbell_pulse <= wr_commit_data[0];
          // TX_READY is read-only; unmapped and read-only writes are accepted
          // and discarded (OKAY), never stalled.
          default: ;
        endcase
      end
    end
  end

  // ---------------------------------------------------------------------------
  // Read path: AR / R
  // ---------------------------------------------------------------------------
  typedef enum logic [0:0] { R_IDLE, R_RESP } rd_state_e;

  rd_state_e rd_state;

  assign s_axi_arready = rst_n && (rd_state == R_IDLE);

  logic [AXI_DATA_WIDTH-1:0] rd_data_next;

  always_comb begin
    case (s_axi_araddr[AXI_ADDR_WIDTH-1:2])
      REG_TX_READY: rd_data_next = {{(AXI_DATA_WIDTH-1){1'b0}}, tx_ready};
      // Table 15 marks 0x40-0x4C write-only. Readback is provided for
      // bring-up only -- AXI-Lite writes are posted, so being able to confirm
      // the PS's five order-field writes actually landed is worth the mux.
      // PS firmware must not depend on it.
      REG_ORD_SYMBOL_SIDE: rd_data_next = {8'h00, ord_side, ord_symbol};
      REG_ORD_QTY:         rd_data_next = ord_qty;
      REG_ORD_PRICE:       rd_data_next = ord_price;
      REG_ORD_ID:          rd_data_next = ord_id;
      // DOORBELL reads as 0 (it stores nothing) and, critically, reading it
      // must not pulse. Same for the not-yet-implemented RX window.
      default:             rd_data_next = '0;
    endcase
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rd_state     <= R_IDLE;
      s_axi_rvalid <= 1'b0;
      s_axi_rdata  <= '0;
    end else begin
      case (rd_state)
        R_IDLE: begin
          if (s_axi_arvalid) begin
            s_axi_rdata  <= rd_data_next;  // sampled at AR accept
            s_axi_rvalid <= 1'b1;
            rd_state     <= R_RESP;
          end
        end
        R_RESP: begin
          if (s_axi_rready) begin
            s_axi_rvalid <= 1'b0;
            rd_state     <= R_IDLE;
          end
        end
      endcase
    end
  end

endmodule
