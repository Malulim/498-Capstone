`timescale 1ns/1ps

// Unit testbench for axi_lite_regbank (Table 15, TX window 0x40-0x54).
// Hand-rolled AXI4-Lite master tasks -- no VIP/BFM, no constrained-random.
module tb_axi_lite_regbank;
  localparam time CLK_PERIOD = 8ns;
  localparam time SETTLE     = 1ns;  // let combinational outputs settle before sampling

  localparam logic [7:0] ADDR_ORD_SYMBOL_SIDE = 8'h40;
  localparam logic [7:0] ADDR_ORD_QTY         = 8'h44;
  localparam logic [7:0] ADDR_ORD_PRICE       = 8'h48;
  localparam logic [7:0] ADDR_ORD_ID          = 8'h4C;
  localparam logic [7:0] ADDR_DOORBELL        = 8'h50;
  localparam logic [7:0] ADDR_TX_READY        = 8'h54;
  localparam logic [7:0] ADDR_UNMAPPED_R      = 8'h1C;  // RX window, not implemented yet
  localparam logic [7:0] ADDR_UNMAPPED_W      = 8'h08;  // read-only RX snapshot slot

  logic clk = 1'b0;
  logic rst_n = 1'b1;

  logic [7:0]  s_axi_awaddr  = '0;
  logic        s_axi_awvalid = 1'b0;
  logic        s_axi_awready;
  logic [31:0] s_axi_wdata   = '0;
  logic        s_axi_wvalid  = 1'b0;
  logic        s_axi_wready;
  logic [1:0]  s_axi_bresp;
  logic        s_axi_bvalid;
  logic        s_axi_bready  = 1'b0;
  logic [7:0]  s_axi_araddr  = '0;
  logic        s_axi_arvalid = 1'b0;
  logic        s_axi_arready;
  logic [31:0] s_axi_rdata;
  logic [1:0]  s_axi_rresp;
  logic        s_axi_rvalid;
  logic        s_axi_rready  = 1'b0;

  logic [15:0] ord_symbol;
  logic [7:0]  ord_side;
  logic [31:0] ord_qty;
  logic [31:0] ord_price;
  logic [31:0] ord_id;
  logic        doorbell_pulse;
  logic        tx_ready = 1'b1;

  axi_lite_regbank dut (
    .clk,
    .rst_n,
    .s_axi_awaddr,  .s_axi_awvalid, .s_axi_awready,
    .s_axi_wdata,   .s_axi_wvalid,  .s_axi_wready,
    .s_axi_bresp,   .s_axi_bvalid,  .s_axi_bready,
    .s_axi_araddr,  .s_axi_arvalid, .s_axi_arready,
    .s_axi_rdata,   .s_axi_rresp,   .s_axi_rvalid, .s_axi_rready,
    .ord_symbol, .ord_side, .ord_qty, .ord_price, .ord_id,
    .doorbell_pulse,
    .tx_ready
  );

  initial forever #(CLK_PERIOD / 2) clk = ~clk;

  task automatic check(input logic condition, input string message);
    if (!condition) begin
      $fatal(1, "FAIL: %s (t=%0t)", message, $time);
    end
  endtask

  // ---------------------------------------------------------------------------
  // Doorbell monitor: counts pulses and independently proves the pulse is never
  // wider than one cycle. A two-cycle pulse would look like two orders to the
  // latcher, so width is not something the write tasks can be trusted to check.
  // ---------------------------------------------------------------------------
  int   doorbell_count = 0;
  logic doorbell_prev  = 1'b0;

  always @(posedge clk) begin
    if (doorbell_pulse) begin
      doorbell_count <= doorbell_count + 1;
      if (doorbell_prev) $fatal(1, "FAIL: doorbell_pulse held for more than one cycle (t=%0t)", $time);
    end
    doorbell_prev <= doorbell_pulse;
  end

  // Testbench-side shadow of what the register bank should be holding.
  logic [15:0] exp_symbol = '0;
  logic [7:0]  exp_side   = '0;
  logic [31:0] exp_qty    = '0;
  logic [31:0] exp_price  = '0;
  logic [31:0] exp_id     = '0;

  task automatic check_ord(input string ctx);
    check(ord_symbol === exp_symbol, {ctx, ": ord_symbol"});
    check(ord_side   === exp_side,   {ctx, ": ord_side"});
    check(ord_qty    === exp_qty,    {ctx, ": ord_qty"});
    check(ord_price  === exp_price,  {ctx, ": ord_price"});
    check(ord_id     === exp_id,     {ctx, ": ord_id"});
  endtask

  // ---------------------------------------------------------------------------
  // AXI4-Lite write. aw_lead > 0 puts AW that many cycles ahead of W, < 0 puts W
  // ahead of AW, 0 drives both in the same cycle. b_delay holds BREADY low for
  // that many extra cycles once BVALID is up.
  // ---------------------------------------------------------------------------
  task automatic axi_write(input logic [7:0] addr, input logic [31:0] data,
                           input int aw_lead, input int b_delay);
    int aw_wait, w_wait;
    aw_wait = (aw_lead > 0) ? 0 : -aw_lead;
    w_wait  = (aw_lead > 0) ? aw_lead : 0;

    fork
      begin : drive_aw
        repeat (aw_wait + 1) @(negedge clk);
        s_axi_awaddr  = addr;
        s_axi_awvalid = 1'b1;
        #SETTLE;
        while (!s_axi_awready) begin
          @(negedge clk);
          #SETTLE;
        end
        @(posedge clk);       // AW transfer lands here
        @(negedge clk);
        s_axi_awvalid = 1'b0;
      end
      begin : drive_w
        repeat (w_wait + 1) @(negedge clk);
        s_axi_wdata  = data;
        s_axi_wvalid = 1'b1;
        #SETTLE;
        while (!s_axi_wready) begin
          @(negedge clk);
          #SETTLE;
        end
        @(posedge clk);       // W transfer lands here
        @(negedge clk);
        s_axi_wvalid = 1'b0;
      end
    join

    // Both halves are in, so the bank has committed and BVALID is up.
    #SETTLE;
    check(s_axi_bvalid === 1'b1, "bvalid asserts once address and data are both in");
    check(s_axi_bresp  === 2'b00, "bresp is OKAY");

    repeat (b_delay) begin
      @(negedge clk);
      #SETTLE;
      check(s_axi_bvalid === 1'b1, "bvalid holds while bready is low");
      check(s_axi_bresp  === 2'b00, "bresp holds OKAY while bready is low");
    end

    s_axi_bready = 1'b1;
    @(posedge clk);
    @(negedge clk);
    s_axi_bready = 1'b0;
    #SETTLE;
    check(s_axi_bvalid === 1'b0, "bvalid drops after bready");
  endtask

  // ---------------------------------------------------------------------------
  // AXI4-Lite read. r_delay holds RREADY low for that many extra cycles once
  // RVALID is up, which also checks RDATA stability under stall.
  // ---------------------------------------------------------------------------
  task automatic axi_read(input logic [7:0] addr, output logic [31:0] data,
                          input int r_delay);
    logic [31:0] held;

    @(negedge clk);
    s_axi_araddr  = addr;
    s_axi_arvalid = 1'b1;
    #SETTLE;
    while (!s_axi_arready) begin
      @(negedge clk);
      #SETTLE;
    end
    @(posedge clk);           // AR transfer lands here
    @(negedge clk);
    s_axi_arvalid = 1'b0;
    #SETTLE;
    check(s_axi_rvalid === 1'b1, "rvalid asserts the cycle after AR is accepted");
    check(s_axi_rresp  === 2'b00, "rresp is OKAY");
    held = s_axi_rdata;

    repeat (r_delay) begin
      @(negedge clk);
      #SETTLE;
      check(s_axi_rvalid === 1'b1, "rvalid holds while rready is low");
      check(s_axi_rdata  === held, "rdata holds while rready is low");
    end

    data = s_axi_rdata;
    s_axi_rready = 1'b1;
    @(posedge clk);
    @(negedge clk);
    s_axi_rready = 1'b0;
    #SETTLE;
    check(s_axi_rvalid === 1'b0, "rvalid drops after rready");
  endtask

  // Nothing in this bank is allowed to stall the PS's AXI master. If any task
  // spins forever waiting on a ready/valid, this is what reports it.
  initial begin
    #200us;
    $fatal(1, "FAIL: testbench timeout -- a channel never completed its handshake");
  end

  logic [31:0] rdata;
  int          count_before;

  initial begin
    // -------------------------------------------------------------------------
    // Reset: nothing accepted, nothing outstanding, no phantom doorbell.
    // -------------------------------------------------------------------------
    #1;
    rst_n = 1'b0;
    #1;
    check(s_axi_awready  === 1'b0, "reset holds awready low");
    check(s_axi_wready   === 1'b0, "reset holds wready low");
    check(s_axi_arready  === 1'b0, "reset holds arready low");
    check(s_axi_bvalid   === 1'b0, "reset holds bvalid low");
    check(s_axi_rvalid   === 1'b0, "reset holds rvalid low");
    check(doorbell_pulse === 1'b0, "reset holds doorbell_pulse low");
    check_ord("reset clears order fields");

    @(negedge clk);
    rst_n = 1'b1;
    #SETTLE;
    check(s_axi_awready === 1'b1, "bank accepts writes once out of reset");
    check(s_axi_arready === 1'b1, "bank accepts reads once out of reset");

    // -------------------------------------------------------------------------
    // ORD_SYMBOL_SIDE unpacking: symbol in [15:0], side in [23:16], [31:24]
    // reserved and dropped. Downstream must never see the packed word.
    // -------------------------------------------------------------------------
    axi_write(ADDR_ORD_SYMBOL_SIDE, 32'h0002_0001, 0, 0);
    exp_symbol = 16'h0001;
    exp_side   = 8'h02;
    check_ord("ORD_SYMBOL_SIDE = 0x00020001");

    // Reserved bits must not bleed into ord_side, and a nonzero side must not
    // be widened past 8 bits.
    axi_write(ADDR_ORD_SYMBOL_SIDE, 32'hFF9A_5566, 0, 0);
    exp_symbol = 16'h5566;
    exp_side   = 8'h9A;
    check_ord("ORD_SYMBOL_SIDE drops reserved bits [31:24]");

    // -------------------------------------------------------------------------
    // The three flat 32-bit order fields.
    // -------------------------------------------------------------------------
    axi_write(ADDR_ORD_QTY, 32'd100, 0, 0);
    exp_qty = 32'd100;
    check_ord("ORD_QTY");

    axi_write(ADDR_ORD_PRICE, 32'd1_505_000, 0, 0);
    exp_price = 32'd1_505_000;
    check_ord("ORD_PRICE");

    axi_write(ADDR_ORD_ID, 32'd10_001, 0, 0);
    exp_id = 32'd10_001;
    check_ord("ORD_ID");

    // -------------------------------------------------------------------------
    // DOORBELL: write-1-to-pulse, exactly one cycle, no stored state, and it
    // must not disturb the order fields it launches.
    // -------------------------------------------------------------------------
    count_before = doorbell_count;
    axi_write(ADDR_DOORBELL, 32'h0000_0001, 0, 0);
    check(doorbell_count == count_before + 1, "doorbell write produces exactly one pulse");
    check_ord("doorbell write leaves order fields untouched");

    // Let several cycles pass: a stored/latched doorbell bit would keep pulsing
    // or would stay readable.
    repeat (5) @(negedge clk);
    check(doorbell_count == count_before + 1, "doorbell does not re-pulse after the write");
    check(doorbell_pulse === 1'b0, "doorbell_pulse returns to 0");
    axi_read(ADDR_DOORBELL, rdata, 0);
    check(rdata === 32'h0, "DOORBELL reads back 0 -- it stores nothing");
    check(doorbell_count == count_before + 1, "reading DOORBELL does not launch an order");

    // A write of 0 is a legal no-op.
    count_before = doorbell_count;
    axi_write(ADDR_DOORBELL, 32'h0000_0000, 0, 0);
    repeat (3) @(negedge clk);
    check(doorbell_count == count_before, "doorbell write of 0 produces no pulse");

    // -------------------------------------------------------------------------
    // AW and W on separate cycles, both orders. This is the only reason the
    // write FSM exists, so it gets tested on a plain register AND on DOORBELL
    // (where a mis-latched address would fire a phantom order).
    // -------------------------------------------------------------------------
    axi_write(ADDR_ORD_QTY, 32'hDEAD_BEEF, 3, 0);   // AW three cycles ahead of W
    exp_qty = 32'hDEAD_BEEF;
    check_ord("AW leads W by 3");

    axi_write(ADDR_ORD_PRICE, 32'hFEED_FACE, -3, 0);  // W three cycles ahead of AW
    exp_price = 32'hFEED_FACE;
    check_ord("W leads AW by 3");

    count_before = doorbell_count;
    axi_write(ADDR_DOORBELL, 32'h1, 2, 0);
    check(doorbell_count == count_before + 1, "AW-first doorbell produces exactly one pulse");

    count_before = doorbell_count;
    axi_write(ADDR_DOORBELL, 32'h1, -2, 0);
    check(doorbell_count == count_before + 1, "W-first doorbell produces exactly one pulse");
    check_ord("split-phase doorbells leave order fields untouched");

    // -------------------------------------------------------------------------
    // A slow PS on the B channel must not stretch the doorbell pulse.
    // -------------------------------------------------------------------------
    count_before = doorbell_count;
    axi_write(ADDR_DOORBELL, 32'h1, 0, 4);          // BREADY held low 4 cycles
    check(doorbell_count == count_before + 1, "delayed bready still yields one pulse");

    // -------------------------------------------------------------------------
    // TX_READY is read-only and reflects the latcher live, both polarities.
    // -------------------------------------------------------------------------
    tx_ready = 1'b1;
    axi_read(ADDR_TX_READY, rdata, 0);
    check(rdata === 32'h0000_0001, "TX_READY reads {31'b0, 1}");

    tx_ready = 1'b0;
    axi_read(ADDR_TX_READY, rdata, 0);
    check(rdata === 32'h0000_0000, "TX_READY reads {31'b0, 0}");
    tx_ready = 1'b1;

    // Writing a read-only register is accepted and discarded, never stalled.
    axi_write(ADDR_TX_READY, 32'hFFFF_FFFF, 0, 0);
    check_ord("write to read-only TX_READY has no side effect");

    // -------------------------------------------------------------------------
    // Unmapped addresses: respond OKAY, read 0, never hang. The RX window
    // 0x00-0x2C is unmapped until the RX owner fills it in, and the PS will be
    // poking at it during bring-up.
    // -------------------------------------------------------------------------
    axi_read(ADDR_UNMAPPED_R, rdata, 0);
    check(rdata === 32'h0, "unmapped read returns 0 with OKAY");

    count_before = doorbell_count;
    axi_write(ADDR_UNMAPPED_W, 32'hA5A5_A5A5, 0, 0);
    check_ord("unmapped write has no side effect");
    check(doorbell_count == count_before, "unmapped write does not pulse the doorbell");

    // -------------------------------------------------------------------------
    // Stalled read channel, and a full PS-style order sequence back to back
    // (four field writes then the doorbell) with no idle recovery time.
    // -------------------------------------------------------------------------
    axi_read(ADDR_ORD_ID, rdata, 4);
    check(rdata === exp_id, "readback under RREADY stall");

    count_before = doorbell_count;
    axi_write(ADDR_ORD_SYMBOL_SIDE, 32'h0002_0002, 0, 0);
    axi_write(ADDR_ORD_QTY,   32'd50, 0, 0);
    axi_write(ADDR_ORD_PRICE, 32'd3_102_000, 0, 0);
    axi_write(ADDR_ORD_ID,    32'd10_002, 0, 0);
    axi_write(ADDR_DOORBELL,  32'h1, 0, 0);
    exp_symbol = 16'h0002;
    exp_side   = 8'h02;
    exp_qty    = 32'd50;
    exp_price  = 32'd3_102_000;
    exp_id     = 32'd10_002;
    check_ord("full order sequence, consecutive writes");
    check(doorbell_count == count_before + 1, "one pulse for the whole order sequence");

    // Debug readback of the (Table 15 write-only) order fields.
    axi_read(ADDR_ORD_SYMBOL_SIDE, rdata, 0);
    check(rdata === {8'h00, exp_side, exp_symbol}, "ORD_SYMBOL_SIDE readback repacks the word");
    axi_read(ADDR_ORD_QTY, rdata, 0);
    check(rdata === exp_qty, "ORD_QTY readback");
    axi_read(ADDR_ORD_PRICE, rdata, 0);
    check(rdata === exp_price, "ORD_PRICE readback");
    axi_read(ADDR_ORD_ID, rdata, 0);
    check(rdata === exp_id, "ORD_ID readback");

    // -------------------------------------------------------------------------
    // Reset with a half-finished write in flight: AW accepted, W never sent.
    // The dropped address must not resurface as a phantom write (least of all a
    // phantom doorbell) after reset releases.
    // -------------------------------------------------------------------------
    @(negedge clk);
    s_axi_awaddr  = ADDR_DOORBELL;
    s_axi_awvalid = 1'b1;
    #SETTLE;
    check(s_axi_awready === 1'b1, "idle bank accepts the address phase");
    @(posedge clk);
    @(negedge clk);
    s_axi_awvalid = 1'b0;
    #SETTLE;
    check(s_axi_awready === 1'b0, "awready drops once the address is taken");
    check(s_axi_wready  === 1'b1, "wready stays up while waiting for the data phase");
    check(s_axi_bvalid  === 1'b0, "no response before the data phase arrives");

    count_before = doorbell_count;
    rst_n = 1'b0;
    #SETTLE;
    check(s_axi_awready === 1'b0, "mid-write reset drops awready");
    check(s_axi_wready  === 1'b0, "mid-write reset drops wready");
    check(s_axi_bvalid  === 1'b0, "mid-write reset drops bvalid");
    exp_symbol = '0;
    exp_side   = '0;
    exp_qty    = '0;
    exp_price  = '0;
    exp_id     = '0;
    check_ord("mid-write reset clears order fields");

    @(negedge clk);
    rst_n = 1'b1;
    repeat (4) @(negedge clk);
    check(doorbell_count == count_before, "aborted write does not replay as a doorbell");
    check_ord("aborted write leaves order fields at reset values");

    // Recovery: a clean write after all that still works.
    axi_write(ADDR_ORD_QTY, 32'd777, 0, 0);
    exp_qty = 32'd777;
    check_ord("bank recovers after mid-write reset");

    $display("PASS: axi_lite_regbank (%0d doorbell pulses observed)", doorbell_count);
    $finish;
  end

endmodule
