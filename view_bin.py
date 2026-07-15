import struct
import os

# 导入你之前的协议定义
TABLE_6_FORMAT = "<B H I I B I I I"
FRAME_FILE = "build/frame.bin"


def view_frame_bin(file_path):
    packet_size = struct.calcsize(TABLE_6_FORMAT)

    if not os.path.exists(file_path):
        print(f"找不到文件: {file_path}")
        return

    with open(file_path, "rb") as f:
        count = 0
        while True:
            data = f.read(packet_size)
            if not data: break

            # 解析二进制包
            unpacked = struct.unpack(TABLE_6_FORMAT, data)
            print(f"Packet {count}: {unpacked}")
            count += 1

            # 为了防止打印太多，你可以先查看前 10 个包
            if count >= 10:
                print("... (仅显示前 10 个包)")
                break


if __name__ == "__main__":
    view_frame_bin(FRAME_FILE)