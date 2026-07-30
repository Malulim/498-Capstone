# Golden Frame Generator

生成 58 字节 Ethernet/IP/UDP 黄金参考帧,供 `tx_logic` 的单元测试和集成测试比对。

这个脚本是 **Table 7 payload 布局和 42 字节常量头的唯一 oracle**。RTL 里
`tx_frame_builder.sv` 的那些 `localparam` 必须与本脚本的 `build_network_header()`
逐字节一致——改动任何一边都要同步改另一边并重新生成,否则字节比对会以"RTL 字节序错了"
的形式报出来。取舍理由见 `../README.md` 的「决定:链路常量的单一来源」。

## 用法

```bash
python3 pl/tx_logic/scripts/generate_golden_frames.py <输出目录>
```

输出目录省略则用当前目录。注意 `pl/tx_logic/sim/` 在 `.gitignore` 里,生成物不进仓库,
**每台机器上第一次跑 testbench 前都要先生成一次**。

## 输出文件

| 文件 | 内容 | 用途 |
|---|---|---|
| `golden_frame_<i>.hex` | 第 i 组用例的 58 行,每行一个字节 | **testbench 用这个**,`$readmemh` 进 58 元素数组 |
| `golden_frames.hex` | 全部用例首尾相接 | 想一次读全部的场景 |
| `golden_frames.bin` | 同上的二进制 | 喂 Exchange Simulator / 与 Wireshark 抓包对照 |
| `golden_frames_meta.json` | 每组的输入字段 + 整帧 hex | 人看的,排查时对字段 |

testbench 一律读 `golden_frame_<i>.hex`,**不要**去 `golden_frames.hex` 里按偏移取——
手写的 `base + i` 偏移算错一次,读到的是另一组用例的字节,查起来会误导到 RTL 上去。

## 测试用例即契约

`main()` 里那两组值不是随手填的,任何比对它们输出的 testbench 都必须驱动**完全相同**的
字段值:

| | order_id | symbol | side | qty | price |
|---|---|---|---|---|---|
| case 0 `Basic_Buy_Limit` | 10001 | 1 | 1 | 100 | 1505000 |
| case 1 `Basic_Sell_Limit` | 10002 | 2 | 2 | 50 | 3102000 |

挑这些值的理由:`10001 = 0x2711`、`1505000 = 0x16F6E8`,每个字节都不相同,字节错位或
字节序反了不可能碰巧比对通过;两组的 symbol 和 side 也不同,保证这两个字段的位置是被
**测出来**的,而不是被假定的。

加减用例时,`tb/tb_tx_frame_builder.sv` 顶部的 `C0_*` / `C1_*` localparam 要跟着改。

## 帧结构

```
byte  0-13 : Ethernet 头   (big-endian, 常量)
byte 14-33 : IPv4 头       (big-endian, checksum 为编译期常量)
byte 34-41 : UDP 头        (big-endian, 常量)
byte 42-57 : Table 7 payload (little-endian, struct '<IHBII1s')
byte 58-59 : pad   ← TEMAC 补,不由我们发
byte 60-63 : FCS   ← TEMAC 补,不由我们发
```

**同一帧里两种字节序**:头部字段是网络字节序(big-endian,RFC 规定),payload 字段是
little-endian(与 `Exchange_simulator/` 里 Python `struct` 的 `<` 格式一致)。不要对整帧
统一做字节序转换。

IP total length = 44、UDP length = 24,**都不包含 TEMAC 补的 pad**——以太网 padding 在
IP 之下,两个 length 字段都不数它。
