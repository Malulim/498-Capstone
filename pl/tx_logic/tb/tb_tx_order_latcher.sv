`timescale 1ns/1ps

module tb_tx_order_latcher;
  localparam time CLK_PERIOD = 8ns;

  logic clk = 1'b0;
  logic rst_n = 1'b1;

  logic [15:0] ord_symbol = '0;
  logic [7:0]  ord_side = '0;
  logic [31:0] ord_qty = '0;
  logic [31:0] ord_price = '0;
  logic [31:0] ord_id = '0;
  logic        doorbell_pulse = 1'b0;
  logic        frame_builder_busy = 1'b0;

  logic        tx_ready;
  logic        cmd_valid;
  logic [31:0] cmd_order_id;
  logic [15:0] cmd_symbol;
  logic [7:0]  cmd_side;
  logic [31:0] cmd_qty;
  logic [31:0] cmd_price;

  tx_order_latcher dut (
    .clk,
    .rst_n,
    .ord_symbol,
    .ord_side,
    .ord_qty,
    .ord_price,
    .ord_id,
    .doorbell_pulse,
    .tx_ready,
    .cmd_valid,
    .cmd_order_id,
    .cmd_symbol,
    .cmd_side,
    .cmd_qty,
    .cmd_price,
    .frame_builder_busy
  );

  always #(CLK_PERIOD / 2) clk = ~clk;

  task automatic check(input logic condition, input string message);
    if (!condition) begin
      $fatal(1, "FAIL: %s", message);
    end
  endtask

  task automatic drive_order(
    input logic [31:0] id,
    input logic [15:0] symbol,
    input logic [7:0]  side,
    input logic [31:0] quantity,
    input logic [31:0] price
  );
    ord_id = id;
    ord_symbol = symbol;
    ord_side = side;
    ord_qty = quantity;
    ord_price = price;
  endtask

  task automatic check_command(
    input logic [31:0] id,
    input logic [15:0] symbol,
    input logic [7:0]  side,
    input logic [31:0] quantity,
    input logic [31:0] price,
    input string ctx
  );
    check(cmd_order_id === id, {ctx, ": order_id"});
    check(cmd_symbol === symbol, {ctx, ": symbol"});
    check(cmd_side === side, {ctx, ": side"});
    check(cmd_qty === quantity, {ctx, ": quantity"});
    check(cmd_price === price, {ctx, ": price"});
  endtask

  initial begin
    // Asynchronous active-low reset must clear state without waiting for a clock.
    #1;
    rst_n = 1'b0;
    #1;
    check(cmd_valid === 1'b0, "async reset clears cmd_valid");
    check_command('0, '0, '0, '0, '0, "async reset clears command");
    check(tx_ready === 1'b1, "ready follows idle builder during reset");

    frame_builder_busy = 1'b1;
    #1;
    check(tx_ready === 1'b0, "ready follows busy builder during reset");
    frame_builder_busy = 1'b0;
    #1;
    check(tx_ready === 1'b1, "ready returns immediately during reset");

    @(negedge clk);
    rst_n = 1'b1;

    // Idle doorbell accepts and atomically captures every field.
    @(negedge clk);
    drive_order(32'h1122_3344, 16'h5566, 8'h01, 32'd75, 32'd12_345);
    doorbell_pulse = 1'b1;
    #1;
    check(cmd_valid === 1'b0, "cmd_valid is registered, not combinational");
    @(posedge clk);
    #1;
    check(cmd_valid === 1'b1, "idle doorbell produces cmd_valid");
    check_command(
      32'h1122_3344, 16'h5566, 8'h01, 32'd75, 32'd12_345,
      "first accepted order"
    );

    @(negedge clk);
    doorbell_pulse = 1'b0;
    @(posedge clk);
    #1;
    check(cmd_valid === 1'b0, "cmd_valid lasts exactly one cycle");
    check_command(
      32'h1122_3344, 16'h5566, 8'h01, 32'd75, 32'd12_345,
      "command holds after valid"
    );

    // TX_READY is a direct combinational inverse of downstream busy.
    frame_builder_busy = 1'b1;
    #1;
    check(tx_ready === 1'b0, "busy deasserts ready immediately");
    frame_builder_busy = 1'b0;
    #1;
    check(tx_ready === 1'b1, "idle asserts ready immediately");

    // Doorbells received while busy are discarded and cannot alter the active
    // command, even while the input fields continue changing.
    @(negedge clk);
    frame_builder_busy = 1'b1;
    drive_order(32'hAABB_CCDD, 16'h00AA, 8'h02, 32'd500, 32'd98_765);
    doorbell_pulse = 1'b1;
    @(posedge clk);
    #1;
    check(cmd_valid === 1'b0, "busy doorbell is blocked");
    check_command(
      32'h1122_3344, 16'h5566, 8'h01, 32'd75, 32'd12_345,
      "busy doorbell preserves active command"
    );

    @(negedge clk);
    doorbell_pulse = 1'b0;
    drive_order(32'hDEAD_BEEF, 16'h0BAD, 8'h02, 32'd999, 32'd77_777);
    @(posedge clk);
    #1;
    check(cmd_valid === 1'b0, "input changes while busy do not create valid");
    check_command(
      32'h1122_3344, 16'h5566, 8'h01, 32'd75, 32'd12_345,
      "busy input changes preserve active command"
    );

    // Releasing busy must not replay the previously discarded doorbell.
    @(negedge clk);
    frame_builder_busy = 1'b0;
    @(posedge clk);
    #1;
    check(cmd_valid === 1'b0, "discarded doorbell is not replayed");
    check_command(
      32'h1122_3344, 16'h5566, 8'h01, 32'd75, 32'd12_345,
      "no replay preserves prior command"
    );

    // A new doorbell after busy clears is accepted normally.
    @(negedge clk);
    drive_order(32'hCAFE_0002, 16'h0001, 8'h02, 32'd120, 32'd54_321);
    doorbell_pulse = 1'b1;
    @(posedge clk);
    #1;
    check(cmd_valid === 1'b1, "new post-busy doorbell is accepted");
    check_command(
      32'hCAFE_0002, 16'h0001, 8'h02, 32'd120, 32'd54_321,
      "second accepted order"
    );

    @(negedge clk);
    doorbell_pulse = 1'b0;
    @(posedge clk);
    #1;
    check(cmd_valid === 1'b0, "second cmd_valid pulse ends");

    // Assert reset away from a clock edge to prove asynchronous behavior.
    #1;
    rst_n = 1'b0;
    #1;
    check(cmd_valid === 1'b0, "final async reset clears cmd_valid");
    check_command('0, '0, '0, '0, '0, "final async reset clears command");

    $display("PASS: tx_order_latcher");
    $finish;
  end

endmodule
