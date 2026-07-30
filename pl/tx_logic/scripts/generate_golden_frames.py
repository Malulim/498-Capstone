#!/usr/bin/env python3
"""
Golden Frame Generator Script for PL tx_logic verification.

Generates:
1. golden_frames.bin: Raw 58-byte binary streams for FPGA simulation.
2. golden_frames.hex: Byte-by-byte ASCII Hex format for Verilog $readmemh.
3. golden_frames_meta.json: Human-readable test vector metadata.
"""

import struct
import json
import os
import sys

def compute_ip_checksum(ip_header_bytes: bytes) -> int:
    """Calculates standard 16-bit IPv4 header checksum."""
    if len(ip_header_bytes) % 2 != 0:
        ip_header_bytes += b'\x00'
    s = 0
    for i in range(0, len(ip_header_bytes), 2):
        w = (ip_header_bytes[i] << 8) + ip_header_bytes[i+1]
        s += w
    while (s >> 16):
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF

class GoldenFrameGenerator:
    def __init__(self):
        # Default network settings
        self.src_mac = b'\x02\x00\x00\x00\x00\x01'
        self.dst_mac = b'\x02\x00\x00\x00\x00\x02'
        self.eth_type = 0x0800  # IPv4
        
        self.ip_src = bytes([192, 168, 1, 10])
        self.ip_dst = bytes([192, 168, 1, 20])
        
        self.udp_src_port = 12345
        self.udp_dst_port = 12346
        self.test_cases = []

    def build_network_header(self) -> bytes:
        """Builds 42-byte Ethernet + IP + UDP Header (Big-Endian)."""
        # Ethernet Header (14B)
        eth_hdr = self.dst_mac + self.src_mac + struct.pack('>H', self.eth_type)
        
        # IP Header without checksum (20B)
        # Total Length = 44 (20B IP + 8B UDP + 16B Payload). Excludes the
        # Ethernet pad TEMAC appends -- padding sits below IP.
        # Flags = 0x4000 (Don't Fragment): this datagram is fixed-size and must
        # never be fragmented. Nothing on a point-to-point link would fragment
        # it anyway, but DF states the intent, so a middlebox on some future
        # path raises an ICMP error instead of silently splitting an order.
        ip_hdr_no_cksum = (
            struct.pack('>BBHHHBB', 0x45, 0x00, 44, 0, 0x4000, 64, 17)
            + b'\x00\x00'
            + self.ip_src
            + self.ip_dst
        )
        cksum = compute_ip_checksum(ip_hdr_no_cksum)
        ip_hdr = ip_hdr_no_cksum[:10] + struct.pack('>H', cksum) + ip_hdr_no_cksum[12:]
        
        # UDP Header (8B) - Length = 24 (8B UDP + 16B Payload)
        udp_hdr = struct.pack('>HHHH', self.udp_src_port, self.udp_dst_port, 24, 0x0000)
        
        return eth_hdr + ip_hdr + udp_hdr

    def create_order_frame(self, order_id: int, symbol: int, side: int, qty: int, price: int) -> bytes:
        """Constructs full 58-byte frame."""
        header = self.build_network_header()  # 42 Bytes Big-Endian
        
        # Table 7 Payload (16 Bytes Little-Endian '<')
        # Format string breakdown:
        # I = uint32 (4B) order_id
        # H = uint16 (2B) symbol
        # B = uint8  (1B) side
        # I = uint32 (4B) qty
        # I = uint32 (4B) price
        # 1s = char[1] (1B) pad byte (0x00)
        payload = struct.pack(
            '<IHBII1s', 
            order_id & 0xFFFFFFFF, 
            symbol & 0xFFFF, 
            side & 0xFF, 
            qty & 0xFFFFFFFF, 
            price & 0xFFFFFFFF, 
            b'\x00'
        )
        
        frame = header + payload
        assert len(frame) == 58, f"Expected 58 bytes, got {len(frame)}"
        return frame

    def add_test_case(self, case_name: str, order_id: int, symbol: int, side: int, qty: int, price: int):
        raw_frame = self.create_order_frame(order_id, symbol, side, qty, price)
        
        # Format as byte-by-byte HEX string list for $readmemh
        hex_bytes = [f"{b:02X}" for b in raw_frame]

        self.test_cases.append({
            "case_name": case_name,
            "inputs": {
                "order_id": order_id, 
                "symbol": symbol, 
                "side": side, 
                "qty": qty, 
                "price": price
            },
            "raw_hex": raw_frame.hex().upper(),
            "hex_bytes": hex_bytes,
            "raw_bytes": raw_frame
        })

    def export_files(self, output_dir: str = "."):
        os.makedirs(output_dir, exist_ok=True)
        
        bin_path = os.path.join(output_dir, "golden_frames.bin")
        hex_path = os.path.join(output_dir, "golden_frames.hex")
        meta_path = os.path.join(output_dir, "golden_frames_meta.json")

        per_case_paths = []

        with open(bin_path, "wb") as f_bin, open(hex_path, "w") as f_hex:
            meta_json_data = []
            for idx, case in enumerate(self.test_cases):
                f_bin.write(case["raw_bytes"])
                for byte_hex in case["hex_bytes"]:
                    f_hex.write(f"{byte_hex}\n")

                # One file per case as well. A testbench that $readmemh's a
                # 58-entry array from its own file cannot silently pick up the
                # wrong baseline; indexing into the concatenated file with a
                # hand-written case offset can, and the failure looks like an
                # RTL byte-order bug.
                case_path = os.path.join(output_dir, f"golden_frame_{idx}.hex")
                with open(case_path, "w") as f_case:
                    for byte_hex in case["hex_bytes"]:
                        f_case.write(f"{byte_hex}\n")
                per_case_paths.append(case_path)

                meta_json_data.append({
                    "case_name": case["case_name"],
                    "inputs": case["inputs"],
                    "raw_hex": case["raw_hex"]
                })

        with open(meta_path, "w") as f_meta:
            json.dump(meta_json_data, f_meta, indent=2)

        print(f"Generated golden frames in '{output_dir}':")
        print(f"  - Binary (all cases): {bin_path}")
        print(f"  - $readmemh Hex (all cases): {hex_path}")
        for idx, p in enumerate(per_case_paths):
            print(f"  - $readmemh Hex (case {idx}): {p}")
        print(f"  - Metadata: {meta_path}")

def main():
    gen = GoldenFrameGenerator()
    # These cases ARE the contract: any testbench comparing against
    # golden_frame_<i>.hex must drive exactly these field values, in this
    # order. Values are deliberately byte-distinct (10001 = 0x2711,
    # 1505000 = 0x16F6E8) so a swapped or misplaced byte cannot coincidentally
    # match, and symbol/side differ between the two cases so their placement is
    # exercised rather than assumed.
    gen.add_test_case("Basic_Buy_Limit", order_id=10001, symbol=0x0001, side=1, qty=100, price=1505000)
    gen.add_test_case("Basic_Sell_Limit", order_id=10002, symbol=0x0002, side=2, qty=50, price=3102000)

    output_directory = sys.argv[1] if len(sys.argv) > 1 else "."
    gen.export_files(output_directory)

if __name__ == "__main__":
    main()