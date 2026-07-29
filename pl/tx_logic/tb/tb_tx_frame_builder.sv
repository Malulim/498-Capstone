// tb_tx_frame_builder.sv — final clean version
`timescale 1ns/1ps

module tb_tx_frame_builder;

    logic clk = 0;
    always #4 clk <= ~clk;

    logic rst_n;
    initial begin rst_n = 0; repeat(4) @(posedge clk); rst_n = 1; end

    logic        cmd_valid  = 0;
    logic [15:0] cmd_symbol = 0;
    logic [7:0]  cmd_side   = 0;
    logic [31:0] cmd_qty    = 0;
    logic [31:0] cmd_price  = 0;
    logic [31:0] cmd_id     = 0;
    logic        m_axis_tready = 1;

    logic [7:0]  m_axis_tdata;
    logic        m_axis_tvalid;
    logic        m_axis_tlast;
    logic        frame_builder_busy;

    tx_frame_builder dut (.*);

    int pass_count = 0, fail_count = 0;
    task automatic check(input string name, input logic cond);
        if (cond) begin $display("  PASS: %s", name); pass_count++; end
        else      begin $display("  FAIL: %s", name); fail_count++; end
    endtask

    // Collect one full frame at posedge boundaries; captures every valid transfer.
    task automatic collect_one_frame(output logic [7:0] fout[0:63], output int cnt);
        cnt = 0;
        forever begin
            @(posedge clk); #1;
            if (m_axis_tvalid && m_axis_tready) begin
                fout[cnt] = m_axis_tdata;
                cnt++;
                if (m_axis_tlast) break;
                if (cnt > 63) break;
            end
        end
    endtask

    // Send cmd + collect frame concurrently
    task automatic run_and_collect(
        input  [31:0] oid, input [15:0] sym, input [7:0] sd,
        input  [31:0] qty, input [31:0] prc,
        output logic [7:0] fout[0:63], output int cnt
    );
        fork
            begin
                @(posedge clk); #1;
                cmd_id=oid; cmd_symbol=sym; cmd_side=sd; cmd_qty=qty; cmd_price=prc;
                cmd_valid=1; @(posedge clk); #1; cmd_valid=0;
            end
            collect_one_frame(fout, cnt);
        join
    endtask

    logic [7:0] golden_0[0:57];
    logic [7:0] golden_1[0:57];
    initial begin
        $readmemh("golden_frame_0.hex", golden_0);
        $readmemh("golden_frame_1.hex", golden_1);
    end

    logic [7:0] rx[0:63];
    int         rx_cnt;

    initial begin
        wait(rst_n); repeat(2) @(posedge clk);

        // ---- T1: Reset ----
        $display("\n[T1] Reset state");
        check("m_axis_tvalid=0",      m_axis_tvalid     === 1'b0);
        check("frame_builder_busy=0", frame_builder_busy === 1'b0);

        // ---- T2: busy combinational — check it persists from cmd_valid through frame ----
        $display("\n[T2] frame_builder_busy high during entire frame (combinational start)");
        m_axis_tready = 1;
        // Fire cmd and immediately check busy on the NEXT posedge (must still be high)
        @(posedge clk); #1;
        cmd_id=32'h1; cmd_symbol=16'h1; cmd_side=8'h1; cmd_qty=32'd100; cmd_price=32'd15050;
        cmd_valid = 1;
        @(posedge clk); #1;   // one cycle in: FSM has latched, busy via ST_SEND
        cmd_valid = 0;
        check("frame_builder_busy=1 one cycle after cmd_valid", frame_builder_busy === 1'b1);
        wait(!frame_builder_busy); @(posedge clk); #1;
        check("busy=0 after frame completes", frame_builder_busy === 1'b0);

        // ---- T3: Exact 58 bytes ----
        $display("\n[T3] Exact 58-byte frame");
        run_and_collect(32'h1, 16'h1, 8'h1, 32'd100, 32'd15050, rx, rx_cnt);
        check("frame is exactly 58 bytes", rx_cnt === 58);
        wait(!frame_builder_busy); @(posedge clk); #1;

        // ---- T4: Golden compare, order 0 ----
        $display("\n[T4] Golden frame — BUY 100 @ 150.50");
        begin
            automatic int pre = fail_count;
            for (int i = 0; i < 58; i++) begin
                if (rx[i] !== golden_0[i]) begin
                    $display("  FAIL: byte[%02d] got 0x%02X expected 0x%02X", i, rx[i], golden_0[i]);
                    fail_count++;
                end
            end
            if (fail_count == pre) begin
                $display("  PASS: all 58 bytes match golden_frame_0");
                pass_count++;
            end
        end

        // ---- T5: Backpressure — use run_and_collect but toggle tready during collection ----
        $display("\n[T5] Backpressure: tready toggled mid-frame");
        begin
            automatic logic [7:0] bp_rx[0:63];
            automatic int         bp_cnt = 0;

            fork
                // cmd thread
                begin
                    @(posedge clk); #1;
                    cmd_id=32'h1; cmd_symbol=16'h1; cmd_side=8'h1;
                    cmd_qty=32'd100; cmd_price=32'd15050;
                    cmd_valid=1; @(posedge clk); #1; cmd_valid=0;
                end
                // collect thread with mid-stream stall
                begin
                    // Collect first 15 bytes normally
                    repeat(15) begin
                        @(posedge clk); #1;
                        if (m_axis_tvalid && m_axis_tready) begin
                            bp_rx[bp_cnt] = m_axis_tdata; bp_cnt++;
                        end
                    end
                    // Stall for 5 cycles
                    m_axis_tready = 0;
                    repeat(5) @(posedge clk); #1;
                    m_axis_tready = 1;
                    // Collect remainder
                    while (1) begin
                        @(posedge clk); #1;
                        if (m_axis_tvalid && m_axis_tready) begin
                            bp_rx[bp_cnt] = m_axis_tdata;
                            if (m_axis_tlast) begin bp_cnt++; break; end
                            bp_cnt++; if (bp_cnt > 63) break;
                        end
                    end
                end
            join

            check("backpressure: 58 bytes total", bp_cnt === 58);
            // Full compare vs golden — this catches any byte loss or duplication
            begin
                automatic int pre2 = fail_count;
                for (int i = 0; i < 58; i++) begin
                    if (bp_rx[i] !== golden_0[i]) begin
                        $display("  FAIL bp byte[%02d]: got 0x%02X expected 0x%02X",
                                 i, bp_rx[i], golden_0[i]);
                        fail_count++;
                    end
                end
                if (fail_count == pre2) begin
                    $display("  PASS: backpressure frame matches golden");
                    pass_count++;
                end
            end
        end
        wait(!frame_builder_busy); @(posedge clk); #1;

        // ---- T6: Second order, different fields ----
        $display("\n[T6] Golden frame — SELL 500 @ 2000.99");
        run_and_collect(32'hDEADBEEF, 16'h1, 8'h2, 32'd500, 32'd200099, rx, rx_cnt);
        check("order 1: 58 bytes", rx_cnt === 58);
        begin
            automatic int pre = fail_count;
            for (int i = 0; i < 58; i++) begin
                if (rx[i] !== golden_1[i]) begin
                    $display("  FAIL: byte[%02d] got 0x%02X expected 0x%02X", i, rx[i], golden_1[i]);
                    fail_count++;
                end
            end
            if (fail_count == pre) begin
                $display("  PASS: all 58 bytes match golden_frame_1");
                pass_count++;
            end
        end

        // ---- T7: Constant header spot-check ----
        $display("\n[T7] Constant header fields");
        check("byte[12]=0x08 (EtherType MSB)", rx[12] === 8'h08);
        check("byte[13]=0x00 (EtherType LSB)", rx[13] === 8'h00);
        check("byte[23]=0x11 (IP proto=UDP)",  rx[23] === 8'h11);
        check("byte[57]=0x00 (Table-7 pad)",   rx[57] === 8'h00);

        // ---- T8: Idle after all frames ----
        $display("\n[T8] Idle after all frames");
        wait(!frame_builder_busy); @(posedge clk); #1;
        check("m_axis_tvalid=0",      m_axis_tvalid     === 1'b0);
        check("frame_builder_busy=0", frame_builder_busy === 1'b0);

        $display("\n========================================");
        $display("PASS: %0d  FAIL: %0d", pass_count, fail_count);
        if (fail_count == 0) $display("ALL TESTS PASSED");
        else                 $display("SOME TESTS FAILED");
        $display("========================================");
        $finish;
    end

    initial begin #1000000; $display("TIMEOUT"); $finish; end

endmodule
