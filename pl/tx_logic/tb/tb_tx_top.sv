`timescale 1ns/1ps

// Integration testbench for tx_top (README "集成测试:黄金帧比对").
//
// Drives the real PS sequence -- four AXI-Lite order-field writes, then
// DOORBELL -- and compares every byte that comes out of the AXI4-Stream master
// against the Python oracle. What this covers that no unit test can: the
// regbank's one-cycle pulse actually reaching the latcher, the latcher's
// captured fields actually reaching the serializer, and the builder's busy
// signal actually closing the doorbell window back at the regbank.
//
// Requires golden_frame_0.hex / golden_frame_1.hex in the working directory:
//   python3 scripts/generate_golden_frames.py <dir>
//   ... then run the simulation binary from <dir>.
module tb_tx_top;
  localparam time CLK_PERIOD  = 8ns;
  localparam time SETTLE      = 1ns;   // let combinational outputs settle before sampling
  localparam int  FRAME_BYTES = 58;

  // Table 15, TX window
  localparam logic [7:0] ADDR_ORD_SYMBOL_SIDE = 8'h40;
  localparam logic [7:0] ADDR_ORD_QTY         = 8'h44;
  localparam logic [7:0] ADDR_ORD_PRICE       = 8'h48;
  localparam logic [7:0] ADDR_ORD_ID          = 8'h4C;
  localparam logic [7:0] ADDR_DOORBELL        = 8'h50;
  localparam logic [7:0] ADDR_TX_READY        = 8'h54;

  // MUST mirror main() in scripts/generate_golden_frames.py -- these are the
  // inputs that produced golden_frame_0.hex / golden_frame_1.hex.
  localparam logic [31:0] C0_ID    = 32'd10001;
  localparam logic [15:0] C0_SYM   = 16'h0001;
  localparam logic [7:0]  C0_SIDE  = 8'd1;
  localparam logic [31:0] C0_QTY   = 32'd100;
  localparam logic [31:0] C0_PRICE = 32'd1505000;

  localparam logic [31:0] C1_ID    = 32'd10002;
  localparam logic [15:0] C1_SYM   = 16'h0002;
  localparam logic [7:0]  C1_SIDE  = 8'd2;
  localparam logic [31:0] C1_QTY   = 32'd50;
  localparam logic [31:0] C1_PRICE = 32'd3102000;

  logic clk   = 1'b0;
  // rst_n is the DUT's async reset and also the `disable iff` guard on the
  // assertions below, which is standard SVA practice but reads to Verilator as
  // a signal flopped both ways.
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n = 1'b1;
  /* verilator lint_on SYNCASYNCNET */

  initial forever #(CLK_PERIOD / 2) clk = ~clk;

  // AXI4-Lite master (the PS side)
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

  // AXI4-Stream slave (standing in for TEMAC TX)
  logic [7:0]  m_axis_tdata;
  logic        m_axis_tvalid;
  logic        m_axis_tlast;
  logic        m_axis_tready = 1'b1;

  tx_top dut (
    .clk, .rst_n,
    .s_axi_awaddr, .s_axi_awvalid, .s_axi_awready,
    .s_axi_wdata,  .s_axi_wvalid,  .s_axi_wready,
    .s_axi_bresp,  .s_axi_bvalid,  .s_axi_bready,
    .s_axi_araddr, .s_axi_arvalid, .s_axi_arready,
    .s_axi_rdata,  .s_axi_rresp,   .s_axi_rvalid, .s_axi_rready,
    .m_axis_tdata, .m_axis_tvalid, .m_axis_tlast, .m_axis_tready
  );

  int pass_count = 0;
  int fail_count = 0;

  // ---------------------------------------------------------------------------
  // The internal contract this testbench owns, because it is a property of the
  // wiring rather than of any one module: whenever the latcher hands over a
  // command, the builder must ALREADY be reporting busy in that same cycle.
  //
  // A registered busy leaves exactly one cycle of hole. Stimulus alone cannot
  // reach it from here -- an AXI-Lite write takes at least three cycles, so the
  // PS physically cannot place two doorbell pulses one cycle apart -- so a
  // black-box test would pass a broken design. Hence the assertion.
  // ---------------------------------------------------------------------------
  assert property (@(posedge clk) disable iff (!rst_n)
    dut.cmd_valid |-> dut.frame_builder_busy)
    else $fatal(1, "busy is not asserted in the cmd_valid cycle -- doorbell mask has a one-cycle hole");

  // Corollary: while a frame is on the wire, TX_READY must read 0 the whole
  // time, not just when the PS happens to look.
  assert property (@(posedge clk) disable iff (!rst_n)
    m_axis_tvalid |-> !dut.tx_ready)
    else $fatal(1, "TX_READY reads 1 while a frame is still being transmitted");

  task automatic check(input logic condition, input string message);
    if (condition) begin
      pass_count++;
    end else begin
      $display("  FAIL: %s (t=%0t)", message, $time);
      fail_count++;
    end
  endtask

  // ---------------------------------------------------------------------------
  // AXI4-Stream sink. Runs for the whole simulation rather than being started
  // per frame: a frame begins about two cycles after the DOORBELL write
  // completes, so a collector launched afterwards would race the first byte.
  // ---------------------------------------------------------------------------
  logic [7:0] rx_frame [0:63];
  int         rx_len     = 0;
  int         frames_seen = 0;
  int         stray_bytes = 0;

  initial begin
    int n;
    n = 0;
    forever begin
      @(posedge clk);
      if (rst_n && m_axis_tvalid && m_axis_tready) begin
        if (n < 64) begin
          rx_frame[n] = m_axis_tdata;
        end else begin
          stray_bytes++;      // frame ran past the buffer: tlast never came
        end
        n++;
        if (m_axis_tlast) begin
          rx_len = n;
          frames_seen++;
          n = 0;
        end
      end
    end
  end

  // Two flat arrays rather than one 2-D array: $readmemh will not load into a
  // slice of a multidimensional unpacked array.
  logic [7:0] golden_0 [0:FRAME_BYTES-1];
  logic [7:0] golden_1 [0:FRAME_BYTES-1];

  initial begin
    $readmemh("golden_frame_0.hex", golden_0);
    $readmemh("golden_frame_1.hex", golden_1);
  end

  task automatic compare_frame(input int which, input string name);
    int mismatches;
    logic [7:0] expected;
    mismatches = 0;
    check(rx_len == FRAME_BYTES, {name, ": frame is exactly 58 bytes"});
    check(stray_bytes == 0, {name, ": tlast arrived (no runaway frame)"});
    for (int i = 0; i < FRAME_BYTES; i++) begin
      expected = (which == 0) ? golden_0[i] : golden_1[i];
      if (rx_frame[i] !== expected) begin
        if (mismatches < 8) begin
          $display("  FAIL: %s byte[%02d] got 0x%02X expected 0x%02X",
                   name, i, rx_frame[i], expected);
        end
        mismatches++;
      end
    end
    if (mismatches == 0) begin
      $display("  PASS: %s -- all 58 bytes match golden_frame_%0d", name, which);
      pass_count++;
    end else begin
      $display("  FAIL: %s -- %0d byte mismatches vs golden_frame_%0d", name, mismatches, which);
      fail_count++;
    end
  endtask

  // ---------------------------------------------------------------------------
  // AXI4-Lite master tasks. Deliberately minimal -- the split-phase AW/W cases
  // and the response-channel stalls are covered by tb_axi_lite_regbank; here the
  // register bank only has to carry traffic.
  // ---------------------------------------------------------------------------
  task automatic axi_write(input logic [7:0] addr, input logic [31:0] data);
    @(negedge clk);
    s_axi_awaddr  = addr;
    s_axi_awvalid = 1'b1;
    s_axi_wdata   = data;
    s_axi_wvalid  = 1'b1;
    #SETTLE;
    fork
      begin : aw_phase
        while (!s_axi_awready) begin @(negedge clk); #SETTLE; end
        @(posedge clk);
        @(negedge clk);
        s_axi_awvalid = 1'b0;
      end
      begin : w_phase
        while (!s_axi_wready) begin @(negedge clk); #SETTLE; end
        @(posedge clk);
        @(negedge clk);
        s_axi_wvalid = 1'b0;
      end
    join
    #SETTLE;
    s_axi_bready = 1'b1;
    while (!s_axi_bvalid) begin @(negedge clk); #SETTLE; end
    check(s_axi_bresp === 2'b00, "write response is OKAY");
    @(posedge clk);
    @(negedge clk);
    s_axi_bready = 1'b0;
  endtask

  task automatic axi_read(input logic [7:0] addr, output logic [31:0] data);
    @(negedge clk);
    s_axi_araddr  = addr;
    s_axi_arvalid = 1'b1;
    #SETTLE;
    while (!s_axi_arready) begin @(negedge clk); #SETTLE; end
    @(posedge clk);
    @(negedge clk);
    s_axi_arvalid = 1'b0;
    s_axi_rready  = 1'b1;
    #SETTLE;
    while (!s_axi_rvalid) begin @(negedge clk); #SETTLE; end
    data = s_axi_rdata;
    check(s_axi_rresp === 2'b00, "read response is OKAY");
    @(posedge clk);
    @(negedge clk);
    s_axi_rready = 1'b0;
  endtask

  // The PS egress sequence from README 3.1.3.2: payload fields first, doorbell
  // last. ORD_SYMBOL_SIDE packs symbol in [15:0] and side in [23:16].
  task automatic write_order_fields(input logic [15:0] sym, input logic [7:0] side,
                                    input logic [31:0] qty, input logic [31:0] price,
                                    input logic [31:0] id);
    axi_write(ADDR_ORD_SYMBOL_SIDE, {8'h00, side, sym});
    axi_write(ADDR_ORD_QTY,   qty);
    axi_write(ADDR_ORD_PRICE, price);
    axi_write(ADDR_ORD_ID,    id);
  endtask

  task automatic ring_doorbell();
    axi_write(ADDR_DOORBELL, 32'h0000_0001);
  endtask

  initial begin
    #500us;
    $fatal(1, "TIMEOUT -- a frame or an AXI handshake never completed");
  end

  logic [31:0] rd;

  initial begin
    // -------------------------------------------------------------------------
    // Reset
    // -------------------------------------------------------------------------
    $display("\n[T1] Reset");
    rst_n = 1'b0;
    repeat (4) @(negedge clk);
    #SETTLE;
    check(m_axis_tvalid === 1'b0, "tvalid low during reset");
    check(m_axis_tlast  === 1'b0, "tlast low during reset");
    rst_n = 1'b1;
    repeat (2) @(negedge clk);

    axi_read(ADDR_TX_READY, rd);
    check(rd === 32'h0000_0001, "TX_READY reads 1 when idle");

    // -------------------------------------------------------------------------
    // Order 0: the plain end-to-end path.
    // -------------------------------------------------------------------------
    $display("\n[T2] Order 0 end to end");
    write_order_fields(C0_SYM, C0_SIDE, C0_QTY, C0_PRICE, C0_ID);
    check(frames_seen == 0, "no frame is emitted before the doorbell");
    ring_doorbell();
    wait (frames_seen == 1);
    compare_frame(0, "order 0");

    repeat (4) @(negedge clk);
    axi_read(ADDR_TX_READY, rd);
    check(rd === 32'h0000_0001, "TX_READY returns to 1 once the frame is out");

    // -------------------------------------------------------------------------
    // Order 1, with the sink stalling mid-frame. Backpressure is tested in the
    // builder's unit test too, but only here does it run with the AXI-Lite side
    // still live, which is what the TEMAC will actually look like.
    // -------------------------------------------------------------------------
    $display("\n[T3] Order 1 with mid-frame backpressure");
    write_order_fields(C1_SYM, C1_SIDE, C1_QTY, C1_PRICE, C1_ID);
    ring_doorbell();

    repeat (12) @(negedge clk);
    m_axis_tready = 1'b0;
    check(frames_seen == 1, "stall lands while the frame is still in flight");
    repeat (9) @(negedge clk);
    m_axis_tready = 1'b1;

    wait (frames_seen == 2);
    compare_frame(1, "order 1 under backpressure");

    // -------------------------------------------------------------------------
    // The safety invariant: a doorbell that arrives mid-frame is dropped, and
    // the fields underneath it are NOT allowed to leak into the frame already
    // on the wire. This is the one behaviour that only exists as a property of
    // the three modules wired together -- the regbank still pulses, the latcher
    // still masks, and the builder keeps serialising the old command.
    // -------------------------------------------------------------------------
    $display("\n[T4] Doorbell during a frame is dropped, not spliced");
    write_order_fields(C0_SYM, C0_SIDE, C0_QTY, C0_PRICE, C0_ID);
    ring_doorbell();
    repeat (4) @(negedge clk);

    axi_read(ADDR_TX_READY, rd);
    check(rd === 32'h0000_0000, "TX_READY reads 0 while a frame is in flight");

    // Overwrite every order register with the *other* order and ring again.
    write_order_fields(C1_SYM, C1_SIDE, C1_QTY, C1_PRICE, C1_ID);
    check(frames_seen == 2, "the competing writes land mid-frame");
    ring_doorbell();
    check(frames_seen == 2, "the competing doorbell also lands mid-frame");

    wait (frames_seen == 3);
    compare_frame(0, "frame 3 (masked doorbell must not corrupt it)");

    // And it must not resurface once the builder frees up.
    repeat (120) @(negedge clk);
    check(frames_seen == 3, "the dropped doorbell is never replayed");

    axi_read(ADDR_TX_READY, rd);
    check(rd === 32'h0000_0001, "TX_READY is 1 again after the masked doorbell");

    // -------------------------------------------------------------------------
    // Not wedged: a normal submission still works afterwards. The order
    // registers still hold order 1 from the discarded attempt, so this also
    // shows the fields survived the drop intact.
    // -------------------------------------------------------------------------
    $display("\n[T5] Normal submission after a dropped doorbell");
    ring_doorbell();
    wait (frames_seen == 4);
    compare_frame(1, "order 1 resubmitted");

    $display("\n========================================");
    $display("frames observed: %0d   checks passed: %0d   failed: %0d",
             frames_seen, pass_count, fail_count);
    $display("========================================");
    if (fail_count != 0) $fatal(1, "tb_tx_top: %0d failures", fail_count);
    $display("PASS: tx_top integration");
    $finish;
  end

endmodule
