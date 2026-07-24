import struct

TABLE_7_FORMAT = "<I H B I I B"  # Table 7 Definition


def parse_order_log(log_path):
    """Parses the binary log file returned by the FPGA."""
    orders = []
    with open(log_path, "rb") as f:
        while True:
            data = f.read(struct.calcsize(TABLE_7_FORMAT))
            if not data: break
            fields = struct.unpack(TABLE_7_FORMAT, data)
            orders.append(fields)
    return orders


def verify_session(log_path, expected_data):
    """Core FS11 validation: Checks if actual orders match expected results exactly."""
    actual_orders = parse_order_log(log_path)

    # Comparison logic
    for i, order in enumerate(actual_orders):
        if order != expected_data[i]:
            print(f"Mismatch detected! Packet index: {i}")
            # Log detailed error information here
    print("Verification complete: Data stream is consistent with expectations.")


def verify_session_stream(log_path, frame_path):
    """Stream validation: Compares frame.bin and order.log without loading entire files into memory."""
    with open(log_path, "rb") as log_f, open(frame_path, "rb") as frame_f:
        # Table 6 format definition
        TABLE_6_FORMAT = "<B H I I B I I I"

        index = 0
        while True:
            frame_data = frame_f.read(struct.calcsize(TABLE_6_FORMAT))
            log_data = log_f.read(struct.calcsize(TABLE_7_FORMAT))

            if not frame_data: break
            index += 1

            # 1. Parse original frame (Table 6)
            # Table 6 fields: msg_type, ver, price, qty, side, id, seq, pad
            f_msg_type, f_ver, f_price, f_qty, f_side, f_id, f_seq, f_pad = struct.unpack(TABLE_6_FORMAT, frame_data)

            # 2. Parse feedback frame (Table 7)
            # Table 7 fields: order_id, symbol, side, qty, price, pad
            l_id, l_sym, l_side, l_qty, l_price, l_pad = struct.unpack(TABLE_7_FORMAT, log_data)

            # 3. Core validation logic with detailed print output
            if f_id != l_id or f_qty != l_qty or f_price != l_price:
                print(f"Validation failed at packet #{index}! Order ID: sent={f_id}, received={l_id}")
                print(f"  -> Qty   - sent: {f_qty}, received: {l_qty}")
                print(f"  -> Price - sent: {f_price}, received: {l_price}")
                return False

    print("Verification complete: Data stream is consistent with expectations.")
    return True


def parse_fpga_packet(data):
    """Parses a data packet according to Table 7."""
    order_id, symbol, side, qty, price, pad = struct.unpack("<I H B I I B", data)

    return {
        "order_id": order_id,
        "symbol": symbol,
        "side": "Buy" if side == 0x01 else "Sell",
        "qty": qty,
        "price": price / 100.0,  # Convert to standard price format
        "pad": pad
    }

if __name__ == "__main__":
        # 1. Simulate generating an FPGA binary log (Table 7 format)
        # Mock data: ID=1001, Symbol=1, Side=0x01(Buy), Qty=50, Price=10050(100.50), Pad=0
        mock_data = struct.pack("<I H B I I B", 1001, 1, 0x01, 50, 10050, 0)

        log_filename = "mock_fpga_output.log"
        frame_filename = "mock_frame.bin"

        with open(log_filename, "wb") as f:
            f.write(mock_data)

        # Create a dummy frame file for stream validation testing
        # Table 6 format: <B H I I B I I I
        with open(frame_filename, "wb") as f:
            # Faking the corresponding Table 6 frame for ID 1001
            frame = struct.pack("<B H I I B I I I", 1, 1, 10050, 50, 1, 1001, 1, 0)
            f.write(frame)

        # 2. Prepare expected results
        expected_results = [(1001, 1, 0x01, 50, 10050, 0)]

        # 3. Test: Full Session Verification
        print("--- Starting Full Session Verification ---")
        verify_session(log_filename, expected_results)

        # 4. Test: Stream-based Validation
        print("\n--- Starting Stream-based Validation ---")
        verify_session_stream(log_filename, frame_filename)

        # 5. Test: Packet Parsing
        print("\n--- Testing Individual Packet Parsing ---")
        print(parse_fpga_packet(mock_data))
