import socket
import struct

TABLE_6_FORMAT = "<B H I I B I I I"  # RX Ingress (Simulator -> FPGA)
TABLE_7_FORMAT = "<I H B I I B"  # TX Order-Egress (FPGA -> Simulator)
SYMBOL_ID = 1  # [NEW] prototype scope is one equity symbol (README 1.2), hardcode it


def run_mock_fpga():
    """
    Simulates the FPGA backend: receives data on the specified port
    and forwards it back to the host receiver.
    """
    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Assuming the Simulator sends data to this address
    listen_sock.bind(("127.0.0.1", 12345))

    print("Mock FPGA initialized, waiting for data from Simulator...")
    count = 0

    while True:
        data, addr = listen_sock.recvfrom(1024)
        print(f"Packet received: {len(data)} bytes from {addr}")
        msg_type, ver, price, qty, side, order_id, seq, pad = struct.unpack(TABLE_6_FORMAT, data)

        # 1. 组装成 Table 7 格式的回复
        reply = struct.pack(TABLE_7_FORMAT, order_id, SYMBOL_ID, side, qty, price, 0)

        # 2. 发送组装好的 reply，而不是原始的 data
        listen_sock.sendto(reply, ("127.0.0.1", 12346))

        count += 1
        if count % 20000 == 0:
            print(f"Mock FPGA: {count} frames received and echoed as order packets...")

        print("Data forwarded to Receiver...")

if __name__ == "__main__":
    run_mock_fpga()
