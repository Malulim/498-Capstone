# PL TX 订单发送通路

对应主 `README.md` 3.1.3.2(FS11)的 TX 子系统。范围:从 PS 写 AXI-Lite DOORBELL
开始,到向 TEMAC TX 输出一个合法的 AXI4-Stream 帧为止。TEMAC 本身是 Xilinx 现成
IP,在板级顶层例化,本目录不实现它。

> **这份文档写给要动 RTL 的人**,讲的是**为什么这样设计**:模块怎么划分、接口契约锁死了
> 什么、每个决定放弃了什么替代方案。
>
> **要跑测试、或想搞清楚这些模块各自是干什么的,看
> [`../module_specification.md`](../module_specification.md)** —— 那里有每个模块的职责、
> 必须成立的不变量、覆盖了哪些用例,以及所有可直接粘贴的命令。
>
> **命令只写在那一份里。**同一批命令抄在两处必然漂移 —— 本文档曾经就有三处 `verilator`
> 命令和实际在用的不一致(少 `--Wall`、少 `--timescale`),所以这里一条命令都不留。

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

跑 Verilator 时有两个跟本仓库路径有关的坑,和 RTL 无关但会直接卡住:

1. **`--Mdir` 不能指向带空格的目录。** `verilated.mk` 里 GNU Make 明确拒绝路径含空格
   (报 `Unsupported: GNU Make cannot build in directories containing spaces`),而课程
   目录 `ECE 4A/ECE 498A/` 就带空格。源文件放在带空格的路径下没问题(Verilator 自己
   能读),只有**编译输出目录**必须挪到无空格的地方,比如 WSL 里的 `~/aqta_sim/`。
   下面的命令都这么写。
2. **RTL 文件里不写 `` `timescale ``**(那是仿真属性,不该进综合源),但 testbench 里
   有,于是 Verilator 会报 `TIMESCALEMOD`,加 `--Wall` 后直接变成 error。命令里统一带
   `--timescale 1ns/1ps` 给没声明的模块一个默认值即可。

---

## 决定:FCS 和 padding 交给 TEMAC

我们两样都不写,`tx_frame_builder` 发满 58 字节就停。这样能从范围里去掉一个 CRC32 模块
(FCS 覆盖 payload,不像 IP header checksum 那样是编译期常量,不能硬编码)。

**已查 PG051 v9.0 确认(p.99):padding 和 FCS 插入是 TEMAC 的默认行为,不是要去打开的
选项。**原文:*"When fewer than 46 bytes of data are supplied by you to the MAC core, the
transmitter module adds padding up to the minimum frame length. The exception to this is
when the MAC core is configured for user-passed FCS."* 我们发 58 字节 = 14B 以太网头 +
44B 数据,44 < 46,所以 MAC 补到 60 字节最小帧再加 4 字节 FCS,凑成合法的 64 字节。

所以配置时**要做的是"别打开 user-supplied FCS passing"**(保持默认关闭),而不是去勾
两个开关 —— 这跟本节原来的写法是反的。一旦打开那个选项,补 pad 和算 FCS 两件事**同时**
落回我们头上,而我们两件都没实现;届时 MAC 只会在帧尾补零,对端每一帧都判 FCS 错误,
而我们自己的 transmit statistics 依然报告帧是好的。

完整的 IP 配置契约(含 RGMII、frame filter、`tx_axis_mac_tuser` 必须拉低等)在主
`README.md` 的 **3.1.2 Decision 1 → TEMAC IP Customization Contract** 一节,那里逐条给了
PG051 页码。

### 遗留问题

~~1. **TEMAC 的 AXI4-Stream `tdata` 实际位宽是多少?**~~ **已解决**:PG051 Table 2
(p.20)确认 `tx_axis_mac_tdata[7:0]`,就是 8 位。按字节串行的设计是对的,不需要
`tkeep`。

(本节暂无未决问题。)

---

## 决定:链路常量的单一来源

`tx_frame_builder.sv` 里那 42 字节常量头(MAC / IP / 端口 / IP checksum)和
`scripts/generate_golden_frames.py` 的 `build_network_header()` **必须逐字节一致**。
两边曾各写各的(RTL:广播 MAC + 192.168.1.1↔.2 + 端口 9000;脚本:单播 LAA MAC +
192.168.1.10↔.20 + 端口 12345/12346),**每一个字段都不同**——这正是本文档开头警告过的
"两边各自实现、上板才发现对不上"。

**逐字段按技术上更优的那个选,不按"哪边改起来省事"选。**黄金帧重新生成一次是几秒钟的事,
不构成选型理由。结果是大部分字段跟脚本、DF 位跟 RTL:

| 字段 | 采用值 | 来自 | 依据 |
|---|---|---|---|
| dst MAC | `02:00:00:00:00:02` | 脚本 | 见下 |
| src MAC | `02:00:00:00:00:01` | 脚本 | 见下 |
| EtherType | `0x0800` | 一致 | 主 README 3.1.3.1 明文 |
| **IP flags/frag** | **`0x4000` (DF)** | **RTL** | **见下** |
| TTL / protocol | `64` / `17` | 一致 | protocol=17 是主 README 3.1.3.1 明文 |
| src IP / dst IP | `192.168.1.10` / `192.168.1.20` | 脚本 | 跟 oracle |
| **UDP dst port** | **`12346`** | 脚本 | **`ExchangeSimulator.py` 硬约束** |
| UDP src port | `12345` | 脚本 | 与行情下发端口一致 |
| UDP checksum | `0x0000` | 一致 | 主 README 3.1.3.1:P2P 链路绕过,靠以太网 FCS |
| IP checksum | `0xB752` | 算出 | 上面这套常量的函数,非独立选项 |

**UDP 目的端口 12346 是外部钉死的。**`Exchange_simulator/ExchangeSimulator.py` 的
`receive_and_log_orders()` 里 `sock.bind(("0.0.0.0", 12346))` 就是订单接收端;
`start_paced_replay(..., 12345)` 是行情下发端。发到别的端口没人收。这条不是取舍,
是约束——**改这两个端口前先改 simulator**。

**dst MAC 不用广播。**原 RTL 是 `FF:FF:FF:FF:FF:FF`。主 README 3.1.3.1 写明 TEMAC
"filters non-matching destination MAC addresses",即两端都靠单播 MAC 过滤收帧,TX 发广播
和 RX 的设计前提矛盾;而且广播帧会被链路上任何设备泛洪,NFS2 要求的"10 分钟零不明丢帧"
就得先解释这些泛洪副本。`02:` 开头是 locally administered 单播地址,私有点对点链路的标准
选择。

**IP flags 取 DF(`0x4000`),这一条是脚本跟 RTL 改。**订单帧是定长的,任何 MTU 下都不会
分片,置 DF 位是表达"这个数据报不许被分片"的规范做法。在这条点对点链路上两种写法行为
完全相同,但 DF 陈述了意图:将来若这条路径上出现了会分片的中间设备,DF 会让它回一个
ICMP 错误,而不是**把一笔订单悄悄劈成两半**。脚本已同步改为 `0x4000`,黄金帧已重新生成。

`IP_CHECKSUM` 是上述常量的函数,不是独立可选项——**任何一个头字段变了,checksum 必须
重算**。跑一次脚本,`meta.json` 里的头 20 字节就是新值(DF 改动就把它从 `0xF752` 变成了
`0xB752`)。它是编译期常量,不做运行时加法器。

改完后 `tb_tx_frame_builder` 对着重新生成的黄金帧跑 **18 项全过**,含反压场景逐字节一致。

---

## Layer 1 — 模块划分

```
              AXI4-Lite (PS)                                    AXI4-Stream (TEMAC)
PS ─────────────────────────► axi_lite_regbank ──► tx_order_latcher ──► tx_frame_builder ──► (TEMAC, 外部)
```

| 模块 | 文件 | 职责 | Owner |
|---|---|---|---|
| `axi_lite_regbank` | `../axi_lite_regbank.sv` | 唯一懂 AXI-Lite 协议的模块。译码 Table 15(0x40–0x54 段),拆包 `ORD_SYMBOL_SIDE`,实现 DOORBELL 的 write-1-to-pulse | lucy |
| `tx_order_latcher` | `tx_order_latcher.sv` | 在 `doorbell_pulse` 上采样订单字段;屏蔽忙碌期到达的 doorbell;驱动 `tx_ready` | hanyu |
| `tx_frame_builder` | `tx_frame_builder.sv` | Payload Build + Frame Build 合并。打包 Table 7,拼接常量 Eth/IP/UDP 头,按字节串行输出到 AXI4-Stream | panzy |
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
| `cmd_valid` | 1 | in | 1 拍脉冲,是 `doorbell_pulse & !frame_builder_busy` 的**寄存器**输出(比 doorbell 晚 1 拍,见下)。latcher 已屏蔽忙碌期到达的 doorbell,所以 frame_builder 不需要反过来给一根 ready 拒绝命令,**收到 `cmd_valid` 就无条件起帧** |
| `cmd_order_id/symbol/side/qty/price` | 32/16/8/32/32 | in | latcher 在整个忙碌窗口内保持不变,frame_builder 直接读,不需要自己复制一份 |
| `frame_builder_busy` | 1 | out(回 latcher) | **必须在 `cmd_valid` 的同一拍组合地拉高**,保持到整帧最后一个字节握手完成。如果做成寄存器输出(晚一拍拉高),落在这一拍空隙里的 doorbell 会穿过 latcher 的屏蔽,把正在发送的 `cmd_*` 改掉 |

**`cmd_valid` 必须是寄存器输出,不能写成组合。**因为 `frame_builder_busy` 要求组合地由 `cmd_valid` 拉起来,如果 `cmd_valid` 也组合地等于 `doorbell_pulse & !frame_builder_busy`, 两条要求合起来就是 `cmd_valid = doorbell & !(active | cmd_valid)`,在 `doorbell=1`、`active=0` 时化简成 `cmd_valid = !cmd_valid`——一个非法组合反馈环,仿真可能不收敛或产生 `X`,综合/时序工具也会报告 combinational loop。晚一拍不影响正确性 (第 N 拍接受、第 N+1 拍 `cmd_valid` 与 `busy` 同时拉高,落在 N+1 的下一个 doorbell 照样被挡住),也不影响性能(FS3 是 1000 笔/秒,125 MHz 下多一拍无感)。

**TX_READY 和忙碌屏蔽是互补的两层,不是同一件事的两种说法:**

- TX_READY 是面向 PS 的协商信号——PS 写 DOORBELL 前应该先查它。但这依赖 PS 软件自觉
  配合。
- 忙碌期屏蔽 doorbell 是**硬件兜底**——不管 PS 是否守规矩、是否踩中竞态窗口,正在发送
  的帧绝对不会被半路篡改。

一层负责效率(别让 PS 白写),一层负责正确性(订单路径不能靠"大家都很乖"这种假设)。

### ③ `tx_frame_builder` → TEMAC(AXI4-Stream)

| 信号 | 位宽 | 方向 | 说明 |
|---|---|---|---|
| `m_axis_tdata` | 8 | out | 已由 PG051 Table 2(p.20)确认:`tx_axis_mac_tdata[7:0]` |
| `m_axis_tvalid` | 1 | out | `rst_n` 拉低期间必须为 0(AXI4-Stream 硬性要求) |
| `m_axis_tlast` | 1 | out | 在 byte 57 拉高,即我们发送的最后一个字节 |
| `m_axis_tready` | 1 | in | 真实反压——TEMAC 是和 RX 共用的硬件资源,可能忙 |

不需要 `tkeep`:8-bit `tdata` 下每次传输都是完整一个字节。位宽已经查证,这条不再是假设。

另外两条 PG051 明文规定、但仿真兜不住的义务(详见主 README 的 IP 配置契约一节):
**`tvalid` 在 `tlast` 之前绝对不能撤**(p.99,MAC 不缓冲,提前撤等于 underrun,帧被中止);
**`tx_axis_mac_tuser` 必须拉低**(p.20,它是输入,拉高会让 MAC 主动把帧打成错误帧)——
`tx_top` 没引出这个端口,得由板级顶层接地。

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
| `tx_order_latcher` | ④ | 接受判断 `accept = doorbell_pulse & !frame_builder_busy` 在当前拍完成；`cmd_valid` 和 `cmd_*` 在时钟边沿一起更新并跨拍保持。它有输出寄存器状态,但没有 FSM 或订单队列 |
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

已实现,testbench 在 `../tb/tb_axi_lite_regbank.sv`(自检查,通过则打印 `PASS`)。

- [x] 写 0x50 → `doorbell_pulse` **恰好 1 拍**(不是 2 拍,不是电平保持)
- [x] 写 0x50 但数据为 0 → **不产生脉冲**
- [x] 写 `ORD_SYMBOL_SIDE` = 0x00020001 → `ord_symbol == 1` 且 `ord_side == 2`
- [x] **AW 和 W 不同拍到达,两种先后顺序各测一次** —— 这是这个模块整个 FSM 存在的
      理由,不测等于没测
- [x] 读 0x54 → 返回 `{31'b0, tx_ready}`
- [x] 复位期间:所有 ready/valid 为 0,`doorbell_pulse` 为 0
- [x] 访问未映射地址不挂死,返回 OKAY 响应

额外覆盖(不在原清单里,但都是静默错误):`ORD_SYMBOL_SIDE` 的保留位 [31:24] 不能漏进
`ord_side`;`BREADY`/`RREADY` 被拉低时 `BVALID`/`RVALID`/`RDATA` 必须保持;PS 把
`BREADY` 拖久了不能把 doorbell 脉冲拉宽;读 0x50 不能触发脉冲;写只读的 0x54 无副作用;
以及**半个写事务(只发了 AW)期间复位,复位释放后不能补出一个幽灵 doorbell**。

脉冲宽度不是靠 task 顺手检查的,而是一个独立的 monitor 进程在每个时钟沿盯着——task
自己的时序假设一旦错了,顺手检查也会跟着一起错。

这套用例做过 mutation 反测(手工改坏 RTL 15 处:doorbell 变电平保持、`ord_side` 切错位、
删掉 AW-first / W-first 中的一条通路、qty/price 互换、`BVALID` 只给 1 拍、提交时用了过期的
latch 值……),15 处全部被 testbench 抓到。

跑法见 [`../module_specification.md`](../module_specification.md)。

**Table 15 之外的一处有意偏离:**0x40–0x4C 在 Table 15 里是 W-only,但这里给了读回。
理由是 AXI-Lite 写是 posted 的,上板 bring-up 时"PS 那 5 个写到底落没落"是最先要排查的
问题,读回只多一个 mux。**PS 固件不许依赖它**,Table 15 仍然是 W-only 的契约。

RX 侧窗口(0x00–0x2C)现在全部走 unmapped 路径:写被接收后丢弃、读返回 0、都是 OKAY。
RX owner 接手时在读 mux 和写 case 里各加自己的地址即可,AXI 协议部分不用再碰。

### `tx_order_latcher`

- [x] 空闲时来 doorbell → `cmd_valid` 出现 1 拍,`cmd_*` 捕获到正确的 `ord_*` 值
- [x] **忙碌时来 doorbell → 没有 `cmd_valid`,且 `cmd_*` 保持不变** —— 这是整套设计的
      安全不变量,这一条比其他所有用例加起来都重要
- [x] `tx_ready` 始终等于 `!frame_builder_busy`
- [x] 复位:`cmd_valid` 为 0

当前模块没有 pending buffer 或 FIFO。busy 时到达的 doorbell 会被直接丢弃；需要重试时, 由 PS 重新读取 `TX_READY` 并提交新的 doorbell。

从 `pl/tx_logic/` 运行 lint 和自检查 testbench(`--Mdir` 见工具链那节的路径限制):

跑法见 [`../module_specification.md`](../module_specification.md)。

### `tx_frame_builder`

- [x] 一帧**恰好 58 字节**,`tlast` 出现在最后一个字节上
- [x] **中途拉低 `tready` 若干拍 → 字节不丢、不重复**(反压测试)
- [x] byte 42–57 的字段位置和字节序与 Table 7 一致
- [x] byte 0–41 与常量头逐字节一致(含预计算的 IP checksum)
- [x] `frame_builder_busy` 与 `cmd_valid` **同一拍**拉高(锁死的组合要求)
- [x] 复位:`m_axis_tvalid` 为 0

最后那条**必须在 `cmd_valid` 那一拍本身检查**。在"下一拍"检查是无效的:那时 FSM 已经
进了 `ST_SEND`,`busy` 无论组合还是寄存器输出都是 1,把 `busy` 写成寄存器也照样通过。
现在的 tb 在同一拍查,并反测确认过——把 `busy` 改成只看 `ST_SEND`,这一条会红。

**testbench 需要黄金帧文件在当前目录下**,而且它驱动的字段值必须与
`scripts/generate_golden_frames.py` 的 `main()` 完全一致(见下节):

跑法见 [`../module_specification.md`](../module_specification.md)。

---

## 黄金帧文件契约

`scripts/generate_golden_frames.py` 是 Table 7 布局和 42 字节常量头的**唯一 oracle**。
它一次输出这些文件:

| 文件 | 内容 | 谁用 |
|---|---|---|
| `golden_frame_<i>.hex` | 第 i 组用例的 58 行,每行一字节 | 单元/集成 testbench 的 `$readmemh` |
| `golden_frames.hex` | 全部用例首尾相接 | 想一次读全部的场景 |
| `golden_frames.bin` | 同上的二进制 | 喂 simulator / Wireshark 对照 |
| `golden_frames_meta.json` | 每组用例的输入字段 + 整帧 hex | 人看的,排查时对字段 |

**testbench 一律读 `golden_frame_<i>.hex`,不要去 `golden_frames.hex` 里按偏移取。**
`$readmemh` 读进一个 58 元素的数组时,文件本身就是边界;而手写 `base + i` 偏移一旦算错,
读到的是**另一组用例的字节**,报出来的现象是"字节序错了"——会往 RTL 上查很久。

**驱动值必须与 `main()` 里的用例一一对应。**tb 里的 `C0_*` / `C1_*` localparam 就是
`main()` 那两组的镜像,加减用例时两边一起改。`main()` 的值是刻意挑的:`10001 = 0x2711`、
`1505000 = 0x16F6E8`,每个字节都不同,错位或字节序反了不可能碰巧对上;两组的 symbol 和
side 也不同,保证这两个字段的位置是被测出来的而不是被假定的。

## 集成测试:黄金帧比对

一个测试,跑通 `tx_top` 的完整流程:

1. 通过 AXI-Lite 写入 4 个订单字段,再写 DOORBELL
2. 收下 AXI4-Stream 上吐出的全部字节
3. 与一份**逐字节的期望帧**比对

**期望帧用 Python 生成**:`Exchange_simulator/` 那边本来就知道 Table 7 的 struct 布局,
写个小脚本吐出 58 字节的 hex 文件,testbench 用 `$readmemh` 读进来比。这样 RTL 和
Python oracle 对 Table 7 的理解**从构造上就一致**,不会出现两边各自实现、上板才发现
对不上的情况。

已实现:`tb/tb_tx_top.sv`,4 帧 / 48 项检查。跑两组不同数据各比对一次,再加反压、
以及帧发送中改寄存器 + 敲 doorbell 的屏蔽用例。用例清单和跑法见
[`../module_specification.md` 第 6 节](../module_specification.md)。

**其中一条是设计出来的,不是写完顺手加的:**集成 testbench 里有两条用层次化引用的断言
(`dut.cmd_valid |-> dut.frame_builder_busy`)。因为**纯黑盒激励物理上够不到那个窗口** ——
`busy` 若做成寄存器输出只开 1 拍的洞,而一次 AXI-Lite 写最少 3~4 拍,PS 根本发不出间隔
1 拍的两个 doorbell。反测证实过:没有这条断言时,把 `busy` 改成寄存器输出,集成测试**照样
全绿**。这条性质属于**接线本身**而不属于任何单个模块,所以由拥有接线的这一层来守。

### 仿真测不到的部分

**TEMAC 是否真的补了 pad 和 FCS,testbench 验证不了。**那是上板后用 Wireshark 抓包才能
确认的,也正是主 README 里 FS11 写的验证方法。这件事留给板级 bring-up,不要指望仿真
兜住。

---

## 任务分配

| # | 任务 | 依赖 | Owner |
|---|---|---|---|
| 1 | `axi_lite_regbank` 实现 + 单元测试 | 无 | lucy |
| 2 | `tx_order_latcher` 实现 + 单元测试 | 无 | hanyu |
| 3 | `tx_frame_builder` 实现 + 单元测试 | 无 | panzy |
| 4 | Python golden frame 生成脚本 | 无 | ashley |
| 5 | 集成测试 testbench | 1、2、3、4 | lucy |

**1–5 全部完成。**三个模块 lint clean(`--Wall`)、四个 testbench 全过、`tx_top` 四个
模块联合 elaborate 干净。当前进度和跑法见 [`../module_specification.md`](../module_specification.md)。

**注意:仿真通过 ≠ 综合会过 ≠ 能上板。**综合、时序收敛、TEMAC IP 配置、bring-up 都还没
开始,是三道独立的门槛。

集成之前踩过、已经修掉的坑,记在这里免得再来一次:

- **常量头两边各写各的**,每个字段都不同(见「决定:链路常量以 golden 脚本为准」)。
- **端口名分叉**:`tx_frame_builder` 一度把订单号叫 `cmd_id`,而契约、`tx_order_latcher`、
  `tx_top` 都是 `cmd_order_id`——`tx_top` 直接 elaborate 失败。**接口契约里的名字是名字,
  不是示意**。
- **黄金帧文件名/用例数据分叉**:tb 读 `golden_frame_<i>.hex`,脚本当时只吐一个拼接的
  `golden_frames.hex`;两边的测试数据也不是同一批。现在脚本两种都吐,契约写在
  「黄金帧文件契约」一节。
- **`context` 是 SystemVerilog 保留字**,`tb_tx_order_latcher.sv` 拿它当参数名,Verilator
  连报十几行 syntax error。已改成 `ctx`。
- **testbench 只累加 fail 计数、不 `$fatal`**,退出码永远是 0——122 个失败照样"正常结束"。
  已改成失败时非零退出。testbench 报告失败却不让调用方知道,等于没测。

`axi_lite_regbank` 是 RX 和 TX 都要用的模块,建议**优先做、且只由一个人写**——两边都
依赖它的输出信号,两个人同时改一个文件容易冲突。
