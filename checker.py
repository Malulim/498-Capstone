import struct

TABLE_7_FORMAT = "<I H B I I B"  # Table 7 定义


def parse_order_log(log_path):
    """解析 FPGA 发回的二进制日志文件"""
    orders = []
    with open(log_path, "rb") as f:
        while True:
            data = f.read(struct.calcsize(TABLE_7_FORMAT))
            if not data: break
            fields = struct.unpack(TABLE_7_FORMAT, data)
            orders.append(fields)
    return orders


def verify_session(log_path, expected_data):
    """FS11 核心：核对实际订单与预期结果是否完全一致"""
    actual_orders = parse_order_log(log_path)

    # 这里加入比对逻辑
    for i, order in enumerate(actual_orders):
        if order != expected_data[i]:
            print(f"检测到差异！包索引: {i}")
            # 输出详细错误日志
    print("验证完成，数据流与预期一致。")


def parse_fpga_packet(data):
    # 根据 Table 7 解析数据包
    order_id, symbol, side, qty, price, pad = struct.unpack("<I H B I I B", data)

    return {
        "order_id": order_id,
        "symbol": symbol,
        "side": "Buy" if side == 0x01 else "Sell",
        "qty": qty,
        "price": price / 100.0,  # 转换回正常价格
        "pad": pad
    }


if __name__ == "__main__":
    # 1. 模拟生成一份 FPGA 发回的二进制日志 (Table 7 格式)
    # 模拟数据：ID=1001, Symbol=1, Side=0x01(Buy), Qty=50, Price=10050(100.50), Pad=0
    mock_data = struct.pack("<I H B I I B", 1001, 1, 0x01, 50, 10050, 0)

    with open("mock_fpga_output.log", "wb") as f:
        f.write(mock_data)

    # 2. 准备一份你预期的结果 (expected_data)
    # 注意：这里的数据必须和上面的 mock_data 完全一致
    expected_results = [(1001, 1, 0x01, 50, 10050, 0)]

    # 3. 运行测试
    print("--- 开始测试 Checker ---")
    verify_session("mock_fpga_output.log", expected_results)

    # 4. 尝试使用新函数解析
    print("\n--- 测试 parse_fpga_packet ---")
    print(parse_fpga_packet(mock_data))