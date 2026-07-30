`timescale 1ns/1ps
// tx_frame_builder.sv
// Serializer FSM: outputs 58 bytes onto AXI4-Stream with backpressure.
// Byte counter only advances when tvalid & tready both high.
//
// Frame layout (TEMAC appends pad + FCS):
//   byte  0-13 : Ethernet header      (big-endian, constants)
//   byte 14-33 : IPv4 header          (big-endian, checksum pre-computed)
//   byte 34-41 : UDP header           (big-endian, constants)
//   byte 42-57 : Table-7 payload      (little-endian, from cmd_*)
//
// IP header checksum: pre-computed for fixed header with total_len=44.
// Run gen_golden_frame.py to verify — value below is for the default
// src/dst IP pair (192.168.1.1 → 192.168.1.2) used in testbench.

module tx_frame_builder (
    input  logic        clk,
    input  logic        rst_n,

    // From tx_order_latcher
    input  logic        cmd_valid,          // 1-cycle pulse
    input  logic [15:0] cmd_symbol,
    input  logic [7:0]  cmd_side,
    input  logic [31:0] cmd_qty,
    input  logic [31:0] cmd_price,
    input  logic [31:0] cmd_id,

    // AXI4-Stream master to TEMAC
    output logic [7:0]  m_axis_tdata,
    output logic        m_axis_tvalid,
    output logic        m_axis_tlast,
    input  logic        m_axis_tready,

    // Back to tx_order_latcher — MUST be combinational same-cycle as cmd_valid
    output logic        frame_builder_busy
);

    // ----------------------------------------------------------------
    // Frame constants — Ethernet + IPv4 + UDP headers (42 bytes)
    // Adjust MAC/IP addresses to match your point-to-point link config.
    // ----------------------------------------------------------------
    localparam [47:0] DST_MAC      = 48'hFF_FF_FF_FF_FF_FF;
    localparam [47:0] SRC_MAC      = 48'hAA_BB_CC_DD_EE_FF;
    localparam [15:0] ETHERTYPE    = 16'h0800;

    // IPv4 header (20 bytes)
    localparam [7:0]  IP_VER_IHL   = 8'h45;   // version=4, IHL=5 (no options)
    localparam [7:0]  IP_DSCP      = 8'h00;
    localparam [15:0] IP_TOTAL_LEN = 16'd44;   // 20(IP)+8(UDP)+16(payload)
    localparam [15:0] IP_ID        = 16'h0000;
    localparam [15:0] IP_FRAG      = 16'h4000; // Don't Fragment
    localparam [7:0]  IP_TTL       = 8'd64;
    localparam [7:0]  IP_PROTO     = 8'd17;    // UDP
    // Checksum for: 45 00 00 2C 00 00 40 00 40 11 ?? ?? C0A80101 C0A80102
    // = 0xB861  (verified by gen_golden_frame.py)
    localparam [15:0] IP_CHECKSUM  = 16'hB76D; // verified by gen_golden_frame.py
    localparam [31:0] SRC_IP       = 32'hC0A80101; // 192.168.1.1
    localparam [31:0] DST_IP       = 32'hC0A80102; // 192.168.1.2

    // UDP header (8 bytes)
    localparam [15:0] UDP_SRC_PORT = 16'd9000;
    localparam [15:0] UDP_DST_PORT = 16'd9000;
    localparam [15:0] UDP_LENGTH   = 16'd24;   // 8(UDP)+16(payload)
    localparam [15:0] UDP_CHECKSUM = 16'h0000; // bypassed on P2P link

    localparam FRAME_BYTES = 58;

    // ----------------------------------------------------------------
    // Byte counter FSM
    // ----------------------------------------------------------------
    typedef enum logic { ST_IDLE = 1'b0, ST_SEND = 1'b1 } state_t;
    state_t state;

    logic [5:0] byte_cnt;   // 0..57

    // busy is combinational: goes high the SAME cycle cmd_valid arrives
    assign frame_builder_busy = (state == ST_SEND) ||
                                (state == ST_IDLE && cmd_valid);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state    <= ST_IDLE;
            byte_cnt <= '0;
        end else begin
            case (state)
                ST_IDLE: begin
                    if (cmd_valid) begin
                        state    <= ST_SEND;
                        byte_cnt <= '0;
                    end
                end
                ST_SEND: begin
                    if (m_axis_tready) begin
                        if (byte_cnt == FRAME_BYTES - 1) begin
                            state    <= ST_IDLE;
                            byte_cnt <= '0;
                        end else begin
                            byte_cnt <= byte_cnt + 1'b1;
                        end
                    end
                end
            endcase
        end
    end

    assign m_axis_tvalid = (state == ST_SEND);
    assign m_axis_tlast  = (state == ST_SEND) && (byte_cnt == FRAME_BYTES - 1);

    // ----------------------------------------------------------------
    // Byte mux — select byte[byte_cnt] from frame
    // Option B: combinational mux over constants + stable cmd_* fields.
    // ----------------------------------------------------------------
    always_comb begin
        m_axis_tdata = 8'h00;
        case (byte_cnt)
            // --- Ethernet header (bytes 0-13) big-endian ---
            6'd0:  m_axis_tdata = DST_MAC[47:40];
            6'd1:  m_axis_tdata = DST_MAC[39:32];
            6'd2:  m_axis_tdata = DST_MAC[31:24];
            6'd3:  m_axis_tdata = DST_MAC[23:16];
            6'd4:  m_axis_tdata = DST_MAC[15:8];
            6'd5:  m_axis_tdata = DST_MAC[7:0];
            6'd6:  m_axis_tdata = SRC_MAC[47:40];
            6'd7:  m_axis_tdata = SRC_MAC[39:32];
            6'd8:  m_axis_tdata = SRC_MAC[31:24];
            6'd9:  m_axis_tdata = SRC_MAC[23:16];
            6'd10: m_axis_tdata = SRC_MAC[15:8];
            6'd11: m_axis_tdata = SRC_MAC[7:0];
            6'd12: m_axis_tdata = ETHERTYPE[15:8];
            6'd13: m_axis_tdata = ETHERTYPE[7:0];

            // --- IPv4 header (bytes 14-33) big-endian ---
            6'd14: m_axis_tdata = IP_VER_IHL;
            6'd15: m_axis_tdata = IP_DSCP;
            6'd16: m_axis_tdata = IP_TOTAL_LEN[15:8];
            6'd17: m_axis_tdata = IP_TOTAL_LEN[7:0];
            6'd18: m_axis_tdata = IP_ID[15:8];
            6'd19: m_axis_tdata = IP_ID[7:0];
            6'd20: m_axis_tdata = IP_FRAG[15:8];
            6'd21: m_axis_tdata = IP_FRAG[7:0];
            6'd22: m_axis_tdata = IP_TTL;
            6'd23: m_axis_tdata = IP_PROTO;
            6'd24: m_axis_tdata = IP_CHECKSUM[15:8];
            6'd25: m_axis_tdata = IP_CHECKSUM[7:0];
            6'd26: m_axis_tdata = SRC_IP[31:24];
            6'd27: m_axis_tdata = SRC_IP[23:16];
            6'd28: m_axis_tdata = SRC_IP[15:8];
            6'd29: m_axis_tdata = SRC_IP[7:0];
            6'd30: m_axis_tdata = DST_IP[31:24];
            6'd31: m_axis_tdata = DST_IP[23:16];
            6'd32: m_axis_tdata = DST_IP[15:8];
            6'd33: m_axis_tdata = DST_IP[7:0];

            // --- UDP header (bytes 34-41) big-endian ---
            6'd34: m_axis_tdata = UDP_SRC_PORT[15:8];
            6'd35: m_axis_tdata = UDP_SRC_PORT[7:0];
            6'd36: m_axis_tdata = UDP_DST_PORT[15:8];
            6'd37: m_axis_tdata = UDP_DST_PORT[7:0];
            6'd38: m_axis_tdata = UDP_LENGTH[15:8];
            6'd39: m_axis_tdata = UDP_LENGTH[7:0];
            6'd40: m_axis_tdata = UDP_CHECKSUM[15:8];
            6'd41: m_axis_tdata = UDP_CHECKSUM[7:0];

            // --- Table-7 payload (bytes 42-57) little-endian ---
            // order_id [31:0] → bytes 42-45 (LSB first)
            6'd42: m_axis_tdata = cmd_id[7:0];
            6'd43: m_axis_tdata = cmd_id[15:8];
            6'd44: m_axis_tdata = cmd_id[23:16];
            6'd45: m_axis_tdata = cmd_id[31:24];
            // symbol [15:0] → bytes 46-47
            6'd46: m_axis_tdata = cmd_symbol[7:0];
            6'd47: m_axis_tdata = cmd_symbol[15:8];
            // side [7:0] → byte 48
            6'd48: m_axis_tdata = cmd_side;
            // qty [31:0] → bytes 49-52
            6'd49: m_axis_tdata = cmd_qty[7:0];
            6'd50: m_axis_tdata = cmd_qty[15:8];
            6'd51: m_axis_tdata = cmd_qty[23:16];
            6'd52: m_axis_tdata = cmd_qty[31:24];
            // price [31:0] → bytes 53-56
            6'd53: m_axis_tdata = cmd_price[7:0];
            6'd54: m_axis_tdata = cmd_price[15:8];
            6'd55: m_axis_tdata = cmd_price[23:16];
            6'd56: m_axis_tdata = cmd_price[31:24];
            // pad → byte 57
            6'd57: m_axis_tdata = 8'h00;

            default: m_axis_tdata = 8'h00;
        endcase
    end

endmodule
