import socket
import struct
import time
import pandas as pd
import os

# 定义路径
DATA_DIR = "data"
BUILD_DIR = "build"
MESSAGE_FILE = os.path.join(DATA_DIR, "message.csv")
FRAME_FILE = os.path.join(BUILD_DIR, "frame.bin")

# 你的其他函数逻辑 ...
# preprocess_lobster_to_bin(MESSAGE_FILE, FRAME_FILE)

# 1. 协议定义
# Table 6: RX Ingress (Simulator -> FPGA)
# B=8b, H=16b, I=32b
TABLE_6_FORMAT = "<B H I I B I I I"
# Table 7: TX Order-Egress (FPGA -> Simulator)[cite: 1]
TABLE_7_FORMAT = "<I H B I I B"


# 2. Offline Preparation: 预处理[cite: 1]
def preprocess_lobster_to_bin(input_csv, output_frame_file):
    """将 CSV 数据转换为二进制 Frame file，并进行必要的类型清洗"""
    # 1. 定义列名（根据 LOBSTER 标准格式）
    # 假设你的 CSV 是 [Time, Type, OrderID, Size, Price, Direction]
    cols = ['time', 'type', 'id', 'qty', 'price', 'side']

    # 2. 读取 CSV，跳过头行（如果文件有表头）
    df = pd.read_csv(input_csv, header=None, names=cols)

    # 3. 添加一个单调递增的 seq_num (Table 6 要求)
    df['seq'] = range(1, len(df) + 1)

    with open(output_frame_file, "wb") as f:
        for _, row in df.iterrows():
            # 数据清洗：将 LOBSTER side (-1/1) 映射为 Table 6 的 (2/1)
            # Table 6: 0x01=Bid, 0x02=Ask
            raw_side = int(row['side'])
            mapped_side = 2 if raw_side == -1 else 1

            # 数据清洗：确保 msg_type 在 0-255 范围内
            msg_type = int(row['type']) % 256

            # 严格打包：注意这里严格匹配 Table 6 的字段顺序
            # 格式: msg_type(B), symbol(H), price(I), qty(I), side(B), order_id(I), seq_num(I), pad(I)
            packet = struct.pack(TABLE_6_FORMAT,
                                 msg_type,
                                 1,  # symbol 恒定为 1
                                 int(row['price']),
                                 int(row['qty']),
                                 mapped_side,
                                 int(row['id']),
                                 int(row['seq']),
                                 0)  # pad
            f.write(packet)

    print(f"预处理完成，已生成二进制文件: {output_frame_file}")

# 3. Online Replay: 在线回放[cite: 1]
def start_paced_replay(frame_file, target_ip, target_port, rate_scale=1.0):
    """按 Pacing 规则发送 UDP 包[cite: 1]"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    with open(frame_file, "rb") as f:
        while True:
            packet = f.read(struct.calcsize(TABLE_6_FORMAT))
            if not packet: break

            sock.sendto(packet, (target_ip, target_port))
            # 模拟真实市场节奏[cite: 1]
            time.sleep(0.001 / rate_scale)

    sock.close()


# 4. Order Receiver: 订单接收器[cite: 1]
def receive_and_log_orders(log_file, port=12345):
    """监听并实时统计接收到的包数量"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))

    count = 0
    with open(log_file, "wb") as f:
        print(f"正在监听端口 {port}...")
        while True:
            data, _ = sock.recvfrom(1024)
            f.write(data)
            f.flush()  # 确保数据立即写入磁盘
            count += 1
            if count % 100 == 0:  # 每收 100 个包打印一次进度
                print(f"已捕获 {count} 个订单反馈包...")


# 5. Offline Checker: 离线验证器[cite: 1]
def check_order_log(log_file, frame_file):
    """离线比对：验证输入与输出的逻辑一致性"""
    # 解析输入 (预期指令)
    expected_orders = []
    # ... (使用 struct.unpack 读取 frame.bin 并存入 expected_orders) ...

    # 解析输出 (实际反馈)
    actual_orders = []
    # ... (使用 struct.unpack 读取 log_file 并存入 actual_orders) ...

    # 执行验证逻辑
    print(f"开始验证：共发现 {len(actual_orders)} 个反馈包")
    for i, (exp, act) in enumerate(zip(expected_orders, actual_orders)):
        # 核心逻辑：比对 Order ID 和 Side 是否匹配
        if exp[5] != act[3]:  # 假设 Table 6 的 ID 是索引 5，Table 7 的 ID 是索引 3
            print(f"包索引 {i}: 订单 ID 不匹配！预期 {exp[5]}, 实际 {act[3]}")
        else:
            print(f"包索引 {i}: OK")


if __name__ == "__main__":
    # 1. 预处理数据 (这一步只需要跑一次，生成 frame.bin)
    preprocess_lobster_to_bin(MESSAGE_FILE, FRAME_FILE)

    # 2. 启动订单接收器 (后台线程，不会阻塞后续操作)
    import threading

    receiver_thread = threading.Thread(target=receive_and_log_orders, args=("build/order.log",))
    receiver_thread.daemon = True  # 设置为 daemon 线程，程序退出时它会自动关闭
    receiver_thread.start()

    print("接收器已启动，正在等待 FPGA 订单数据...")

    # 3. 开始发送数据 (开始你的回放)
    # 填入 FPGA 的 IP 和端口
    FPGA_IP = "192.168.1.10"
    FPGA_PORT = 12345
    print("开始发送数据...")
    start_paced_replay(FRAME_FILE, FPGA_IP, FPGA_PORT)