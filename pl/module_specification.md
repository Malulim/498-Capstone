# PL 模块规格与验证手册

本文回答三个问题:**每个模块是干什么的、怎么单独测它、怎么合起来测。**

设计取舍的论证不在这里 —— 那些在 `tx_logic/README.md`(模块划分理由、接口契约、
链路常量决定)和主 `README.md`(3.1.3.2 TX 子系统、Table 15 寄存器映射、TEMAC IP
配置契约)。本文是操作手册:接口是什么、不变量是什么、命令怎么敲。

**当前范围:仿真验证。**综合、时序收敛、TEMAC IP 配置、上板 bring-up 都还没做。
lint 通过和仿真通过**不等于**综合会过 —— 这是三道独立的门槛。

---

## 0. 跑之前

### 环境

需要 **Verilator ≥ 5.0**。Windows 上装在 WSL2 里(`apt install verilator`),macOS 用
`brew install verilator`。Vivado / XSim 不是必需的,本文所有命令都是 Verilator。

### 两个会直接卡住的坑

**① `--Mdir` 不能指向带空格的目录。** `verilated.mk` 里 GNU Make 明确拒绝含空格的
路径,而课程目录 `ECE 4A/ECE 498A/` 就带空格:

```
*** Unsupported: GNU Make cannot build in directories containing spaces
```

源文件放在带空格的路径下没问题(Verilator 自己能读),**只有编译输出目录**要挪走。
本文一律用 `~/aqta_sim/`。

**② 命令必须带 `--timescale 1ns/1ps`。** RTL 文件里不写 `` `timescale ``(那是仿真
属性,不该进综合源),但 testbench 里有,于是 Verilator 报 `TIMESCALEMOD`;加了
`--Wall` 之后 warning 升成 error,构建直接失败。

### 黄金帧:先生成,否则两个测试跑不了

`tx_frame_builder` 和 `tx_top` 的 testbench 都要读黄金帧文件。这些文件**不在仓库里**
(`pl/tx_logic/sim/` 在 `.gitignore` 中),每台机器第一次跑之前要自己生成一次:

```bash
python3 pl/tx_logic/scripts/generate_golden_frames.py <输出目录>
```

`$readmemh` 用的是**相对路径**,所以仿真可执行文件必须**在 hex 文件所在目录下运行**。
下面的命令都把黄金帧和可执行文件放在同一个目录里。

---

## 1. 系统总览

```
        AXI4-Lite (PS, M_AXI_GP0)                                AXI4-Stream (→ TEMAC)
PS ──────────────────────────► axi_lite_regbank ──► tx_order_latcher ──► tx_frame_builder ──► TEMAC ──► PHY
                                      ▲                    │                    │              (Xilinx IP,
                                      └── tx_ready ────────┘                    │               不在本仓库)
                                                           └── frame_builder_busy┘
```

PS 先把 4 个订单字段写进寄存器,最后写 DOORBELL;DOORBELL 产生一拍脉冲,latcher 在这拍
把字段锁存成一条稳定命令,frame_builder 把它拼成 58 字节帧按字节吐给 TEMAC,TEMAC 补
pad 和 FCS 后发上线。

| 文件 | 模块 | Owner |
|---|---|---|
| `axi_lite_regbank.sv` | 寄存器组(RX/TX 共用) | lucy |
| `tx_logic/tx_order_latcher.sv` | 订单锁存 | hanyu |
| `tx_logic/tx_frame_builder.sv` | 帧构造 + 串行化 | panzy |
| `tx_logic/tx_top.sv` | 纯接线 | — |
| `tx_logic/scripts/generate_golden_frames.py` | 黄金帧 oracle | ashley |

---

## 2. `axi_lite_regbank`

**位置:** `pl/axi_lite_regbank.sv` **测试:** `pl/tb/tb_axi_lite_regbank.sv`

### 干什么

**整个 PL 里唯一懂 AXI4-Lite 协议的模块。**它把 PS 的总线事务翻译成干净的信号,让下游
永远不需要认识 AWADDR/WDATA。它是 RX 和 TX 共用的(同一个物理寄存器组,地址段不重叠),
所以放在 `pl/` 根目录而不属于任何子系统。

实现 Table 15 的 TX 窗口:

| 偏移 | 寄存器 | 方向 | 说明 |
|---|---|---|---|
| 0x40 | ORD_SYMBOL_SIDE | W | symbol 在 [15:0],side 在 [23:16],[31:24] 保留丢弃 |
| 0x44 | ORD_QTY | W | |
| 0x48 | ORD_PRICE | W | |
| 0x4C | ORD_ID | W | |
| 0x50 | DOORBELL | W | 写 1 产生恰好一拍脉冲,不存状态 |
| 0x54 | TX_READY | R | `{31'b0, tx_ready}` |

RX 窗口(0x00–0x2C)目前走 unmapped 路径:写接收后丢弃、读返回 0、一律 OKAY。RX owner
接手时在读 mux 和写 case 里各加自己的地址即可,AXI 协议部分不用碰。

### 结构

写通路是 4 态 FSM(`W_IDLE` / `W_WAIT_DATA` / `W_WAIT_ADDR` / `W_RESP`)。**这个 FSM
存在的唯一理由是 AW 和 W 是独立通道**,AXI 不保证它们同拍到达,slave 必须能拿着一半等
另一半。读通路是 2 态。

`ready` 信号只从状态寄存器组合出来,**从不从对面的 `valid` 出来** —— 没有 valid→ready
组合路径。

### 必须成立的不变量

1. **DOORBELL 脉冲恰好 1 拍**,与 PS 拖多久才接受 `BREADY` 无关。脉冲每拍默认清零,只在
   命中 0x50 且 `wdata[0]==1` 的那一拍置起。宽度是 2 拍的话,latcher 会看成两笔订单。
2. **写 0 不产生脉冲。**
3. **未映射地址必须响应,绝不 stall。**挂死 PS 的 AXI master 比丢一次杂写严重得多。
4. **复位期间所有 ready/valid 为 0。**

### 单元测试测了什么

README 清单 7 条全覆盖,另加:保留位 [31:24] 不能漏进 `ord_side`;`BREADY`/`RREADY`
拉低时 `BVALID`/`RVALID`/`RDATA` 必须保持;PS 拖长 `BREADY` 不能把 doorbell 脉冲拉宽;
读 0x50 不能触发脉冲;写只读的 0x54 无副作用;**只发了 AW 就复位、复位释放后不能补出一个
幽灵 doorbell**。

脉冲宽度由一个**独立的 monitor 进程**在每个时钟沿检查,不靠驱动 task 顺手检查 —— task
自己的时序假设一旦错了,顺手检查会跟着一起错。

反测:手工改坏 RTL 15 处(doorbell 变电平保持、`ord_side` 切错位、删掉 AW-first /
W-first 任一通路、qty/price 互换、`BVALID` 只给 1 拍、提交时用过期的 latch 值……),
**15 处全部被抓到**。

### 怎么跑

```bash
cd pl
verilator --lint-only --Wall --timescale 1ns/1ps axi_lite_regbank.sv

verilator --binary --timing --assert --Wall --timescale 1ns/1ps \
  --top-module tb_axi_lite_regbank \
  --Mdir ~/aqta_sim/regbank \
  axi_lite_regbank.sv tb/tb_axi_lite_regbank.sv
~/aqta_sim/regbank/Vtb_axi_lite_regbank
```

预期:`PASS: axi_lite_regbank (5 doorbell pulses observed)`,退出码 0。不需要黄金帧。

---

## 3. `tx_order_latcher`

**位置:** `pl/tx_logic/tx_order_latcher.sv` **测试:** `pl/tx_logic/tb/tb_tx_order_latcher.sv`

### 干什么

在 `doorbell_pulse` 那一拍把 5 个订单字段**原子地**抓成一份快照,在整个发帧窗口内保持
不变;同时**屏蔽忙碌期到达的 doorbell**;并驱动 `tx_ready` 回给寄存器组。

没有 FSM,没有队列,没有 FIFO。就是一组带使能的寄存器加一个与门。

### 必须成立的不变量

1. **忙碌时到达的 doorbell 被直接丢弃**,不排队、不补发、不报错,而且**正在发送的
   `cmd_*` 一个比特都不许变**。这是整套设计的安全不变量,比其他所有用例加起来都重要。
2. **`tx_ready` 恒等于 `!frame_builder_busy`**,包括复位期间。
3. **`cmd_valid` 必须是寄存器输出,不能写成组合。**因为 `frame_builder_busy` 要求组合地
   由 `cmd_valid` 拉起来;两条要求合起来会化简成 `cmd_valid = !cmd_valid`,一个非法组合
   反馈环。晚一拍不影响正确性也不影响性能(FS3 是 1000 笔/秒,125 MHz 下多一拍无感)。

### 两层保护是互补的,不是重复

- **TX_READY** 面向 PS,是协商信号 —— PS 写 DOORBELL 前应该先查。但这依赖软件自觉配合。
- **忙碌屏蔽** 是硬件兜底 —— 不管 PS 是否守规矩、是否踩中竞态窗口,在飞的帧绝对不会被
  半路篡改。

一层负责效率(别让 PS 白写),一层负责正确性(订单路径不能建立在"大家都很乖"的假设上)。

丢弃后的重试是 PS 的责任:重新读 `TX_READY`,确认为 1 再提交新的 doorbell。

### 单元测试测了什么

空闲时 doorbell 正确捕获全部字段;**忙碌时 doorbell 被挡且 `cmd_*` 不变**(输入持续变化
也不变);忙碌解除后不补发被丢弃的那一次;`tx_ready` 组合跟随;`cmd_valid` 确实是寄存器
输出(在 doorbell 同拍检查它还是 0);异步复位在非时钟沿也能立刻清零。

### 怎么跑

```bash
cd pl/tx_logic
verilator --lint-only --Wall --timescale 1ns/1ps tx_order_latcher.sv

verilator --binary --timing --assert --Wall --timescale 1ns/1ps \
  --top-module tb_tx_order_latcher \
  --Mdir ~/aqta_sim/latcher \
  tx_order_latcher.sv tb/tb_tx_order_latcher.sv
~/aqta_sim/latcher/Vtb_tx_order_latcher
```

预期:`PASS: tx_order_latcher`,退出码 0。不需要黄金帧。

---

## 4. `tx_frame_builder`

**位置:** `pl/tx_logic/tx_frame_builder.sv` **测试:** `pl/tx_logic/tb/tb_tx_frame_builder.sv`

### 干什么

把一条稳定订单命令拼成完整以太网帧,按字节串行输出到 AXI4-Stream。主 README 图上是
"Payload Build" 和 "Frame Build" 两个框,这里合成一个模块 —— 两者之间没有任何会被独立
消费的中间状态,硬拆只会多两级寄存器。

**帧布局:**

| 字节 | 内容 | 字节序 | 谁发 |
|---|---|---|---|
| 0–13 | Ethernet 头 | big-endian | 我们 |
| 14–33 | IPv4 头,total length = 44,checksum 为编译期常量 | big-endian | 我们 |
| 34–41 | UDP 头,length = 24 | big-endian | 我们 |
| 42–57 | Table 7 payload(16B) | **little-endian** | 我们 |
| 58–59 | pad 到 60B 最小帧 | — | **TEMAC** |
| 60–63 | FCS (CRC32) | — | **TEMAC** |

**同一帧里两种字节序,不要对整帧统一转换。**头部字段必须是网络字节序(RFC 规定);
Table 7 payload 是 little-endian(与 `Exchange_simulator/` 里 Python `struct` 的 `<`
格式一致)。两个 length 字段**都不包含 pad** —— 以太网 padding 在 IP 之下。

`IP_CHECKSUM` 是编译期常量,不做运行时加法器:点对点链路上所有头字段都固定,checksum
也就固定。**任何一个头字段变了,checksum 必须重算**(跑一次 golden 脚本即可)。

### 结构

2 态 FSM + 一个字节计数器。计数器只在 `tvalid && tready` 同时成立时前进 —— 拍数不固定,
取决于 `tready` 拉低多久。

数据通路用组合 mux(README 里的方案 B):不复制帧内容,计数器每拍在常量头和 `cmd_*` 之间
选。这样安全的前提是 latcher 保证了 `cmd_*` 在整个忙碌窗口内稳定,省下 480 个触发器。

### 必须成立的不变量

1. **`frame_builder_busy` 必须在 `cmd_valid` 的同一拍组合地拉高。**做成寄存器输出会留下
   一拍空隙,落在那拍的 doorbell 会穿过 latcher 的屏蔽,把在飞的帧改掉。
2. **一帧恰好 58 字节,`tlast` 只在最后一个字节上。**
3. **反压期间字节不丢不重。**
4. **复位时 `m_axis_tvalid` 为 0**(AXI4-Stream 硬性要求)。

### 单元测试测了什么

18 项。复位状态;恰好 58 字节;两组不同数据各自对着黄金帧逐字节比对;中途拉低 `tready`
后仍逐字节一致;常量头抽查;帧结束后回到空闲。

**其中一项值得单独说:`busy` 与 `cmd_valid` 同拍的检查必须在 `cmd_valid` 那一拍本身做。**
在"下一拍"检查是无效的 —— 那时 FSM 已经进了 `ST_SEND`,`busy` 无论组合还是寄存器输出
都是 1,把 `busy` 写成寄存器也照样通过。反测确认过:改成只看 `ST_SEND`,这一条会红。

### 怎么跑

**需要黄金帧,且必须在黄金帧所在目录下运行。**

```bash
cd pl/tx_logic
verilator --lint-only --Wall --timescale 1ns/1ps tx_frame_builder.sv

python3 scripts/generate_golden_frames.py ~/aqta_sim/fb

verilator --binary --timing --assert --Wall --timescale 1ns/1ps \
  --top-module tb_tx_frame_builder \
  --Mdir ~/aqta_sim/fb/build \
  tx_frame_builder.sv tb/tb_tx_frame_builder.sv

cd ~/aqta_sim/fb && ./build/Vtb_tx_frame_builder
```

预期:`PASS: 18  FAIL: 0` / `ALL TESTS PASSED`,退出码 0。

---

## 5. `tx_top`

**位置:** `pl/tx_logic/tx_top.sv`

纯接线,自身没有任何逻辑。往上暴露一个 AXI4-Lite slave(给 PS)和一个 AXI4-Stream
master(给 TEMAC),往下例化三个模块并把内部信号连起来。

它目前例化 `axi_lite_regbank`,因为今天 TX 是唯一使用者。**等 RX 落地时,这个例化要上移
到一个新的 `pl_top`** —— 现在不写那个顶层,RX 还不存在,提前建等于给空气搭架子。

没有独立的单元测试:没有逻辑就没什么可单独测的,它的正确性完全由下面的集成测试覆盖。

---

## 6. 集成测试

**测试:** `pl/tx_logic/tb/tb_tx_top.sv`

### 测什么

单元测试各自证明一个模块自洽;集成测试证明**接起来之后还是对的**。它跑真实的 PS 时序 ——
4 个字段写 + DOORBELL 最后 —— 然后收下 AXI4-Stream 上吐出的每一个字节,和 Python oracle
逐字节比。

| | 内容 |
|---|---|
| T1 | 复位:`tvalid`/`tlast` 为 0;`TX_READY` 读 1 |
| T2 | 订单 0 端到端 → 58 字节全对 `golden_frame_0`;doorbell 之前不出帧;发完 `TX_READY` 回 1 |
| T3 | 订单 1 + 帧中途拉低 `tready` 9 拍 → 全对 `golden_frame_1` |
| T4 | **安全不变量**:帧发送中把 4 个订单寄存器全改成另一笔订单、再敲 doorbell → 该 doorbell 被丢弃,在飞的帧一个字节没被污染,之后也不补发 |
| T5 | 丢过 doorbell 之后系统没卡死,正常提交仍然工作 |

预期 4 帧、48 项检查、0 失败。

### 两个实现细节,改这个 testbench 前要知道

**① AXI-Stream 接收器是常驻后台进程,不是每帧现起的。**doorbell 写事务返回后大约 2 拍
帧就开始吐字节,现起的收集器会和第一个字节赛跑。

**② 有两条断言用了层次化引用(白盒),这是刻意的:**

```systemverilog
assert property (@(posedge clk) disable iff (!rst_n)
  dut.cmd_valid |-> dut.frame_builder_busy);      // 同拍,不许有洞
assert property (@(posedge clk) disable iff (!rst_n)
  m_axis_tvalid |-> !dut.tx_ready);               // 帧在线上时 TX_READY 全程为 0
```

第一条是必需的,因为**纯黑盒激励物理上够不到那个窗口**:`busy` 改成寄存器只开 1 拍的洞
(`cmd_valid` 高、`state` 还在 `ST_IDLE`),而一次 AXI-Lite 写最少 3~4 拍,PS 根本发不出
间隔 1 拍的两个 doorbell。反测证实过:没有这条断言时,把 `busy` 改成寄存器输出,集成测试
**照样全绿**。加上之后 6/6 mutation 全抓到。

这条性质属于**接线本身**而不属于任何单个模块,所以由拥有接线的这一层来守。

### 怎么跑

```bash
cd pl/tx_logic
python3 scripts/generate_golden_frames.py ~/aqta_sim/top

verilator --binary --timing --assert --Wall --timescale 1ns/1ps \
  --top-module tb_tx_top \
  --Mdir ~/aqta_sim/top/build \
  tx_top.sv tx_order_latcher.sv tx_frame_builder.sv ../axi_lite_regbank.sv \
  tb/tb_tx_top.sv

cd ~/aqta_sim/top && ./build/Vtb_tx_top
```

预期:`frames observed: 4   checks passed: 48   failed: 0` / `PASS: tx_top integration`,
退出码 0。

---

## 7. 黄金帧契约

`scripts/generate_golden_frames.py` 是 **Table 7 布局和 42 字节常量头的唯一 oracle**。
RTL 里 `tx_frame_builder.sv` 的常量必须与它的 `build_network_header()` 逐字节一致。

**两条纪律:**

1. **testbench 读 `golden_frame_<i>.hex`(每组一个文件),不要去拼接的
   `golden_frames.hex` 里按偏移取。**`$readmemh` 读进 58 元素数组时文件本身就是边界;
   手写 `base + i` 偏移算错一次,读到的是**另一组用例的字节**,报出来的现象会是"RTL 字节
   序错了",会往硬件上白查很久。
2. **testbench 驱动的字段值必须与脚本 `main()` 里的用例一一对应。**tb 顶部的 `C0_*` /
   `C1_*` localparam 就是那两组的镜像,加减用例时两边一起改。

`main()` 的值是刻意挑的:`10001 = 0x2711`、`1505000 = 0x16F6E8`,每个字节都不同,错位或
字节序反了不可能碰巧对上;两组的 symbol 和 side 也不同,保证这两个字段的位置是被**测出来**
的而不是被假定的。

---

## 8. 一次跑完全部

从仓库根目录:

```bash
# 0) 黄金帧(每台机器第一次跑,或改过脚本/常量之后)
python3 pl/tx_logic/scripts/generate_golden_frames.py ~/aqta_sim/golden

# 1) lint,四个都要 clean
cd pl
verilator --lint-only --Wall --timescale 1ns/1ps axi_lite_regbank.sv
verilator --lint-only --Wall --timescale 1ns/1ps tx_logic/tx_order_latcher.sv
verilator --lint-only --Wall --timescale 1ns/1ps tx_logic/tx_frame_builder.sv
verilator --lint-only --Wall --timescale 1ns/1ps --top-module tx_top \
  tx_logic/tx_top.sv tx_logic/tx_order_latcher.sv tx_logic/tx_frame_builder.sv \
  axi_lite_regbank.sv

# 2) 三个单元测试(顺序无所谓,互不依赖)
verilator --binary --timing --assert --Wall --timescale 1ns/1ps \
  --top-module tb_axi_lite_regbank --Mdir ~/aqta_sim/regbank \
  axi_lite_regbank.sv tb/tb_axi_lite_regbank.sv
~/aqta_sim/regbank/Vtb_axi_lite_regbank

cd tx_logic
verilator --binary --timing --assert --Wall --timescale 1ns/1ps \
  --top-module tb_tx_order_latcher --Mdir ~/aqta_sim/latcher \
  tx_order_latcher.sv tb/tb_tx_order_latcher.sv
~/aqta_sim/latcher/Vtb_tx_order_latcher

mkdir -p ~/aqta_sim/fb && cp ~/aqta_sim/golden/golden_frame_*.hex ~/aqta_sim/fb/
verilator --binary --timing --assert --Wall --timescale 1ns/1ps \
  --top-module tb_tx_frame_builder --Mdir ~/aqta_sim/fb/build \
  tx_frame_builder.sv tb/tb_tx_frame_builder.sv
(cd ~/aqta_sim/fb && ./build/Vtb_tx_frame_builder)

# 3) 集成测试(依赖前面三个都过)
mkdir -p ~/aqta_sim/top && cp ~/aqta_sim/golden/golden_frame_*.hex ~/aqta_sim/top/
verilator --binary --timing --assert --Wall --timescale 1ns/1ps \
  --top-module tb_tx_top --Mdir ~/aqta_sim/top/build \
  tx_top.sv tx_order_latcher.sv tx_frame_builder.sv ../axi_lite_regbank.sv \
  tb/tb_tx_top.sv
(cd ~/aqta_sim/top && ./build/Vtb_tx_top)
```

**全部通过的样子:**

```
PASS: axi_lite_regbank (5 doorbell pulses observed)
PASS: tx_order_latcher
PASS: 18  FAIL: 0 / ALL TESTS PASSED
frames observed: 4   checks passed: 48   failed: 0 / PASS: tx_top integration
```

四个 testbench 失败时都以**非零退出码**结束(`$fatal`),可以直接 `&&` 串起来或进 CI。
报告失败却让调用方以为成功的 testbench 等于没测。

**单元测试先于集成测试。**集成测试失败时,如果三个单元测试都是绿的,问题几乎一定在接线
或接口契约上,而不在模块内部 —— 这正是分两层的价值。

---

## 9. 仿真测不到的部分

以下全部只能上板确认,**仿真会一路全绿**:

| | 为什么测不到 |
|---|---|
| TEMAC 是否真的补了 pad 和 FCS | 仿真里 TEMAC 不存在,AXI-Stream 接收端是我们自己写的桩。配置错了就是一个 58 字节的非法帧上线 |
| `tx_axis_mac_tuser` 是否被拉低 | 它是 TEMAC 的**输入**(PG051 Table 2, p.20),拉高会让 MAC 主动把帧打成错误帧。`tx_top` 没引出这个端口,**板级顶层必须接地**,悬空则每帧都废 |
| 125 MHz 时序收敛 | 需要 Vivado 综合 + 实现,NFS6 要求 WNS > 0 |
| 资源利用率 | NFS6 要求 < 75% LUT、< 85% BRAM |
| 异步复位释放的亚稳态 | 现在没有复位同步器 |

验证方法是 Wireshark 抓包(主 README 中 FS11 的验证手段)。TEMAC IP 的完整配置契约在主
`README.md` 的 **3.1.2 Decision 1 → TEMAC IP Customization Contract**,逐条标了 PG051
页码 —— **配 IP 之前先读那一节**。
