# PL TX 订单发送通路

对应主 `README.md` 3.1.3.2(FS11)的 TX 子系统。范围:从 PS 写 AXI-Lite DOORBELL
开始,到向 TEMAC TX 输出一个合法的 AXI4-Stream 帧为止。TEMAC 本身是 Xilinx 现成
IP,在板级顶层例化,本目录不实现它。

## 当前阶段:只做编译与仿真

现在的目标是**三个模块能编译、能通过单元测试和集成测试仿真**。综合、时序收敛、
TEMAC IP 配置、上板 bring-up 都不在这一轮范围内。

其他明确排除的内容:
- 诊断计数器(`tx_backpressure` 等,Table 8)——demo 阶段不做,只做最小可用流程
- 不使用 Vivado wizard 生成骨架,所有 RTL 手写(包括 `axi_lite_regbank`)

## 工具链

| | macOS | Windows |
|---|---|---|
| Verilator 仿真 | 原生(`brew install verilator`) | 需先装 WSL2,再 `apt install verilator` |
| Vivado / XSim | **不存在**(Vivado 无 macOS 版) | 原生 |
| 综合 / bitstream | **不存在** | 原生 |

**仿真统一用 Verilator**,因为它是两个平台都能跑的唯一选择。golden frame 用 Python
生成,`$readmemh` 读取,这套写法在 Verilator 和 XSim 下行为一致,将来要换 XSim 不用
改 testbench。

Mac 上可以写 RTL、lint、跑仿真,但无法综合、无法配 TEMAC IP、无法上板——这些必须
在 Windows 或 Linux 机器上做。

---

## 决定:FCS 和 padding 交给 TEMAC

**配置 TEMAC IP 时开启 FCS insertion 和 frame padding 两个选项**,我们两样都不写。
这样可以从范围里去掉一个 CRC32 模块(FCS 覆盖 payload,不像 IP header checksum 那样
是编译期常量,不能硬编码),`tx_frame_builder` 只需发满 58 字节就停。

配置 IP 时要确认这两个选项确实打开了。如果 padding 不可用,`tx_frame_builder` 需要
多发 2 个零字节、`tlast` 移到 byte 59——改动很小,但必须在配置阶段发现,而不是等一个
58 字节的非法帧上了线才发现。

### 遗留问题

1. **TEMAC 的 AXI4-Stream `tdata` 实际位宽是多少?** 目前全部按 8-bit 设计
   (8 bit × 125 MHz = 1 Gbps,结构上对得上)。如果实际更宽,需要引入 `tkeep` 并重做
   serializer。

---

## Layer 1 — 模块划分

```
              AXI4-Lite (PS)                                    AXI4-Stream (TEMAC)
PS ─────────────────────────► axi_lite_regbank ──► tx_order_latcher ──► tx_frame_builder ──► (TEMAC, 外部)
```

| 模块 | 文件 | 职责 | Owner |
|---|---|---|---|
| `axi_lite_regbank` | `../axi_lite_regbank.sv` | 唯一懂 AXI-Lite 协议的模块。译码 Table 15(0x40–0x54 段),拆包 `ORD_SYMBOL_SIDE`,实现 DOORBELL 的 write-1-to-pulse | TBD |
| `tx_order_latcher` | `tx_order_latcher.sv` | 在 `doorbell_pulse` 上采样订单字段;屏蔽忙碌期到达的 doorbell;驱动 `tx_ready` | TBD |
| `tx_frame_builder` | `tx_frame_builder.sv` | Payload Build + Frame Build 合并。打包 Table 7,拼接常量 Eth/IP/UDP 头,按字节串行输出到 AXI4-Stream | TBD |
| `tx_top` | `tx_top.sv` | 纯接线,自身无逻辑 | — |

划分理由:

- **`axi_lite_regbank` 单独拆出来**,因为 AXI-Lite 协议处理和 TX 业务逻辑是两件无关的
  事——它下游的所有模块只看到干净的信号,永远不需要认识 AWADDR/WDATA。它是 RX/TX
  **共用**模块(同一个物理寄存器组,地址段不重叠),所以放在 `pl/` 根目录下,不属于任何
  一个子系统的目录。RX 侧寄存器(SEQ、快照、timestamp,0x00–0x18)由 RX 的 owner 补。

  目前它由 `tx_top` 例化,因为今天 TX 是唯一使用者。等 RX 落地时,例化上移到一个新的
  `pl_top`——**现在不写那个顶层**,RX 还不存在,提前建等于给空气搭架子。

- **Payload Build 和 Frame Build 合并成一个模块**(主 README 图上是两个框)。两者之间
  没有任何会被独立消费的中间状态,硬拆成两级只会多两级寄存器,不产生设计价值。

- **TEMAC 是现成 IP,不是我们的 RTL**。我们的范围到"输出一个合法的 AXI4-Stream
  master"为止。

---

## Layer 2 — 接口契约

### ① `axi_lite_regbank` → `tx_order_latcher`

| 信号 | 位宽 | 方向(latcher 视角) | 说明 |
|---|---|---|---|
| `ord_symbol` | 16 | in | 已从 `ORD_SYMBOL_SIDE` 拆包,latcher 永远看不到打包的 32-bit 字 |
| `ord_side` | 8 | in | 同上 |
| `ord_qty` | 32 | in | |
| `ord_price` | 32 | in | |
| `ord_id` | 32 | in | |
| `doorbell_pulse` | 1 | in | PS 每次向 DOORBELL 写 1,产生恰好 1 拍脉冲 |
| `tx_ready` | 1 | out(回 regbank) | latcher 驱动,regbank 把它挂到 0x54 只读寄存器上 |

### ② `tx_order_latcher` → `tx_frame_builder`

| 信号 | 位宽 | 方向(frame_builder 视角) | 说明 |
|---|---|---|---|
| `cmd_valid` | 1 | in | 1 拍脉冲。只会在 `frame_builder_busy == 0` 时出现——latcher 屏蔽了忙碌期到达的 doorbell,所以 frame_builder 不需要反过来给一根 ready 拒绝命令。**前提是 `frame_builder_busy` 组合拉高,见下** |
| `cmd_order_id/symbol/side/qty/price` | 32/16/8/32/32 | in | latcher 在整个忙碌窗口内保持不变,frame_builder 直接读,不需要自己复制一份 |
| `frame_builder_busy` | 1 | out(回 latcher) | **必须在 `cmd_valid` 的同一拍组合地拉高**,保持到整帧最后一个字节握手完成。如果做成寄存器输出(晚一拍拉高),落在这一拍空隙里的 doorbell 会穿过 latcher 的屏蔽,把正在发送的 `cmd_*` 改掉 |

**TX_READY 和忙碌屏蔽是互补的两层,不是同一件事的两种说法:**

- TX_READY 是面向 PS 的协商信号——PS 写 DOORBELL 前应该先查它。但这依赖 PS 软件自觉
  配合。
- 忙碌期屏蔽 doorbell 是**硬件兜底**——不管 PS 是否守规矩、是否踩中竞态窗口,正在发送
  的帧绝对不会被半路篡改。

一层负责效率(别让 PS 白写),一层负责正确性(订单路径不能靠"大家都很乖"这种假设)。

### ③ `tx_frame_builder` → TEMAC(AXI4-Stream)

| 信号 | 位宽 | 方向 | 说明 |
|---|---|---|---|
| `m_axis_tdata` | 8 | out | **假设值**,未确认——见遗留问题 1 |
| `m_axis_tvalid` | 1 | out | `rst_n` 拉低期间必须为 0(AXI4-Stream 硬性要求) |
| `m_axis_tlast` | 1 | out | 在 byte 57 拉高,即我们发送的最后一个字节 |
| `m_axis_tready` | 1 | in | 真实反压——TEMAC 是和 RX 共用的硬件资源,可能忙 |

不需要 `tkeep`:仅在 8-bit `tdata` 下成立,每次传输都是完整一个字节。如果遗留问题 1
的答案是更宽的总线,这条要重新考虑。

**帧布局。**我们发送 byte 0–57 并拉 `tlast`,pad 和 FCS 由 TEMAC 补:

| 字节 | 内容 | 字节序 | 谁发 |
|---|---|---|---|
| 0–13 | Ethernet 头 | big-endian | 我们 |
| 14–33 | IP 头,total length = 44,checksum 为预计算常量 | big-endian | 我们 |
| 34–41 | UDP 头,length = 24 | big-endian | 我们 |
| 42–57 | Table 7 payload(16B) | little-endian | 我们 |
| 58–59 | 补齐到 60B 以太网最小帧 | — | TEMAC |
| 60–63 | FCS(CRC32) | — | TEMAC |

两个注意点:

1. **同一帧里两种字节序**:Eth/IP/UDP 头字段必须是 big-endian(网络字节序,RFC 规定);
   Table 7 payload 字段是 little-endian(与 `Exchange_simulator/` 里 Python `struct`
   的 `<` 格式一致)。**不要对整帧统一做字节序转换。**
2. **pad 字节不计入** IP total length 和 UDP length——以太网 padding 在 IP 之下,两个
   length 字段都不数它,接收端靠 IP total length 找真实数据的末尾。
3. **IP header checksum 是编译期常量**。点对点链路上所有头字段(MAC、IP、端口、长度)
   都是固定的,所以 checksum 也是固定的:算一次硬编码进去,不要做运行时加法器。

---

## Layer 3 — 各模块微架构

**三个模块共同的前提:**订单事件最快 1000 笔/秒(FS3 限制),而时钟是 125 MHz
(8 ns/拍),平均每 12.5 万拍才来一笔。这条链子上任何模块都不会遇到"上一笔没处理完
下一笔已经堆过来"的场景,所以**流水线(持续背靠背吞吐)对三个模块全部不成立**,下面
不再逐个重复这个论证。

排除流水线后,每个模块归入剩下三类形状之一:

- **① 1 拍纯组合** —— 一个时钟边沿内既做判断又完成动作,不需要跨拍记忆状态。
- **② 固定步数顺序 FSM** —— 需要若干拍,但拍数和步骤顺序在设计时就确定,不依赖任何
  外部阻塞条件。
- **③ 计数器驱动的 serializer FSM** —— 拍数不固定,由一个每拍重新检验的条件(比如
  `ready`)决定计数器推不推进。

| 模块 | 分类 | 理由 |
|---|---|---|
| `axi_lite_regbank` | ② | AXI-Lite 的 AW/W 是独立通道,协议不保证 AWVALID 和 WVALID 同拍到达,slave 必须跨拍记住"地址到了,还在等数据"——这就排除了 ①。等两者到齐本身是条件驱动的,所以实际上更接近一个只迭代一次的 ③,但无论如何是个小顺序 FSM,不是纯组合 |
| `tx_order_latcher` | ① | `doorbell_pulse` 和 `frame_builder_busy` 都是持续驱动、同拍可得的信号,不存在"这一拍只到了一半信息"的情况。`cmd_valid = doorbell_pulse & !frame_builder_busy` 和 `cmd_*` 的捕获(clock-enable = `cmd_valid`)都在一个时钟边沿内解决。**不需要 FSM** |
| `tx_frame_builder` | ③ | 58 字节内容 / 每拍 1 字节的接口,数据量本身就排除 ①。实际需要多少拍取决于 `m_axis_tready` 拉低多久——这是每拍重新检验的外部条件,不是设计期固定的步数,所以排除 ② 落入 ③:一个只在 `tready` 成立时推进的字节计数器 |

`tx_frame_builder` 内部还有一个**未定的实现选择**(由实现者决定):

- **(A)** 在 `cmd_valid` 那一拍,把常量头 + 格式化后的 payload 拷进一个 480-bit 本地
  寄存器,之后计数器对这份拷贝切片;
- **(B)** 不拷贝,计数器每拍组合地在常量头 ROM 和 `cmd_*` 之间选择——因为接口 ② 已经
  保证 `cmd_*` 在整个忙碌窗口内稳定,所以这样是安全的。

(B) 不占额外寄存器,倾向 (B),除非那个 mux/case 写出来太难维护再退回 (A)。

---

## 单元测试要求

每个模块的 owner 在填完模块 body 后,自己写对应的 testbench。**不要搭完整的 AXI-Lite
VIP/BFM**——一个三十行的 SV task 完成一次写事务就够了。不做 constrained-random,不做
覆盖率。

下面列的是**必须覆盖的用例**,因为这些行为坏掉是静默的,不写针对性用例就发现不了。

### `axi_lite_regbank`

- [ ] 写 0x50 → `doorbell_pulse` **恰好 1 拍**(不是 2 拍,不是电平保持)
- [ ] 写 0x50 但数据为 0 → **不产生脉冲**
- [ ] 写 `ORD_SYMBOL_SIDE` = 0x00020001 → `ord_symbol == 1` 且 `ord_side == 2`
- [ ] **AW 和 W 不同拍到达,两种先后顺序各测一次** —— 这是这个模块整个 FSM 存在的
      理由,不测等于没测
- [ ] 读 0x54 → 返回 `{31'b0, tx_ready}`
- [ ] 复位期间:所有 ready/valid 为 0,`doorbell_pulse` 为 0
- [ ] 访问未映射地址不挂死,返回 OKAY 响应

### `tx_order_latcher`

- [ ] 空闲时来 doorbell → `cmd_valid` 出现 1 拍,`cmd_*` 捕获到正确的 `ord_*` 值
- [ ] **忙碌时来 doorbell → 没有 `cmd_valid`,且 `cmd_*` 保持不变** —— 这是整套设计的
      安全不变量,这一条比其他所有用例加起来都重要
- [ ] `tx_ready` 始终等于 `!frame_builder_busy`
- [ ] 复位:`cmd_valid` 为 0

### `tx_frame_builder`

- [ ] 一帧**恰好 58 字节**,`tlast` 出现在最后一个字节上
- [ ] **中途拉低 `tready` 若干拍 → 字节不丢、不重复**(反压测试)
- [ ] byte 42–57 的字段位置和字节序与 Table 7 一致
- [ ] byte 0–41 与常量头逐字节一致(含预计算的 IP checksum)
- [ ] `frame_builder_busy` 与 `cmd_valid` **同一拍**拉高(锁死的组合要求)
- [ ] 复位:`m_axis_tvalid` 为 0

---

## 集成测试:黄金帧比对

一个测试,跑通 `tx_top` 的完整流程:

1. 通过 AXI-Lite 写入 4 个订单字段,再写 DOORBELL
2. 收下 AXI4-Stream 上吐出的全部字节
3. 与一份**逐字节的期望帧**比对

**期望帧用 Python 生成**:`Exchange_simulator/` 那边本来就知道 Table 7 的 struct 布局,
写个小脚本吐出 58 字节的 hex 文件,testbench 用 `$readmemh` 读进来比。这样 RTL 和
Python oracle 对 Table 7 的理解**从构造上就一致**,不会出现两边各自实现、上板才发现
对不上的情况。

建议至少跑两组数据(不同的 order_id/qty/price/side),确认变化的字段确实跟着变、常量
头确实不变。

### 仿真测不到的部分

**TEMAC 是否真的补了 pad 和 FCS,testbench 验证不了。**那是上板后用 Wireshark 抓包才能
确认的,也正是主 README 里 FS11 写的验证方法。这件事留给板级 bring-up,不要指望仿真
兜住。

---

## 任务分配

| # | 任务 | 依赖 | Owner |
|---|---|---|---|
| 1 | `axi_lite_regbank` 实现 + 单元测试 | 无 | TBD |
| 2 | `tx_order_latcher` 实现 + 单元测试 | 无 | TBD |
| 3 | `tx_frame_builder` 实现 + 单元测试 | 无 | TBD |
| 4 | Python golden frame 生成脚本 | 无 | TBD |
| 5 | 集成测试 testbench | 1、2、3、4 | TBD |

1、2、3 之间没有依赖,接口已经锁死,可以并行开工。

`axi_lite_regbank` 是 RX 和 TX 都要用的模块,建议**优先做、且只由一个人写**——两边都
依赖它的输出信号,两个人同时改一个文件容易冲突。
