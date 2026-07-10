# 1. Introduction  1. 引言

## 1.1 Motivation  1.1 动机

Algorithmic trading systems are strongly constrained by end-to-end event latency: market data must be decoded, converted into a usable order book state, evaluated by a strategy, checked for risk, and converted into an order message before the opportunity disappears. A software-only implementation running on a general-purpose Linux host incurs kernel network stack and scheduler overhead before any strategy logic executes; published FPGA-based trading systems quantify this cost directly — a hardware datapath has been shown to achieve roughly a 4x latency reduction over a conventional software-based pipeline [1], and specialized hardware implementations report sub-microsecond response, with one 10 Gigabit Ethernet FPGA trading system achieving approximately 433 nanoseconds from market packet analysis to order trigger [2]. The current AQTA design therefore treats latency elimination as the central design problem rather than as a late-stage optimization.  
算法交易系统受到端到端事件延迟的严格限制：市场数据必须先被解码，转换为可用的订单簿状态，经过策略评估，检查风险因素，然后再转化为订单消息——否则机会就会错过。在通用 Linux 主机上运行的纯软件实现在策略逻辑执行之前，就需要处理内核网络堆栈和调度器的开销；而基于 FPGA 的交易系统则可以直接量化这一成本——研究表明，硬件数据路径能够将延迟减少约 4 倍[1]。专门的硬件实现则能够实现亚微秒级的响应时间，有报道指出，某个 10 千兆比特以太网 FPGA 交易系统从市场数据包分析到订单下达的响应时间约为 433 纳秒[2]。目前的 AQTA 设计将消除延迟作为核心设计目标，而不是作为后期优化的一部分。

AQTA addresses this by adopting a hardware-software co-designed architecture: the time-critical, deterministic portions of the pipeline — packet decoding and order-book maintenance — are implemented directly in programmable logic, while strategy evaluation, logging, and overnight reconfiguration remain in software for flexibility. This division follows the same rationale used throughout the FPGA trading literature cited above: push fixed, latency-critical operations into hardware, and keep the parts that need to change often in software.  
AQTA 通过采用一种硬件与软件协同设计的架构来解决这个问题：那些时间敏感且需要确定性结果的任务——比如数据包解码和订单簿维护等——直接通过可编程逻辑实现，而策略评估、日志记录以及临时配置等任务则仍然保留在软件中，以实现灵活性。这种分工方式遵循了上述 FPGA 交易领域文献中常用的原则：将那些需要固定执行且对延迟有严格要求的操作交给硬件处理，而将那些需要频繁修改的部分保留在软件中。

## 1.2 Project Objective  1.2 项目目标

The objective of this project is to design a hardware-software co-designed trading accelerator that processes simulated market data, maintains a real-time order book, selects and applies a validated trading decision, and emits a corresponding order within a bounded latency budget, while supporting operator-approved overnight strategy reconfiguration.  
该项目的目标是设计一种软硬件协同设计的交易加速器。该加速器能够处理模拟的市场数据，实时维护订单簿，选择并执行经过验证的交易决策，并在有限的延迟预算内发出相应的订单。同时，该系统还支持由操作员批准的夜间策略重新配置功能。

The essential prototype performs market-data ingestion, protocol decoding, and order-book maintenance in programmable logic (PL) to keep the time-critical path deterministic; passes the resulting order-book state to a configurable strategy running on the ARM processing system (PS), which selects among several pre-loaded strategies and applies a RiskGuard filter; and returns the validated decision to the PL, where it is encoded and transmitted back onto the exchange link.  
这个核心原型模块负责市场数据获取、协议解码以及订单簿的维护工作，所有这些操作都通过可编程逻辑电路来实现，以确保关键任务过程的确定性。之后，该模块会将得到的订单簿状态传递给一个可配置的策略引擎，该引擎会在 ARM 处理系统上运行，并从多个预加载的策略中选择一种来进行处理，同时应用风险防护机制。最后，该模块会将经过验证的决策返回到可编程逻辑电路中，然后对其进行编码处理，再将其传输回交易系统。

The secondary objective is an End-of-Day (EOD) optimization pipeline that classifies the next trading day's market regime from historical data, searches a bounded parameter space to select a strategy configuration for that regime, and backtests the selected configuration before presenting it to a human operator for approval; only an approved configuration is loaded into the live system for the next trading session.  
次要目标是实现一个每日结束时的优化流程。该流程会根据历史数据来预测下一个交易日的市场状况，然后在有限参数的空间中选择适合该状况的策略配置，并对所选配置进行回测。只有在获得人工审核后批准的配置才会被加载到实时系统中，用于下一个交易时段的使用。

The prototype scope is intentionally bounded to one simulated exchange and one equity symbol, which keeps the project focused on the engineering problem of deterministic hardware/software partitioning while avoiding real-money financial risk and the complexity of multi-venue market-data normalization. Rather than implementing an industry-standard compressed protocol such as FAST, the prototype defines a fixed-width binary custom protocol for market data and order messages; this narrows the scope of the PL-side protocol decoder to a fixed, minimal field set and keeps decoding latency low, at the cost of interoperability with real exchange feeds. The prototype is restricted to paper trading and simulation: it does not place live orders and does not connect autonomous strategy decisions directly to a real-money account.  
该原型系统的范围被明确限制在了一个模拟交易系统和一种股权报价符号上。这样设计是为了让项目专注于确定性硬件/软件分区的工程问题，同时避免真正的货币交易风险以及多地点市场数据标准化的复杂性。与行业标准压缩协议如 FAST 不同，该原型定义了一个固定宽度的二进制自定义协议用于市场数据和订单消息的传输。这样一来，PL 端协议解码器的功能就被限制在一个固定的、最小化的字段集上，从而降低了解码延迟，但牺牲了与真实交易系统的互操作性。该原型仅适用于模拟交易环境，不会进行实盘交易，也不会将自主策略决策直接连接到真实货币账户上。

## 2. System Specifications  
2. 系统规格说明

### 2.1 Functional Specifications  
2.1 功能规格

|ID|Specification  规格说明|Essential  必备的/重要的|
|---|---|---|
|**FS1**|Upon receipt of a market data packet at the PL Gigabit Ethernet interface, the system must decode the packet and make an updated top-of-book snapshot **readable by the PS** within ≤ 1.1 μs of packet arrival. **Verifiable by:** ILA/logic analyzer measurement from MAC RX valid to **the PL snapshot-register write (`seq` increment)**, using a reference packet sequence.  <br>在 PL 千兆以太网接口接收到市场数据包后，系统必须解码该数据包，并在数据包到达后≤1.1 微秒内生成一份更新后的图书顶部信息快照，该快照必须由 PS 能够读取。验证方式：通过 MAC 接收有效信号对 PL 快照寄存器进行写入操作（ `seq` 递增），并使用参考数据包序列进行验证。|**Y**|
|**FS2**|Upon a top-of-book update becoming visible to the PS, the system must produce a trading decision (BUY / SELL / HOLD) using one of three pre-loaded strategies, and transmit a corresponding order packet via the PL Gigabit Ethernet interface within ≤ 26 μs of the update becoming visible, evaluated at the 99th percentile. The selected design (busy-poll on an isolated core, 3.2 Decision 3) eliminates OS scheduling jitter on the hot path; NFS1's 300 μs worst-case ceiling applies only to the superseded interrupt-based design. **Verifiable by:** measuring elapsed time from PS observation of a new `seq` (PMU cycle counter) to MAC TX packet capture (Wireshark) across 1000 consecutive observed updates on the designated reference setup, verifying that the 99th percentile does not exceed 26 μs, and verifying order field encoding matches the protocol specification.  <br>当书籍内容的更新被 PS 系统看到后，系统必须使用三种预加载的策略之一来做出交易决策（买入/卖出/持有），并在更新被看到后≤26 微秒内通过 PL 千兆以太网接口发送相应的订单数据包。所选方案（在隔离的核心上采用忙轮询机制，决策树为 3.2 层）能够消除热路径上的操作系统调度抖动问题；NFS1 的 300 微秒最坏情况上限仅适用于被替换的基于中断的设计。验证结果如下：从 PS 系统观察到新的 `seq` （PMU 周期计数器）到通过 Wireshark 捕获 MAC 传输数据包的总时间不超过 1000 微秒，且 99%分位时间的确不超过 26 微秒。同时，订单字段的编码与协议规范一致。|**Y**|
|**FS3**|The system must reject any order violating at least one of the following limits, each configurable via FS4, with the values below acting as hard ceilings that a loaded configuration may tighten but never exceed: (a) notional value > $50,000 CAD; (b) position size > 1,000 shares; (c) order submission rate > 1,000 orders/second; (d) in-flight (submitted but not yet terminal) orders > 100. **Verifiable by:** submitting one test order violating each of the four constraints individually and confirming a REJECT response with a logged reason code.  <br>该系统必须拒绝任何违反以下限制的订单，这些限制可以通过 FS4 进行配置，且数值以下为硬性上限，即使配置参数有所调整，也不应超过这些数值：(a) 理论价值超过 50,000 加元；(b) 持仓数量超过 1,000 股；(c) 订单提交频率超过每秒 1,000 个订单；(d) 正在提交但尚未完成的订单数量超过 100 个。验证方法为：分别提交违反上述每项限制的测试订单，并确认收到“拒绝”响应，同时记录相应的错误原因代码。|**Y**|
|**FS4**|At system startup, the system must load an externally-supplied strategy configuration — specifying the active strategy and its parameters — before processing any market data. **Verifiable by:** modifying the configuration source, restarting the system, and confirming via system log that the correct strategy and parameters are active.  <br>在系统启动时，系统必须加载由外部提供的策略配置——即指定当前生效的策略及其参数。这一验证可以通过修改配置源、重新启动系统，以及通过系统日志确认正确的策略和参数已生效来完成。|**Y**|
|**FS5**|The system must continuously persist trading activity (strategy decisions, execution outcomes, order book snapshots) within a bounded memory budget, without triggering an out-of-memory condition during sustained high-frequency operation, and must be able to export this history for offline use. **Verifiable by:** stress-testing with > 10 million injected ticks and confirming static memory usage with no OOM exceptions; confirming a full session's history is successfully exported and contains one entry per decision.  <br>该系统必须在有限的内存预算内持续进行交易活动（包括策略决策、执行结果、订单快照等），并且在高频操作期间不会触发内存不足的情况。同时，该系统还需要能够将这些历史数据导出以供离线使用。验证方式：通过注入超过 1000 万笔交易数据来进行压力测试，确认内存使用量不会超过限制；同时确认整个会话的历史数据能够成功导出，并且每个决策都有对应的记录。|**Y**|
|**FS6**|Given a history of daily market data, the system must classify the next trading day's market regime into one of at least three distinguishable states. **Verifiable by:** running the classifier on 6 months of historical OHLCV data for a single equity and confirming at least 3 distinct regimes are assigned across the period.  <br>给定每日市场数据的历史记录，该系统需要将下一个交易日的市场状态划分为至少三种不同的状态。验证方法为：对某只股票过去 6 个月的开盘价、最高价、最低价和收盘价数据运行分类器，并确认在整段时间内至少出现了 3 种不同的市场状态。|**Y**|
|**FS7**|Given a classified regime, the system must search a parameter space of at least 9 combinations for the corresponding strategy and select the combination that maximizes a defined performance metric (e.g., Sharpe ratio) over a recent trailing window. **Verifiable by:** running the optimizer twice on the same designated reference host with identical input data and confirming deterministic (bit-identical) output.  <br>在面临机密性的约束条件下，该系统必须在至少包含 9 种组合的参数空间中搜索合适的策略，并选择能在近期观察窗口内最大化特定性能指标（如夏普比率）的组合。验证方式是通过在同一台指定主机上两次运行优化算法，使用相同的输入数据，然后确认输出结果具有确定性（bit 级一致）。|**Y**|
|**FS8**|A newly generated strategy configuration must not be loaded into the live trading system until it has been explicitly approved by a human operator. **Verifiable by:** confirming that the configuration is not transmitted to the SoC until a manual approval action is taken.  <br>新生成的策略配置在得到人工操作员的明确批准之前，不得被导入到实时交易系统中。确认该配置在获得手动批准之前不会传输到系统控制中心。|**Y**|
|**FS9**|The system should ingest unstructured text data (≥ 10 text assets/day, comprising financial news, social media streams, and optional financial/research reports) via HTTPS from designated web sources, and extract a structured event record (headline, entity/ticker mentioned, timestamp, source) from each asset for downstream sentiment scoring. **Verifiable by:** mocking a web server with standard news feeds and PDF financial reports, and verifying successful ingestion and correct structured-event extraction for each asset.  <br>该系统应通过 HTTPS 从指定的网络来源获取非结构化文本数据（每天至少 10 条文本数据，包括金融新闻、社交媒体帖子以及可选的金融/研究报告）。系统会从每条数据中提取结构化的事件记录（标题、提到的实体/股票代码、时间戳、来源），以便进行后续的情感评分工作。验证方式包括使用标准的新闻源和 PDF 金融报告来测试网络服务器的功能，同时确认每条数据的正确结构化事件提取结果。|**N**|
|**FS10**|The system must compute a normalized sentiment score in [−1, +1] from each structured event record, and use this scored payload to adjust next-day position limits, where adjustment may only reduce limits below their configured baseline: negative sentiment tightens; neutral or positive sentiment leaves limits unchanged. **Verifiable by:** running the stage on a reference set of pre-labeled event records and confirming computed scores fall within [−1, +1] with correct polarity, confirming position-limit reduction occurs for negative-polarity records, and confirming no adjustment occurs for neutral or positive records.  <br>该系统需要为每个结构化事件记录计算出一个归一化的情感评分，该评分范围在[−1, +1]之间。然后，利用这个评分来调整当天的仓位限制。通常情况下，评分会使得仓位限制低于设定的基准值：负面情感会使得仓位限制进一步降低：中性或正面的情感则不会对仓位限制产生影响。验证方法如下：在预标记好的事件记录集上运行该系统，确认计算出的评分符合[−1, +1]的范围，且情感极性正确；同时确认对于负面情感的记录，确实发生了仓位限制降低，而对于中性或正面情感的记录则没有发生任何调整。|**N**|
|**FS11**|During the trading session, the system should output a real-time report of current order book state and recent trading decisions via Debug UART; the server host software must print this to the console and save it to a local log file. **Verifiable by:** confirming output is received, displayed, and written to disk at the server console during an active simulated session.  <br>在交易过程中，系统应通过调试 UART 输出一份实时报告，内容包括当前订单状况以及最近的交易决策。服务器主机软件必须将这些信息打印到控制台，并保存到本地日志文件中。验证方式是在模拟会话期间，确认这些输出已成功接收、显示，并且已保存到服务器控制台的磁盘上。|**N**|
|**FS12**|During EOD pipeline execution, the system must display and log the current pipeline stage, the classified regime, the selected strategy and swept parameters, the backtest Sharpe ratio, and the operator approval status, updated as each stage completes. **Verifiable by:** running a full EOD pipeline cycle and confirming the console output and saved log contain one entry per pipeline stage transition, including the final approval status.  <br>在每日结束时的管道执行过程中，系统必须显示并记录当前的管道阶段、分类制度、所选策略及相关参数，回测后的夏普比率，以及操作员的审批状态。这些信息会随着每个阶段的完成而更新。验证方式是通过运行完整的每日管道执行流程，并确认控制台输出和保存的日志中包含了每个管道阶段的相关信息，包括最终的审批状态。|**N**|
|**FS13**|The order packet transmitted via the PL Gigabit Ethernet interface must conform to a fixed-length binary format specifying, at minimum: order ID, symbol identifier, side (BUY/SELL), quantity, price, and a checksum field. This format must be documented as a standalone protocol specification referenced by FS2's verification procedure. **Verifiable by:** parsing a captured order packet against the documented field layout and confirming byte-offset and length correctness for each field.  <br>通过 PL 千兆以太网接口传输的订单数据包必须遵循一种固定的二进制格式。该格式至少应包含以下信息：订单编号、交易品种标识符、交易方向（买入/卖出）、订单数量、价格以及校验和字段。这种格式必须作为独立的协议规范被记录下来，以便 FS2 的验证程序能够对其进行验证。验证方式是通过将捕获到的订单数据包与文档中的字段布局进行比对，同时确认每个字段的字节偏移量和长度是否正确。|**Y**|
|**FS14**|The system must track the state of every in-flight (submitted but not yet terminal) order for the traded symbol, supporting up to 100 concurrent in-flight orders (configurable via FS4, with 100 as the default and hard ceiling per FS3(d)), without data corruption or dropped state. **Verifiable by:** injecting simulated order flow that drives the in-flight count to the configured limit and confirming, via post-run log inspection, that per-order state remains correct and no orders are lost or duplicated.  <br>该系统必须能够跟踪与交易符号相关的所有处于处理中的订单的状态。最多可以同时处理 100 个处于处理中的订单（可通过 FS4 进行配置，默认值为 100，这是 FS3 中的最大限制）。系统必须确保数据不会损坏，所有订单的状态也不会丢失或重复。验证方式可以是注入模拟订单流，以触发设定的处理数量上限，然后通过检查运行后的日志来确保每个订单的状态都是正确的，没有任何订单丢失或重复处理。|**Y**|

### 2.2 Non-Functional Specifications  
2.2 非功能规格要求

|ID|Specification  规格说明|Essential  必备的/重要的|
|---|---|---|
|**NFS1**|Total system latency from market data packet arrival (PL MAC RX) to corresponding order packet transmission (PL MAC TX) must not exceed 50 μs typical, with a hard ceiling of 300 μs under the superseded interrupt-based design (the selected busy-poll design eliminates OS scheduling jitter on the hot path, making the 300 μs ceiling a historical bound, not an active requirement). **Verifiable by:** logic analyzer measurement of MAC RX to MAC TX interval on a reference loopback test packet.  <br>从市场数据包到达时开始，到相应订单包传输完毕之间的系统总延迟时间，通常不得超过 50 微秒。在旧的基于中断的设计方案中，这一数值有一个上限，即 300 微秒（采用新的忙轮转调度方案后，这一上限成为了历史性的限制，而非实际需要满足的要求）。这一结果可以通过逻辑分析仪对参考回环测试数据包中从 MAC 接收到 MAC 传输间隔的监测来验证。|**Y**|
|**NFS2**|The Ethernet link between the PL and the exchange simulator must sustain a 10-minute continuous test window with zero unexplained frame drops. **Verifiable by:** Wireshark capture over a 10-minute test window, confirming frame delivery matches expected count.  <br>PL 与交换模拟器之间的以太网连接必须能够在 10 分钟的连续测试时间内保持连接，且不会出现任何帧丢失的情况。验证方式是通过 Wireshark 进行 10 分钟内的捕获分析，确保帧的传输数量符合预期。|**Y**|
|**NFS3**|Physical hardware components (excluding the Zynq-7000 SoC development board, host PC, and monitors) must not exceed $1,000 CAD in total cost. **Verifiable by:** summing itemized purchase receipts for all acquired components.  <br>物理硬件组件（不包括 Zynq-7000 系统级芯片开发板、主机电脑和显示器）的总成本不得超过 1,000 美元。可通过汇总所有购买组件的明细发票来验证这一金额。|**Y**|
|**NFS4**|The system must operate continuously through a full simulated trading session (6.5 hours, 09:30–16:00 ET) without a crash, hang, or unrecovered error requiring manual restart. **Verifiable by:** running the exchange simulator for a full session duration and inspecting system logs for fatal errors.  <br>该系统必须在完整的模拟交易过程中持续运行，时间长达 6.5 小时，从东部时间 09:30 到 16:00。系统必须能够稳定运行，不会出现崩溃、挂掉或无法恢复的错误，也不需要手动重启。验证方式是通过运行整个模拟会话来测试系统，并检查系统日志中是否有致命错误记录。|**Y**|
|**NFS5**|The full EOD pipeline (data ingestion → regime classification → parameter optimization → human approval prompt) must complete within 30 minutes of receiving end-of-day data. **Verifiable by:** timing the pipeline on a reference dataset of 1 year of daily OHLCV data for a single equity.  <br>完整的 EOD 流程（数据导入→市场状况分类→参数优化→人工审批提示）必须在收到当日结束数据后 30 分钟内完成。验证方式：使用包含 1 年每日 OHLCV 数据的参考数据集来测试该流程的运行时间。|**N**|
|**NFS6**|The FPGA PL implementation must utilize fewer than 75% of available LUTs on the XC7Z020 device, and fewer than 85% of available Block RAMs, to ensure timing closure at 125 MHz. **Verifiable by:** Vivado post-implementation utilization and timing summary reports showing WNS > 0 ns at 125 MHz.  <br>FPGA PL 实现过程中，所使用的逻辑单元数量应少于 XC7Z020 芯片上可用逻辑单元数的 75%，同时使用的块 RAM 数量也应少于可用块 RAM 数量的 85%。这样可以确保在 125 MHz 的频率下实现时序的准确匹配。验证结果可通过 Vivado 实施后使用的报告得到确认，该报告显示在 125 MHz 的频率下，WNS 值大于 0 纳秒。|**Y**|
|**NFS8**|Upon detecting a recoverable fault — including but not limited to: a market data packet failing checksum validation, a receive FIFO overflow condition, or a strategy configuration failing validation at load time — the system must discard/reject the offending input, log a timestamped error record with a fault code, and continue normal operation without requiring a manual restart. **Verifiable by:** individually injecting each fault type (corrupted checksum packet, sustained burst exceeding FIFO depth, malformed config file) and confirming the system logs the corresponding fault code, discards the bad input, and resumes processing subsequent valid inputs within **≤ 96 ns (the Ethernet inter-packet gap)** for PL hardware faults, or immediately upon the next polling cycle for PS faults.  <br>当检测到可修复的故障时——包括但不限于：市场数据包校验和验证失败、接收 FIFO 缓冲区溢出，或策略配置在加载时验证失败等情况——系统必须丢弃或拒绝该错误输入，并记录一个带有错误代码的错误日志。然后系统可以继续正常运行，无需手动重启。验证方法为：分别模拟每种错误类型（如校验和错误的数据包、持续的数据包超过 FIFO 容量限制、配置文件损坏），确认系统记录了相应的错误代码，并丢弃了错误的输入。对于 PL 硬件故障，系统会在≤96 纳秒内恢复处理后续有效的输入；对于 PS 故障，系统会在下一次轮询周期立即恢复处理。|**Y**|
|**NFS9**|**Market Data Ingest Throughput** The FPGA PL data pipeline must sustain a peak market data ingestion and processing rate of ≥ 1.2 million messages per second (msg/s), matching or exceeding the theoretical maximum packet rate of the Gigabit Ethernet link (full wire-speed). The system must process micro-bursts at line rate without dropping packets or stalling the MAC RX buffer. **Verifiable by:** injecting a synthesized PCAP file containing FAST UDP packets at full 1 Gbps line rate using a packet generator, and confirming zero dropped packets via MAC/FPGA drop counters. _(Lit basis: FPGA book builders at 1.2–1.5M msg/s [3]; hardware feed processing reported at multi-M msg/s on faster links where line-rate is no longer the limiter [4].)_  <br>通过 FPGA PL 数据管道进行市场数据摄取的吞吐量要求必须达到每秒至少 120 万条消息的峰值处理速率，从而超过千兆以太网链接的理论最大数据包传输速率。系统必须能够连续处理这些微量的数据流量，同时避免数据包丢失或 MAC 接收缓冲区出现停滞现象。验证方法为：使用数据包生成器以 1 Gbps 的线路速率注入包含 FAST UDP 数据包的合成 PCAP 文件，并通过 MAC/FPGA 丢包计数器确认没有数据包丢失。（参考依据：FPGA 相关文献中报道的每秒 120 万到 150 万条消息的处理能力[3]；实际硬件处理经验表明，在更快的链接上，线路速率不再是限制因素，处理速率可达到多百万条消息每秒[4]。）|**Y**|

# 3.1 PL (FPGA) Market Data Path Subsystem  
3.1 PL（FPGA）市场数据路径子系统

> **Template conventions:** `[TEAM: …]` = requires a team decision or board-level confirmation. `OPEN: …` = a claim that is currently an analytical design target and must be replaced or confirmed by simulation/synthesis/measurement before the final report. `[REF-n]` = citation placeholder; map to the bibliography. All numeric analysis in 3.1.4 is derivable on paper today (line-rate arithmetic, cycle budgets, datasheet resource math) — no code required.  
> 模板约定： `[TEAM: …]` 需要团队决策或董事会级别的确认。 `OPEN: …` 是一个分析性设计目标，需要在最终报告之前通过仿真、合成或测量来确认或替换。 `[REF-n]` 是引用占位符，用于引用参考文献。在 3.1.4 中所有的数值分析都可以用纸上的方法进行计算（如速率计算、周期预算、数据表资源计算等）——无需编写代码即可实现。

---

## 3.1.1 Overview and Specification Mapping  
3.1.1 概述与规格说明的映射

The PL subsystem implements the entire wire-to-snapshot market data path and the order egress path in programmable logic on the XC7Z020. On the receive side, it terminates the point-to-point Gigabit Ethernet link from the exchange simulator, validates and parses each custom UDP market data packet at fixed byte offsets, maintains a 10-level bid / 10-level ask limit order book (an L3-to-L1/L2 aggregation), and publishes the resulting top-of-book snapshot to the PS through an AXI-Lite register bank on M_AXI_GP0 (snapshot fields plus an incrementing `seq` register, committed atomically in one clock edge). On the transmit side, it receives risk-validated order fields written by the PS into the same register bank, begins encoding on the doorbell-register write strobe, encodes them into the fixed-length binary order format defined by FS13, and transmits them through the same PL GbE interface.  
PL 子系统在 XC7Z020 上实现了整个从线路到快照数据的传输路径以及订单输出路径的可编程逻辑处理。在接收端，它负责处理来自交换模拟器的点对点千兆以太网链接，验证并解析每个自定义的 UDP 数据 packets，这些数据包的字段位置遵循固定的字节偏移量。此外，该系统还维护了一个包含 10 级买入价和 10 级卖出价的限价单簿，该簿通过 L3 到 L1/L2 的级联方式实现。最后，系统会将生成的快照数据通过 M_AXI_GP0 上的 AXI-Lite 寄存器组发布到 PS 端，其中快照数据的字段会与一个递增的 `seq` 寄存器一起被发送，并且这些数据的提交会在一个时钟周期内完成。在发送端，系统会接收由 PS 端写入的、经过风险验证的订单字段，然后在门铃寄存器写入脉冲时开始对这些字段进行编码，将其转换为由 FS13 定义的固定长度的二进制订单格式，最后通过相同的 PL GbE 接口将这些数据发送出去。

The subsystem exists because the software network path cannot meet the project's latency specifications: a conventional Linux socket path incurs interrupt handling, kernel protocol stack traversal, and kernel-to-user copies that together cost tens to hundreds of microseconds per packet, which is incompatible with the ≤ 1.1 μs decode budget of FS1. Placing the parse and book-build stages in the PL removes the operating system from the market-data critical path entirely.  
该子系统存在的原因是，软件网络路径无法满足项目的延迟要求。传统的 Linux 套接字路径需要处理中断处理、内核协议栈传输以及内核到用户的数据复制等操作，这些操作每包数据需要花费数十到数百微秒的时间，这远远超出了 FS1 要求的≤1.1 微秒的解码时间限制。将解析和构建阶段移入 PL 阶段后，操作系统就完全不会参与到市场数据处理的关键路径中了。

This subsystem is directly responsible for the following specifications:  
这个子系统直接负责以下规范的实施：

|Spec  规格/参数|Role of PL subsystem  <br>PL 子系统的作用|
|---|---|
|**FS1**|Sole owner: packet arrival → decoded top-of-book snapshot available to PS in ≤ 1.1 μs.  <br>唯一所有者：数据包到达后，书顶端的快照在 1.1 微秒以内即可供 PS 使用。|
|**FS13**|Sole owner of the egress half: order packets must conform to the fixed-length binary format.  <br>出口部分的唯一所有者：传输的数据包必须遵循固定的二进制格式。|
|**NFS1**|Owns the two PL segments (RX decode, TX encode) of the ≤ 50 μs end-to-end budget (300 μs ceiling applies to the superseded interrupt design).  <br>拥有两个 PL 模块的职责，分别是 RX 解码和 TX 编码。这些模块的总执行时间不超过 50 微秒；对于被取代的中断设计来说，最高执行时间则限制在 300 微秒以内。|
|**NFS2**|Owns link integrity: zero unexplained frame drops over a 10-minute window.  <br>拥有良好的链接稳定性：在 10 分钟的时间段内，没有出现任何未解释的帧丢失情况。|
|**NFS6**|Owns the resource envelope: < 75% LUT, < 85% BRAM at 125 MHz with WNS > 0.  <br>拥有以下资源：LUT 低于 75%，BRAM 在 125 MHz 频率下低于 85%，且 WNS 大于 0。|
|**NFS9**|Owns ingest throughput: ≥ 1.2 M msg/s sustained at line rate without MAC RX stall.  <br>自身处理的吞吐量：在线路速率下，能够持续处理≥120 万条消息/秒，且不会出现 MAC 接收阻塞的情况。|
|**NFS8 (partial)  NFS8（部分内容）**|Owns the hardware fault path: checksum-fail discard and FIFO-overflow handling with fault counters.  <br>拥有处理硬件错误路径的权限：包括校验和失败时的处理机制，以及带有错误计数器的 FIFO 溢出处理功能。|

Figure 3.1 shows the PL block structure and the shared AXI-Lite register bank at the PS boundary. _(Figure placeholder — reuse the PL subgraph of the system block diagram; stage names below must match the block labels`[TEAM: unify naming — the latest diagram uses "Market Data Packet Parser / Market Feature Builder / Order Emitter"; this section currently uses "Protocol Decode / Build Order Book / Protocol Encode". Pick one vocabulary for both.]`.)_  
图 3.1 展示了 PL 模块的结构，以及 PS 边界处共享的 AXI-Lite 寄存器组。（图例占位符——复用系统框图中的 PL 子图；下面的阶段名称必须与模块标签 `[TEAM: unify naming — the latest diagram uses "Market Data Packet Parser / Market Feature Builder / Order Emitter"; this section currently uses "Protocol Decode / Build Order Book / Protocol Encode". Pick one vocabulary for both.]` 相匹配。）

---

## 3.1.2 Engineering Design Process  
3.1.2 工程设计流程

Four significant design decisions shaped this subsystem. Each is presented with the alternatives considered and the rationale for the selection; where the rationale is quantitative, the supporting calculation appears in Section 3.1.4.  
这个子系统的设计受到了四个重要决策的影响。每个决策都详细说明了所考虑的替代方案以及选择该方案的原因；其中一些原因是基于定量分析的，相关的计算支持内容则出现在第 3.1.4 节中。

### Decision 1 — Network path placement: PS socket, PS-DMA-then-parse, or full PL path  
决策 1——网络路径选择：选择 PS 套接字、PS-DMA 方式处理，或者采用完整的 PL 路径。

|Alternative  替代方案|Description  描述|Outcome  结果|
|---|---|---|
|A. PS socket parsing  <br>A. 指针位解析|Receive UDP through the PS hardened GEM MAC and Linux sockets; parse in user space.  <br>通过经过 PS 加固处理的 GEM MAC 和 Linux 套接字接收 UDP 数据包；在用户空间进行解析。|**Rejected.** Kernel networking and scheduler jitter are incompatible with FS1 (≤ 1.1 μs) and consume most of the NFS1 worst-case budget before any useful work occurs.  <br>被拒绝。内核网络机制和调度器的抖动与 FS1 不兼容（抖动时间≤1.1 微秒），并且在产生任何有效结果之前，就已经消耗了 NFS1 最坏情况下的大部分资源。|
|B. PS GEM + post-DMA parse  <br>B. PS GEM + 任务完成后的解析|Let the PS GEM MAC receive frames, DMA raw frames to DDR3, then parse in PL or PS.  <br>让 PS GEM MAC 接收帧数据，将这些 DMA 原始帧数据传输到 DDR3 内存中，然后再在 PL 或 PS 层面进行解析处理。|**Rejected.** The Zynq GEM controller is a PS hard block: even with EMIO pin routing, every frame still traverses PS memory before the PL can observe it, adding one full DDR3 round trip and defeating the purpose of hardware parsing. EMIO relocates pins, not the MAC.  <br>被拒绝。Zynq GEM 控制器属于 PS 硬件块：即使采用 EMIO 引脚布局，每一帧数据在 PL 端可见之前，仍然需要经过 PS 内存处理。这相当于增加了一次完整的 DDR3 往返传输过程，从而破坏了硬件解析的初衷。EMIO 只是重新分配了引脚的位置，而 MAC 部分并没有进行任何调整。|
|C. Full PL path (selected)  <br>C. 完整的 PL 路径（可选）|Terminate the PHY on a PL I/O bank and implement MAC, parse, and book entirely in fabric.  <br>在 PL I/O 组中终止物理层模块，然后完全在芯片内部实现 MAC 层、解析模块以及存储功能。|**Selected.** The event is decoded before the PS ever observes it; latency is deterministic and clock-cycle countable.  <br>已选中。该事件在 PS 观察到之前就已经被解码了；延迟是确定的，且可以量化到时钟周期级别。|

Alternative C is only feasible because the selected carrier board exposes a dedicated **PL-side Gigabit Ethernet (RJ45)** in addition to the PS-side Ethernet — this was a primary board-selection criterion (the sibling board “启明星” exposes only the PS-side PHY and cannot implement Alternative C at all, while “领航者” includes 1× PS GbE + 1× PL GbE). The target board for this report is the 正点原子领航者 ZYNQ7020 开发板 (XC7Z020CLG400-2I); the board reference manual is the authoritative source for the PL Ethernet PHY wiring (REF-3). This decision also constrained the device choice: the PL path plus PS-interface infrastructure must fit NFS6's resource envelope, which motivated the XC7Z020 (53,200 LUTs) over the XC7Z010 (17,600 LUTs) — see Table 3.1.7.  
选择替代方案 C 是可行的，因为所选的电路板除了支持 PS 端的以太网接口外，还提供了专用的 PL 端千兆以太网接口（RJ45 接口）。这一标准是选择该电路板的主要依据。（与之相比，另一个候选电路板“启明星”仅支持 PS 端的光纤接口，无法实现替代方案 C 的功能。而“领航者”则具备 1 个 PS 千兆以太网接口和 1 个 PL 千兆以太网接口。）本报告所针对的电路板是正点原子领航者 ZYNQ7020 开发板（XC7Z020CLG400-2I）。关于 PL 端以太网接口的接线方式，可以参考该电路板的参考手册，该手册是确定 PL 端以太网接口接线的权威依据（参考 3.1.7）。这一决定也限制了设备的选择：PL 端接口以及 PS 端接口的基础设施必须符合 NFS6 的资源限制要求。因此，选择了 XC7Z020 开发板，其拥有 53,200 个逻辑单元，而 XC7Z010 开发板则只有 17,600 个逻辑单元——详见表 3.1.7。

### Decision 2 — MAC layer implementation: vendor IP, open-source stack, or minimal custom MAC  
决策 2——MAC 层实现：采用厂商提供的 IP 地址，还是使用开源解决方案，或者选择最少的定制 MAC 地址配置？

|Criterion (weight)  标准（权重）|Xilinx TEMAC IP  希利安克斯 TEMAC IP|Open-source full stack (e.g., verilog-ethernet)  <br>开源全栈技术（例如，Verilog 语法用于以太网通信）|Minimal custom MAC (selected)  <br>最小化的自定义 MAC 地址（已选择）|
|---|---|---|---|
|Latency determinism (35%)  <br>延迟决定论（35%）|Medium — general-purpose buffering  <br>中等——通用缓冲用途|Medium-high  中高|High — no unused feature logic in path  <br>高——路径中没有未使用的功能逻辑|
|Resource cost (25%)  资源成本（25%）|High (multi-thousand LUT + license terms)  <br>高难度级别（包含数千种 LUT 配置以及相关授权条款）|Medium  中等水平|Low — RX/TX framing + CRC only  <br>低级别——仅使用 RX/TX 框架结构以及 CRC 编码|
|Verification burden, given team capability (25%)  <br>验证负担，根据团队能力而言（25%）|Low (pre-verified)  低（待验证前状态）|Medium (must verify integration)  <br>中等水平（需要确认集成是否完成）|Medium — small surface, fully testable with directed + constrained-random testbenches  <br>中等难度——适用于小型表面，可以通过有指导性的以及受限制的随机测试方案进行全面测试。|
|Protocol generality (15%)  <br>协议通用性（15%）|High  高|High  高|Low — sufficient (see below)  <br>足够低——详见下文|
|**Weighted result (1–5 scale)  <br>加权评分结果（1-5 分制）**|3.55|3.65|**4.05 — Selected  4.05 — 已选中的项**|

The generality that vendor and open-source MACs provide — address learning, ARP resolution, multi-node arbitration — is dead weight in this system, because the physical link is a two-node point-to-point segment with one fixed peer. Both endpoints' MAC and IP addresses are compile-time constants, so ARP is replaced by hardcoded address matching, and the MAC reduces to preamble/SFD detection, frame delimiting, and FCS (CRC-32) checking on RX, plus framing and FCS generation on TX. Removing dynamic address resolution eliminates an entire class of state machines from the timing-critical path and from the verification plan. (Scoring: each criterion rated 1–5 per row — cost-type criteria score higher when the cost is lower — then weighted; TEMAC = 0.35×3 + 0.25×2 + 0.25×5 + 0.15×5 = 3.55, open-source = 0.35×4 + 0.25×3 + 0.25×3 + 0.15×5 = 3.65, custom = 0.35×5 + 0.25×5 + 0.25×3 + 0.15×2 = 4.05. The weights encode our priorities — latency > resources ≈ verifiability > generality — and the custom MAC wins on the two heaviest criteria while losing only on generality, which the point-to-point link makes worthless.)  
那些由供应商提供的通用功能以及开源 MAC 技术所提供的能力——比如地址学习、ARP 解析、多节点仲裁等——在这个系统中其实毫无用处。因为物理连接实际上只涉及两个节点之间的点对点连接，且每个节点的地址都是固定的。因此，ARP 功能被硬编码的地址匹配所取代，而 MAC 功能则简化为前导码检测、帧边界确定，以及接收端对帧进行 CRC-32 校验，而在发送端则进行帧封装和 CRC 校验。去除动态地址解析功能后，就不需要在时序关键路径上使用这类状态机了，同时也简化了验证流程。（评分标准：每个指标按照 1-5 分进行评分——成本型指标在成本越低时得分越高——然后进行加权计算；TEMAC = 0.35×3 + 0.25×2 + 0.25×5 + 0.15×5 = 3.55，开源版 = 0.35×4 + 0.25×3 + 0.25×3 + 0.15×5 = 3.65，定制版 = 0.35×5 + 0.25×5 + 0.）25×3 + 0.15×2 = 4.05。这些权重编码了我们的优先级——延迟优先，资源次之，可验证性次之，通用性最不重要。这个自定义的 MAC 在最重要的两个标准上表现优异，只是在通用性方面稍显不足，不过这一点在点对点连接中并不重要。

### Decision 3 — Parse architecture: store-and-forward vs. cut-through streaming parse  
决策 3——解析架构：存储转发与直通流解析

A store-and-forward design buffers the complete frame, verifies FCS, then parses. A cut-through design slices fields at their fixed byte offsets as bytes stream in from the MAC, so all fields are already latched when the final FCS byte arrives.

The quantitative case (full derivation in 3.1.4.2): at GMII rates the frame body alone occupies ~~560 ns of the 1,100 ns FS1 budget. Store-and-forward would serialize an additional walk over the buffered frame after reception — a second traversal the budget cannot afford — whereas cut-through leaves the entire post-frame budget (~~475 ns ≈ 59 cycles) for book update and snapshot commit. Cut-through is only safe because the packet format (Table 3.1.4) has fixed offsets: no length-dependent field positions exist, so slicing requires no lookahead. This is the same property that drove the format decision in Section 2: fixed-offset binary message layouts are an established market-data protocol class (NASDAQ ITCH-family feeds use fixed-length binary messages `[TEAM: confirm feed + cite the ITCH spec]`), and cut-through applies to that class; variable-length FAST-class encodings (presence maps, stop-bit fields) instead require stateful sequential decoding and framing/length handling that aggravates decoding complexity [1].

**Commit policy.** Cut-through creates one hazard: fields are latched before FCS validates the frame. The design therefore stages the parsed event in a holding register and commits it to the order book only on FCS pass; on FCS fail the event is discarded and a `parse_error` counter increments (NFS8 path). This costs one cycle of commit latency and zero throughput, versus the alternative of speculative book update with rollback, which was rejected because rollback of an aggregated price level requires storing pre-update state for every level touched — added area and a new failure mode for negligible latency gain.

### Decision 4 — Order book storage: BRAM-indexed structure vs. fixed register array

|Alternative|Description|Outcome|
|---|---|---|
|BRAM price-indexed table|Hash or direct-index price levels into Block RAM; scales to deep books and multiple symbols.|**Rejected for the prototype.** BRAM imposes synchronous 1-cycle read latency, making every book update a ≥ 2-cycle read-modify-write with pipeline hazard handling between back-to-back updates to the same level. Depth beyond 10 levels is not required by any specification for the single-equity scope.|
|Fixed register array (selected)|10 bid + 10 ask levels as flip-flop registers; combinational best-price selection.|**Selected.** Single-cycle read of any level, single-cycle update, no read-after-write hazards, and a trivially verifiable datapath. Resource cost is bounded and small (3.1.4.3).|

Updates addressing a price level outside the 10-level working window are discarded and counted (`dropped_out_of_window`) rather than triggering structural growth in the critical path; the diagnostic counter makes the discard observable during verification without altering trading behaviour. This register-vs-BRAM trade aligns with published FPGA order book designs noting BRAM's synchronous access latency and the resulting read-after-write hazard handling on back-to-back updates [5]. `[TEAM: confirm discard vs. compress vs. resync policy — currently specified as discard-and-count.]`

FS14 (rev.) fixes the single-symbol scope, closing this forward dependency: the register-array choice is final for the prototype.

---

## 3.1.3 Final Design Details

### 3.1.3.1 Receive pipeline

The RX path is a five-stage streaming pipeline at 125 MHz (Figure 3.2 — _placeholder: per-stage pipeline diagram with cycle annotations_):  
RX 路径是一个由五个阶段组成的流处理流水线，每阶段的时钟频率为 125 MHz（见图 3.2——占位符：每个阶段的流水线图及周期注释）：

1. **MAC RX.** RGMII DDR capture from the PHY, preamble/SFD alignment, destination-MAC match against the hardcoded constant, FCS accumulation. Non-matching frames are dropped at this stage without downstream activity.  
    MAC 接收帧。从 PHY 接口捕获 RGMII 数据，进行前导码/SFD 对齐处理，检查目标 MAC 是否与硬编码的常量匹配，然后进行 FCS 累积操作。如果匹配失败，这些帧会被丢弃，不会继续向下传输。
2. **IP/UDP header parse.** Fixed-offset validation of EtherType (0x0800), IP protocol (17), destination IP, and destination UDP port — all compile-time constants of the point-to-point link. IP header checksum is verified; the UDP checksum is not validated — the simulator emits UDP checksum = 0 (legal for IPv4 per RFC 768: zero means "no checksum") and the parser ignores the field, because payload integrity on this single-segment point-to-point link is already covered end-to-end by the Ethernet FCS (commit gate, stage 4).  
    IP/UDP 头部解析。对 EtherType（0x0800）、IP 协议号（17）、目标 IP 地址以及目标 UDP 端口进行了固定偏移量验证——这些都是点对点链接在编译阶段确定的常量。同时验证了 IP 头部的校验和；而 UDP 头部校验和并未进行验证——模拟器设定 UDP 校验和等于 0（根据 RFC 768 的规定，对于 IPv4 来说这是合法的：零表示“没有校验和”）。由于在这种单段点对点链接中，有效载荷的完整性已经由以太网 FCS 确保了，因此解析器可以忽略这个字段。
3. **Protocol decode.** Field slicing of the custom payload (Table 3.1.4) into a staged event register as bytes arrive.  
    协议解码。将自定义负载中的字段按字节分割，并将其作为事件记录的一部分进行处理（参见表 3.1.4）。
4. **Commit gate.** On FCS pass, the staged event commits; on fail, discard + `parse_error` increment (NFS8).  
    提交门。在 FCS 传递过程中，如果成功则进行事件提交；如果失败，则丢弃并增加 `parse_error` 的值（根据 NFS8 规范）。
5. **Order book update.** Aggregation of the committed L3 event (Add/Modify/Delete keyed by `order_id`) into the affected side/level; for Modify, `qty` is the new absolute remaining quantity (not a delta), and for Delete `qty` is ignored (encoder sets it to 0). Combinational extraction of the new top-of-book; single-cycle atomic commit of the snapshot registers and `seq` increment in the register bank.  
    订单簿更新。将已提交的 L3 事件数据（按 `order_id` 进行分组，包括添加、修改、删除等操作）汇总到相关侧边/级别；对于修改操作， `qty` 表示新的绝对剩余数量（不是增量）；对于删除操作， `qty` 被忽略（编码器将其设置为 0）。同时提取订单簿顶部的组合数据；对快照寄存器进行单周期原子提交操作，并让 `seq` 的值增加。

### 3.1.3.2 Packet formats (FS13 interface contract)  
3.1.3.2 数据包格式（FS13 接口协议）

Table 3.1.4 — Custom market data payload (RX). _(Identical to the Section 2 contract table; repeat or cross-reference per report style.)_  
表 3.1.4——自定义市场数据负载（接收端）。（与第 2 节中的合同表格相同；可根据报告风格进行重复显示或交叉引用。）

|Field  字段|Bit offset  位偏移量|Width (bits)  宽度（位）|Encoding  编码|
|---|---|---|---|
|msg_type  消息类型|0|8|0x01 Add, 0x02 Modify, 0x03 Delete, 0x04 reserved (execution report extension; not emitted in prototype)  <br>0x01 添加，0x02 修改，0x03 删除，0x04 保留（执行报告扩展；在原型中不会输出）|
|symbol  符号|8|16|Numeric symbol ID (single-equity prototype; constant 1)  <br>数字符号标识（单 Equity 原型；常数为 1）|
|price  价格|24|32|Unsigned integer cents; sources carrying finer precision are rounded half-to-even at the encoder and counted in `price_rounded` diagnostics  <br>未签名的整数位值；具有更高精度来源的数值在编码器处会被四舍五入到最接近的偶数，并会在 `price_rounded` 诊断信息中记录其数量。|
|qty  数量|56|32|Unsigned share quantity (validated against real ITCH-derived data); for msg_type 0x02 (Modify), `qty` is the order's new absolute remaining quantity (not a delta); for msg_type 0x03 (Delete), `qty` is ignored by the parser and set to 0 by the encoder  <br>未签署的分享数量（已通过与 ITCH 相关数据的比对进行验证）；对于 msg_type 为 0x02 的情况（修改）， `qty` 表示订单中新的绝对剩余数量（而非差值）；对于 msg_type 为 0x03 的情况（删除）， `qty` 被解析器忽略，由编码器设置为 0。|
|side|88|8|0x01 Bid, 0x02 Ask|
|order_id|96|32|Unique within simulator session (validated against real ITCH-derived data)|
|seq_num|128|32|Monotonic simulator-side sequence number (wrap allowed); supports attributable drop accounting (NFS2) and loop-boundaries in throughput tests|
|pad|160|32|Reserved = 0; fixes payload length to 24 B|

**Scope note (validated translation layer).** The protocol deliberately carries book-affecting events only. Trading-halt and hidden-execution events present in some source feeds are consumed by the simulator and not forwarded to the PL.

**Price alternative (documented).** A higher-precision price unit (10⁻⁴ dollars) was considered to avoid any rounding, but is rejected for the prototype because it would change constants and worked examples across 3.1/3.2/3.3 for a small fraction of events; integer cents with encoder-side rounding is selected.

Table 3.1.5 — Order packet payload (TX, FS13): order_id, symbol, side, qty, price, checksum, at fixed offsets. `[TEAM: freeze exact layout; this table is the standalone protocol spec FS13 requires and is referenced by FS2's verification procedure.]`

### 3.1.3.3 Order book register layout

|Register group  注册组|Entries  参赛作品|Fields per entry  每条条目的字段数量|Purpose  目的|
|---|---|---|---|
|Bid book  投标书/报价单|10|price_cents (32b), aggregate_qty (32b)  <br>价格分位（32 亿） 总数量（32 亿）|Highest active bid levels  <br>最高的活跃出价水平|
|Ask book|10|price_cents (32b), aggregate_qty (32b)  <br>价格分位（32 亿） 总数量（32 亿）|Lowest active ask levels  <br>最低的活跃报价水平|
|Top-of-book snapshot  书籍顶部快照|1|best_bid_price, best_bid_qty, best_ask_price, best_ask_qty  <br>最佳出价价格、最佳出价数量、最佳可接受价格、最佳可接受数量|Published to the PS-visible register bank (with `seq`) on each committed update  <br>在每次提交更新时，将结果写入 PS-visible 注册表组（使用 `seq` 作为标识符）。|
|Diagnostic counters  诊断计数器|4+|parse_error, fcs_fail, dropped_out_of_window, dma_backpressure  <br>解析错误，FCS 失败，窗口外丢失，DMA 背压|NFS2/NFS8 observability  NFS2/NFS8 的可观测性|

### 3.1.3.4 Clocking and PS interface  
3.1.3.4 时钟同步与 PS 接口

The PL runs a single 125 MHz clock domain: 125 MHz is simultaneously the GMII byte rate at 1 Gbps (one octet per cycle) and the NFS6 timing target, so the parse pipeline requires no clock-domain crossing between MAC and decode. On the selected board the PL reference clock is a 50 MHz active oscillator, so the 125 MHz PL fabric clock is generated by MMCM/PLL multiplication rather than sourced directly from the oscillator. The RGMII interface transfers 4 bits per edge at 125 MHz DDR; IDDR/ODDR primitives and the PHY-required clock skew are handled at the I/O ring `[TEAM: confirm RGMII delay scheme — PHY internal delay vs. IDELAY — from board schematic]`.  
PL 系统仅使用一个 125 MHz 的时钟域。这个频率同时作为 GMII 接口的传输速率（每周期传输一个八位组），也是 NFS6 协议的计时目标。因此，解析流水线在 MAC 层和解码层之间不需要跨越不同时钟域。在所选的板上，PL 系统的参考时钟是一个 50 MHz 的活跃振荡器，所以 125 MHz 的 PL 结构时钟是通过 MMCM/PLL 乘法算法生成的，而不是直接来自振荡器。RGMII 接口在 125 MHz 的 DDR 模式下每半个周期传输 4 位数据；而 IDDR/ODDR 原语以及 PHY 所需的时钟偏差则是由 I/O 环在 0 号节点处处理的。

The PS boundary is a single AXI-Lite slave register bank on M_AXI_GP0 (full map in Section 3.2.3.1); the PL is never a bus master, and the HP ports are unused. Snapshot publication is a one-clock-edge atomic commit of all snapshot registers plus the `seq` increment — hardware-side tearing is impossible by construction; the multi-read consistency problem exists only on the PS side and is solved there by seqlock (3.2.3.1). FS1's measurable endpoint is the `seq`-increment write enable, observable with an ILA. On the egress side, the order-field registers are sampled only on the doorbell write strobe (PS writes payload first, doorbell last), which starts the Protocol Encode stage on the following cycle; a `tx_ready` flag provides flow control (structurally uncontended — see 3.2.4.2).  
PS 边界是一个位于 M_AXI_GP0 上的单个 AXI-Lite 从寄存器组（完整映射请参见 3.2.3.1 节）；PL 从来不会担任总线主控角色，而 HP 端口则未被使用。快照发布是一个包含所有快照寄存器的原子操作，再加上 `seq` 的增量操作——从硬件层面来看，撕裂现象是不可能发生的；多读一致性问题仅存在于 PS 端，并通过 seqlock 在 PS 端得到解决（参见 3.2.3.1）。FS1 的可测量端点是 `seq` 的增量写使能位，可以通过 ILA 来观测该位。在出口端，订单字段寄存器仅在门铃写入时采样（PS 首先写入有效载荷，最后写入门铃信息），这标志着协议编码阶段的开始，该阶段会在下一个周期进行。 `tx_ready` 标志用于提供流量控制功能（从结构上看，这一功能并不必要——详见 3.2.4.2 节）。

Datasheet references for all interface and resource claims: Zynq-7000 TRM, XC7Z020 datasheet, PHY datasheet/board reference manual `[TEAM: add once board + PHY part number are finalized]`.

---

## 3.1.4 Quantitative Technical Analysis

### 3.1.4.1 Line-rate throughput (NFS9)

The maximum packet rate of the link is fixed by arithmetic, and the design must not stall below it. With the 24-byte payload `[TEAM: confirm final size]`:

```
Frame on wire = preamble/SFD 8 + Eth header 14 + IPv4 20 + UDP 8
 + payload 24 + FCS 4 + inter-frame gap 12
 = 90 bytes = 720 bits
Line-rate ceiling = 10^9 b/s ÷ 720 b = 1.389 M packets/s
```

(For any payload ≤ 18 B the 64-byte Ethernet minimum applies and the ceiling rises to 1.488 Mpps — the classic 64-byte wire-speed figure; our payload is above the pad threshold, so 1.389 Mpps governs.)

The NFS9 target of ≥ 1.2 M msg/s therefore means: **the pipeline must sustain the true wire-speed ceiling of this link, 1.389 Mpps, with zero drops** — there is no headroom between 1.2 M and the ceiling worth engineering to; the design targets the ceiling. The pipeline sustains it structurally: every stage consumes one octet per cycle at 125 MHz with initiation interval 1, so a new frame can begin on the cycle after the previous frame's IFG — the pipeline is never the bottleneck; the wire is. This matches the range reported for comparable single-feed FPGA book builders (1.2–1.5 M msg/s) [3] and hardware feed processing studies that exceed gigabit wire-rate ceilings on faster links [4]. OPEN: confirm with a full-rate PCAP injection test and zero drop-counter delta (NFS9 verification procedure).  
NFS9 的目标要求是每秒至少处理 1.2 百万条消息。这意味着管道必须能够维持该链路真正的线速上限，即 139.9 万条消息每秒，且不会出现任何性能下降——在 1.2 百万与线速上限之间并没有值得优化的空间；设计目标正是要达到这个上限。管道能够稳定支持这一速率：每个阶段在 125 MHz 的频率下每周期消耗一个八位组，且启动间隔为 1 周期，因此新的帧可以在前一个帧的 IFG 之后的下一个周期开始生成——管道从来不是性能的瓶颈，真正的瓶颈在于硬件层面。这一性能与一些类似的单输入 FPGA 处理器的报告结果一致（1.2–1.5 百万条消息每秒），以及那些在更快的链路上实现千兆位线速的硬件处理系统的性能表现。[3] 此外，这一性能还符合通过全速率 PCAP 注入测试并确保在零下降率下的性能测试（NFS9 验证流程）所得到的结果。

### 3.1.4.2 FS1 latency budget decomposition  
3.1.4.2 FS1 延迟预算分解

FS1 allows 1,100 ns from MAC RX to the snapshot becoming readable by the PS (endpoint: `seq`-increment write enable). At 125 MHz (8 ns/cycle):  
FS1 允许在 MAC RX 从 1,100 纳秒后，快照数据才能被 PS 端读取到（终端地址： `seq` - 增量写入启用）。在 125 MHz 的频率下（每周期 8 纳秒）：

|Stage  阶段/环节|Cycles  循环周期|Time  时间|Basis  基础|
|---|---|---|---|
|Preamble/SFD detection (8 B)  <br>前言/安全域检测（8 字节）|8|64 ns  64 纳秒|GMII: 1 octet/cycle; MAC RX stage must detect SFD before frame body parsing begins  <br>GMII：每周期处理 1 个八位组；在解析帧体之前，MAC 接收阶段必须检测到 SFD 信号|
|Frame body reception (70 B post-preamble, streaming)  <br>帧体接收（在序言部分之后，流媒体传输，70 字节大小）|70|560 ns  560 纳秒|GMII: 1 octet/cycle; parse overlaps reception (Decision 3), so this is reception time, not reception + parse  <br>GMII：每周期处理 1 个八位组；解析过程与接收过程重叠（决策 3），因此这里指的是接收时间，而不是接收加上解析的时间。|
|FCS check + commit gate  <br>FCS 检查阶段 + 提交关口|2|16 ns  16 纳秒|Registered compare + commit enable  <br>注册后的比较功能已启用，可以执行提交操作。|
|Order book update + top-of-book extract  <br>订单簿更新情况 + 订单簿顶部的摘录信息|4|32 ns  32 纳秒|Register-array write + combinational best-price mux, registered (OPEN: confirm 4-cycle timing in RTL simulation)  <br>寄存器阵列写入功能，结合组合式最佳价格多路选择器设计（开放申请：需在 RTL 仿真中确认 4 周期时序）|
|Snapshot register commit + `seq` increment  <br>快照寄存器提交 + `seq` 递增|1|8 ns  8 纳秒|Single-edge atomic write into the register bank  <br>单刃原子操作被写入寄存器组|
|**Total  总计**|**85**|**680 ns  680 纳秒**|**38% margin against FS1 = 1,100 ns; every stage is design arithmetic  <br>与 FS1 相比，毛利率为 38%，即 1,100 纳秒；每个阶段的设计都经过精确计算。**|

Two structural conclusions fall out of this table. First, 58% of the FS1 budget is consumed by physics (the preamble + frame must arrive), which is why Decision 3's cut-through overlap is not an optimization but a requirement: a store-and-forward second pass would consume most of the remaining budget for zero benefit. Second — and this is a direct consequence of the register-interface iteration described in 3.2.2 Decision 3 — the former governing unknown (AXI HP write latency into DDR3 under PS memory contention) has been eliminated from the FS1 path entirely: the endpoint is now a PL-internal register write whose latency is exactly one cycle by construction. FS1 compliance is therefore closed by arithmetic, pending only RTL simulation of the stated stage depths. Published HFT/market-data FPGA systems report sub-microsecond pipeline latencies on faster MACs (e.g., hundreds of nanoseconds) in similar parse→decision trigger chains, supporting the feasibility of microsecond-class PL budgets [2], [6]. _(Under the superseded DMA design, this row read "≤ 61 cycles, budget remainder, governing unknown" — retain that version as the documented iteration.)_  
从这张表格中可以得出两个关键结论。首先，FS1 预算的 58%被用于处理物理相关任务（即确保前置处理部分和框架的传输能够顺利完成）。因此，决策 3 所要求的优化并非必要，而是一种强制要求——因为进行二次处理会消耗掉大部分剩余预算，而这样做并无实际意义。其次，这是 3.2.2 节中描述的决策 3 迭代过程的直接结果——原本需要处理未知因素（例如在 PS 内存争用情况下向 DDR3 写入数据时的延迟问题）的问题，现在已经被完全解决了：现在的处理过程只是对 PL 内部寄存器的写入操作，其延迟恰好为一个周期。因此，FS1 的合规性问题已经通过算术运算得到了解决，现在只需对各个阶段的实现进行 RTL 仿真即可。目前公开的 HFT/市场数据 FPGA 系统能够在更快的 MAC 上实现亚微秒级的流水线延迟，例如在类似的解析→决策触发链中。支持微秒级 PL 预算的可行性[2][6]。在已被取代的 DMA 设计中，这一行描述为“≤ 61 个周期，预算剩余，控制方式未知”——保留这一版本作为文档记录。

### 3.1.4.3 Resource envelope (NFS6)  
3.1.4.3 资源限额（NFS6）

XC7Z020 PL resources: 53,200 LUTs, 106,400 FFs, 140 × 36 Kb BRAM (4.9 Mb), 220 DSP. NFS6 caps usage at 75% LUT (39,900) and 85% BRAM (119 blocks).  
XC7Z020 PL 的资源配置如下：拥有 53,200 个 LUT、106,400 个 FF，以及 140×36 千字节的 BRAM 内存（共计 4.9 Mb）。此外，还有 220 个 DSP 单元。NFS6 的缓存使用率达到了 75%的 LUT 资源（39,900 个单元）和 85%的 BRAM 资源（119 个块）。

|Component  组件|FF estimate (arithmetic)  <br>FF 的估算（算术方式）|LUT estimate|BRAM|
|---|---|---|---|
|Order book registers  订单簿已登记完毕|20 levels × 64 b + snapshot 128 b + counters ≈ 1.5 K  <br>20 个关卡 × 64 字节/关卡 + 快照数据 128 字节 + 计数器 ≈ 1.5 千字节|Best-price compare tree over 10 levels ≈ small  <br>在 10 个层级以上的价格比较中，选择最优惠的树木 ≈ 小型版本|0|
|Minimal MAC (RX+TX, CRC-32)  <br>最小 MAC 地址（接收端+发送端，CRC 校验 32 位）|≈ 0.5–1 K  ≈ 0.5–1 开|≈ 1–2 K (OPEN: confirm via synthesis)  <br>≈ 1-2 千卡（开放状态：通过合成确认）|0–2 (elastic FIFO)|
|Header parse/encode + protocol decode/encode  <br>头部数据解析/编码，以及协议数据的解码/编码操作|≈ 0.5 K  ≈ 0.5 开尔文|≈ 1 K (constant-compare + slicing)  <br>≈ 1 K（恒定比较 + 切片）|0|
|AXI-Lite register bank (GP0 slave)  <br>AXI-Lite 寄存器组（GP0 从属寄存器）|≈ 0.5 K  ≈ 0.5 开尔文|≈ 0.5–1 K (wizard-generated slave + decode) (OPEN: confirm via Vivado utilization report)  <br>≈ 0.5–1 开尔文（由法师生成的奴隶+解码过程）（开放状态：通过 Vivado 使用报告进行确认）|0|
|**Preliminary total  初步总数**|**≈ 3–4 K FF  ≈ 3–4 千赫兹的频闪效应**|**≈ 5–8 K LUT ≈ 9–15% of device  <br>≈ 5–8 K 设备 ≈ 占设备的 9–15%**|**≪ 10 blocks ≈ < 8%  <br>≪ 10 个街区 ≈ < 8%**|

The estimate sits a factor of ~5 below the NFS6 LUT ceiling, which is the deliberate margin motivating Decision 1's board choice: the same architecture on the XC7Z010 (17,600 LUTs) would already commit ~30–45% of the device before any capstone-scope growth (e.g., deeper book, added diagnostics). OPEN: replace all preliminary estimates with post-implementation Vivado utilization + timing summary; NFS6 pass gate is WNS > 0 at 125 MHz.

---

## 3.1.5 Specification Compliance Summary

|Spec|How the final design satisfies it|Evidence status|
|---|---|---|
|FS1|Cut-through parse overlaps reception; 85-cycle path to snapshot-register commit (including preamble/SFD), 38% margin (3.1.4.2)|Closed by arithmetic; pending RTL sim + ILA measurement|
|FS13|Fixed-offset TX encoder implements Table 3.1.5 byte-exactly|Design complete pending layout freeze|
|NFS1 (PL share)|RX segment ≤ 1.1 μs; TX encode segment is a fixed ~80-cycle (≈ 0.65 μs) path by the same octet-per-cycle arithmetic as 3.1.4.2 — doorbell latch + ~75 B order frame streamed at 1 octet/cycle|Analytical|
|NFS2|Point-to-point link, no switch, elastic FIFO sized for IFG-less bursts; drop counters make every discard attributable|Pending 10-min Wireshark test|
|NFS6|~9–15% LUT estimate vs. 75% cap (3.1.4.3)|Pending synthesis|
|NFS9|II=1 octet pipeline sustains the 1.389 Mpps wire ceiling (3.1.4.1)|Analytical; pending PCAP injection test|
|NFS8|FCS-fail discard + fault counters; no manual restart path in PL|Pending fault-injection test|

---

# 3.2 PS (ARM OS Layer) Strategy & Risk Subsystem  
3.2 PS（ARM 操作系统层）策略与风险子系统

> **Template conventions:** `[TEAM: …]` needs a team decision; `OPEN: …` is an analytical target pending simulation/measurement; `[REF-n]` maps to the bibliography. **Architecture baseline (v2):** hot-path interface is the **AXI-Lite register bank + doorbell on M_AXI_GP0** — no DMA, no interrupts, no HP ports on the intraday path. The earlier DMA/interrupt design is retained below only as documented iterations. All budgets are derived against **FS2 = 26 μs** (new wording: from a top-of-book update _becoming visible to the PS_ to MAC TX). **Diagram naming:** subsection names follow the latest block diagram — _Config Loader, Strategy Engine (Plug-In Execution), Runtime Risk Guard, Execution Logger, HOLD Mode_. `[TEAM: keep 3.2.x headings and diagram labels in lockstep.]`  
> 模板约定： `[TEAM: …]` 需要团队决策确认； `OPEN: …` 是一个分析性目标，需通过模拟或测量来验证其可行性； `[REF-n]` 与参考文献相关。架构基线（v2 版本）：热路径接口包括 AXI-Lite 寄存器组以及位于 M_AXI_GP0 上的门铃模块——在日内传输过程中不使用 DMA 技术、中断功能，也不涉及高级端口。早期的 DMA/中断设计仅作为文档中的示例保留下来。所有预算均基于 FS2=26 微秒的时间要求进行计算（新表述：从书籍顶部更新内容到 MAC TX 传输所需的时间）。图表命名规则：各子部分的名称遵循最新的框图命名方式——配置加载器、策略引擎（插件执行模块）、运行时风险防护模块、执行记录器、HOLD 模式。 `[TEAM: keep 3.2.x headings and diagram labels in lockstep.]`

---

## 3.2.1 Overview and Specification Mapping  
3.2.1 概述与规格说明的映射

The PS subsystem is the software half of the intraday trading loop, executing on the dual-core ARM Cortex-A9 of the XC7Z020. Core 1 — isolated from the Linux scheduler — busy-polls the PL's snapshot registers, evaluates the currently active strategy on each newly observed top-of-book update, filters every proposed order through the Runtime Risk Guard, and issues risk-approved orders back to the PL by writing the order-field registers followed by the doorbell. Core 0 owns everything latency-tolerant: configuration loading at startup (FS4), the Execution Logger and end-of-session export (FS5), the Debug-UART console feed (FS11), recoverable-fault logging (NFS8), and HOLD-mode supervision.  
PS 子系统是日内交易循环中的软件部分，运行在 XC7Z020 芯片的双核 ARM Cortex-A9 处理器上。核心 1 与 Linux 调度器独立运行，负责周期性查询 PL 的快照寄存器，评估每次新观察到的交易数据上活跃的策略，通过运行时风险防护机制筛选所有拟议的订单，并通过将订单字段写入寄存器来发出经过风险审核的订单。核心 0 则负责处理所有耐延迟的任务：启动时的配置加载（FS4）、执行日志记录、会话结束后的导出操作（FS5）、调试 UART 控制台输入（FS11）、可恢复故障日志功能（NFS8），以及 HOLD 模式下的监控功能。

The division of labour with the PL follows one rule established in 3.1: the PL owns everything that must be deterministic at wire speed; the PS owns everything that must be **changeable** — strategy formulas, parameters, and risk limits are all expected to be replaced nightly by the EOD pipeline (Section 3.3), and iterating on them must not require re-synthesis.  
与 PL 的分工遵循 3.1 中所确立的规则：PL 负责处理所有需要以高速确定性方式处理的事务；PS 则负责处理所有需要可变更的事务——比如策略公式、参数以及风险限制等，这些都需要每晚由 EOD 流程进行更新（参见 3.3 节），并且这些过程的迭代操作不需要再次进行整体整合。

|Spec|Role of PS subsystem|
|---|---|
|**FS2**|Sole owner of the software segment: observed snapshot update → decision (BUY/SELL/HOLD) → order handed to PL, inside the ≤ 26 μs budget.  <br>软件部分的唯一所有者：在≤26 微秒的时间内观察到快照更新，然后做出买入、卖出或持有的决策，并将订单下达给 PL 处理。|
|**FS3**|Sole owner: reject orders violating notional (> $50,000 CAD), position (> 1,000 shares), rate (> 1,000 orders/s), or in-flight (> 100) limits, with logged reason codes.  <br>唯一所有者：拒绝那些违反以下限制的订单执行——订单金额超过 50,000 加元、持仓数量超过 1,000 股、订单频率超过 1,000 个/小时，以及执行过程中订单数量超过 100 个。同时，会记录相关的错误原因代码。|
|**FS14**|Sole owner: track every in-flight order's state for the traded symbol, up to the configured capacity, and expose terminal outcomes to the logger.  <br>唯一所有者：记录交易符号在飞行过程中的订单状态，最多可达配置的容量上限，并将终端结果输出到日志器中。|
|**FS4**|Sole owner: load and validate the externally supplied strategy configuration before any market data is processed.  <br>唯一所有者：在处理任何市场数据之前，必须先加载并验证外部提供的策略配置。|
|**FS5**|Sole owner: bounded-memory persistence of decisions/outcomes/snapshots over > 10 M injected ticks, plus full-session export.  <br>唯一所有者：决策、结果或快照的存储采用有界内存方式，存储时间超过 1000 万个时间点；此外还支持整个会话的导出功能。|
|**FS11 (non-ess.)  FS11（非核心职位）**|Owner of the SoC side: real-time book/decision report over Debug UART.  <br>SoC 部分的负责人：通过 Debug UART 发送实时报表和决策报告。|
|**NFS1 (PS share)  NFS1（PS 份额）**|Owns the dominant software segment of the ≤ 50 μs typical budget.  <br>拥有占主导地位的技术领域，其应用范围涵盖了那些在 50 微秒以内完成的典型任务。|
|**NFS4**|Primary owner: 6.5-hour session with no crash/hang/unrecovered error.  <br>主要所有者：运行了 6.5 小时，期间没有出现崩溃、挂起或无法恢复的错误。|
|**NFS8 (partial)  NFS8（部分内容）**|Owner of software fault handling: malformed-config rejection at load time, fault-coded logging, continue-without-restart.  <br>软件故障处理功能的负责人：在加载时会出现配置错误，日志记录存在故障，无法在重启后继续运行。|

Figure 3.3 shows the PS runtime structure. _(Figure placeholder — must reuse the block-diagram labels above; the register bank appears once, on the PL/PS boundary, with the Feature Parameters and Trade Decision arrows passing through it.)_  
图 3.3 展示了 PS 运行时的结构。（图例占位符——需要重复使用上述框图中的标签；寄存器组出现在 PL/PS 边界处，带有特征参数和交易决策的箭头穿过该区域。）

---

## 3.2.2 Engineering Design Process  
3.2.2 工程设计流程

### Decision 1 — Hardware/software boundary: why the strategy engine is not in the PL  
决策 1——硬件/软件边界：为什么策略引擎并不属于 PL 范畴？

|Alternative  替代方案|Description|Outcome|
|---|---|---|
|Strategy in PL|Implement decision rules as fabric logic; sub-microsecond tick-to-order.|**Rejected.** Strategy formulas, thresholds, and the active strategy identity change nightly via the EOD JSON config (FS4/FS8). A PL implementation would either require re-synthesis per change (hours per iteration, incompatible with the EOD cycle) or a parameterized rule engine in fabric whose design and verification cost exceeds the entire remaining PL budget. Industry practice concurs: fixed protocol/risk primitives migrate to hardware, iterating alpha logic stays in software.|
|Strategy in PS (selected)|Evaluate rules on the Cortex-A9 against the observed snapshot.|**Selected.** A software strategy is reconfigured by rewriting a struct, tested with host-compiled unit tests, and debugged with standard tooling. The cost — microseconds instead of nanoseconds — is affordable: QTA 3.2.4.1 shows the FS2 budget closes with ~5× margin.|

This decision is the reason FS2's budget (26 μs) is three orders of magnitude looser than FS1's (1.1 μs): the specs deliberately price in the software boundary, and Decisions 2–3 carry the burden of proving the priced-in budget is achievable.

### Decision 2 — Operating environment: bare-metal, FreeRTOS, AMP, or Linux with core isolation

|Criterion (weight)|Bare-metal (both cores)|FreeRTOS|AMP (Linux + bare-metal core)|Linux + isolcpus (selected)|
|---|---|---|---|---|
|Hot-path determinism (30%)|Best|Good|Best on isolated core|Good — requires isolation measures (Decision 3)|
|TCP/IP, filesystem, UART tooling for FS4/FS5/FS11 (30%)|None — must port a network stack for the PS GbE paths|lwIP port; limited filesystem|Full on Linux core|Full, native|
|Team development & debug cost (25%)|High|Medium|High (OpenAMP, two-kernel shared-memory protocol)|Low — standard toolchain, matches team's embedded-Linux experience|
|NFS4 6.5-hour robustness path (15%)|All failure handling hand-rolled|Partial|Split-brain failure modes|Mature, observable (logs, watchdogs)|
|**Result**|Rejected|Rejected|**Documented fallback**|**Selected**|

The FS5 export and FS4/FS8 config paths both want a real TCP/IP stack and filesystem; bare-metal and FreeRTOS price those in as porting projects that add no marks. AMP delivers determinism plus Linux but introduces a two-kernel debugging burden — the classic capstone schedule-killer. Linux is selected **with the explicit obligation** to neutralize its scheduling jitter on the hot path, which is Decision 3's job. `[TEAM: confirm distro/kernel — PetaLinux vs. Ubuntu-based; PREEMPT_RT not required by the selected design.]`

### Decision 3 — Hot-path interface and event delivery: a three-iteration, spec-driven design history

This decision governs FS2 and went through three documented iterations; the reversals are driven by arithmetic, not preference, and each iteration is retained per the engineering-design-process requirement.

**Iteration 1 — AXI DMA + interrupt (superseded).** The initial design followed the dominant pattern in the literature: a PL DMA engine pushes each snapshot into a DDR3 ring via an HP port and raises an interrupt; a pinned SCHED_FIFO thread wakes and consumes,. This was designed against an early 200 μs stage budget and was internally consistent with it.

**Iteration 2 — FS2 tightened to 26 μs → interrupts infeasible.** Consolidating the spec table cut the software stage budget ~8×. Linux IRQ→userspace wakeup latency is typically 10–40 μs with worse tails `[TEAM: add a citable Linux IRQ→userspace latency measurement source]` — the _notification mechanism alone_ can exceed the entire budget. The replacement is a **busy-poll on an isolated core**: core 1 is removed from the scheduler (`isolcpus`, IRQ affinity to core 0) and spins awaiting new data. The classic objection — polling wastes compute — is void here: the A9 has exactly two cores, core 0 absorbs all housekeeping, and core 1 has no other duty during the session; burning an otherwise-idle core to remove 10–40 μs of nondeterminism is the cheapest latency purchase in the system.  
第二次迭代——将 FS2 的延迟调整为 26 微秒后，中断处理变得不可行。合并规格表使得软件阶段的预算减少了 1001 倍。在 Linux 系统中，用户空间唤醒的延迟通常为 10 到 40 微秒，而最坏情况下的延迟则高达 0 微秒——仅此通知机制就足以超出预算。解决方案是在一个独立的核心上执行轮询操作：将核心 1 从调度器中移除（ `isolcpus` ），使其专注于核心 0 的任务，同时让核心 1 处于空闲状态，等待新的数据。这里的经典反对意见——轮询会浪费计算资源——在这里并不适用：A9 系统恰好只有两个核心，核心 0 负责所有管理工作，而核心 1 在会话期间没有其他任务；因此，让原本空闲的核心消耗 10 到 40 微秒的延迟时间，实际上是系统中最经济的解决方案。

**Iteration 3 — busy-polling removes DMA's rationale → register bank + doorbell.** DMA earns its complexity (descriptor path, kernel driver, cache-coherency management — Zynq-7000 HP ports are not I/O-coherent) by moving bulk data without CPU involvement. With a core already dedicated to watching for a 16–24 B payload, that rationale is gone. The interface collapses to the simplest thing that works: the PL exposes the snapshot as **AXI-Lite registers plus an incrementing `seq`**; core 1 polls `seq` over M_AXI_GP0 and reads the fields on change. The egress direction is event-driven for free in hardware: the PS writes the order-field registers then a **doorbell register**, and the doorbell write strobe itself launches the PL encoder — payload-first/doorbell-last ordering makes torn sampling impossible without any lock.  
迭代 3——忙碌的轮询机制消除了 DMA 的必要性。DMA 之所以复杂（因为需要处理描述符路径、内核驱动程序以及缓存一致性管理——而 Zynq-7000 的硬件端口并不具备 I/O 一致性），是因为它需要在不需要 CPU 参与的情况下传输大量数据。现在，由于一个核心已经专门用于处理 16-24 字节的数据负载，这种复杂性就消失了。接口简化为最简单的形式：PL 将快照数据以 AXI-Lite 寄存器的形式输出，同时会有一个递增的 `seq` 操作；核心 1 通过 M_AXI_GP0 轮询 `seq` ，并在字段发生变化时读取它们的值。在硬件层面，出行的方向是由事件驱动的：PS 先写入订单字段寄存器，然后写入门铃寄存器，而门铃的写入脉冲则触发 PL 编码器——这种先传输数据后处理门铃的顺序方式，使得无需任何锁机制就能实现数据的采样。

**Reconciling with the literature (why our conclusion differs from the papers we cite).** Leber et al. and Morris et al. use DMA-to-ring architectures _because they are PCIe systems_ [1], [4]: a CPU read of an FPGA register over PCIe is a non-posted MMIO transaction costing on the order of a microsecond and stalling the pipeline, so the only efficient pattern is hardware-push into host RAM and CPU polling of cache-resident memory,. On Zynq, the on-chip GP port inverts that cost structure: a PL register read costs ~0.15–0.3 μs and the payload is 16–24 B, so the same design principle — _minimize the CPU's cost of observing new data_ — selects direct register polling instead. Kao et al. state the boundary explicitly: the DMA subsystem is appropriate for _non-timing-critical_ transfers such as supervision and reporting [2] — which is precisely where DMA survives in AQTA (the PS GEM's internal DMA on the EOD export and config-load paths, interfaces 6/8). Osuna et al.'s PYNQ-Z2 study is the cautionary converse of our 3.1 Decision 1: with the PHY wired to the PS, they were forced into a socket-receive-then-DMA-to-PL topology [7] — the board-level constraint our carrier-board selection was made to avoid.  
与现有文献一致（我们的结论与所引用的论文有所不同）。Leber 等人以及 Morris 等人采用 DMA 到环式架构，因为他们处理的是 PCIe 系统[1][4]：通过 PCIe 从 FPGA 寄存器读取数据的过程属于非并发的 MMIO 操作，其耗时约微秒级，还会导致流水线停滞。因此，唯一有效的方案是将数据直接推入主机 RAM，并由 CPU 轮询缓存中的内存。而在 Zynq 平台上，片上 GP 端口改变了这种成本结构：PL 寄存器读取数据的耗时为 1001#0.15–0.3 微秒，而数据负载为 16–24 字节。因此，同样基于最小化 CPU 处理新数据成本的原理，他们选择直接轮询寄存器。Kao 等人则明确指出了 DMA 子系统的适用场景：它适用于那些不要求实时处理的传输任务，比如监控和报告等[2]——而这正是 DMA 在 AQTA 中的应用场景（PS GEM 在 EOD 导出和配置加载路径中使用的内部 DMA 功能）。Osuna 等人的 PNQ-Z2 研究实际上是对我们 3.1 决策方案的警示性反例：由于 PHY 接口被连接到 PS 端，他们不得不采用一种由插座接收数据，然后再通过 DMA 传输到 PL 端的拓扑结构[7]——这正是我们在选择电路板时试图避免的约束条件。

|Alternative (final trade study)|End-to-end estimate|Implementation cost|Outcome|
|---|---|---|---|
|Interrupt + DMA ring|10–40 μs wakeup dominates|DMA IP + driver + coherency|Rejected — worst case exceeds FS2|
|Busy-poll + DMA ring  <br>忙轮询 + 直接内存访问环|~1–1.5 μs  ~1–1.5 微秒|DMA IP + driver + coherency  <br>DMA IP + 驱动程序 + 一致性处理|Rejected — μs-class, but pays full DMA complexity for a 24 B payload  <br>被拒绝——属于μs 类，但对于 24 B 的数据量来说，其处理复杂度仍然很高。|
|**Busy-poll + register bank + doorbell (selected)  <br>忙时投票机制 + 注册银行 + 门铃功能（可选）**|~2 μs  ~2 微秒|Wizard-generated AXI-Lite slave + user-space mmap; zero driver, zero coherency  <br>由巫师生成的 AXI-Lite 从模块 + 用户空间的内存映射；没有驱动程序，也没有一致性机制|**Selected — μs-class latencies are indistinguishable against 26 μs; the decision criterion is implementation and verification cost, where the register bank wins decisively  <br>入选——微秒级延迟在与 26 微秒的对比中几乎无法被区分；决策标准在于实现和验证的成本，在这方面，寄存器库取得了明显的优势。**|

Note the honest framing: the register path is _not_ claimed to be faster than a well-built DMA push — both are single-digit μs. It is claimed to be **equally fast where it matters and drastically cheaper to build and verify**, which is the correct optimization target for this team and schedule.  
请注意这种诚实的表述方式：该接口路径并不被声称比性能优良的 DMA 推送方式更快——两者的响应时间都在个位数微秒级别。该接口在关键场景中的性能同样出色，而且其设计和验证的成本也低得多。这正是该团队所追求的优化目标，也是他们的设计计划。

### Decision 4 — Execution Logger architecture: the memory arithmetic forces the record policy  
决策 4——执行日志器架构：内存运算机制决定了记录策略的实施方式

FS5 demands > 10 M ticks with bounded memory. The naive design — one full record per tick — fails by arithmetic before any code is written (QTA 3.2.4.3): 10 M × 128 B = 1.28 GB against roughly 512 MB of DDR3 realistically available, and at the 1.389 Mpps wire ceiling a full-rate log stream (~178 MB/s) exceeds any on-board sink's sustained write rate.  
FS5 要求内存使用量超过 1000 万次写入操作。这种简单的设计——每次写入操作只记录一次数据——在编写任何代码之前就因算术错误而失败（参见 QTA 3.2.4.3）：1000 万次写入操作乘以 128 字节，总计 1.28 吉字节的数据量，而实际可用的 DDR3 内存仅能容纳约 512 兆字节的数据。在 1.389 百万每秒的写入速率下，全速率日志流的数据写入速率约为 178 兆字节每秒，这远远超过了板上存储设备的持续写入能力。

|Alternative  替代方案|Description  描述|Outcome  结果|
|---|---|---|
|Full per-tick log in DRAM  <br>完整的每笔交易日志数据，存储在 DRAM 中|One record per snapshot  <br>每个快照只能记录一条记录|**Rejected by capacity arithmetic.  <br>因容量计算错误而被拒绝。**|
|Full per-tick log streamed to eMMC/SD  <br>完整的每笔交易日志已上传到 eMMC/SD 存储设备中。|Continuous spill  持续泄漏|**Rejected**: worst-case bandwidth exceeds eMMC sustained write (OPEN: measure board eMMC sustained write bandwidth); a storage stall would back-pressure the hot path.  <br>被拒绝：最坏情况下的带宽超过了 eMMC 的持续写入能力限制（开启时测量到的 eMMC 持续写入带宽不足）；存储延迟可能会导致热路径出现压力问题。|
|Decision-complete + snapshot-sampled ring (selected)  <br>决策完整性高 + 采样快照功能（可选）|Log **every** decision/outcome record (rate structurally capped by FS3's 1,000 orders/s) plus book snapshots at a sampling interval and on order events; fixed pre-allocated ring in cached DDR3, written by core 1, drained asynchronously by core 0  <br>记录每一个决策或结果，记录频率受 FS3 的限制，即每秒 1000 条记录。同时，以一定的采样间隔记录订单事件的相关信息。这些数据存储在缓存的 DDR3 内存中，由核心 1 负责写入，而数据则由核心 0 异步处理。|**Selected.** Decision records are what FS5's verification inspects ("one entry per decision"); FS3 caps their rate, so bandwidth is trivially bounded (3.2.4.3). Static allocation at startup — no malloc on the hot path, no OOM by construction.  <br>已选中。FS5 的验证检查会针对每个决策记录进行记录（即“每个决策只记录一条记录”）；FS3 限制了这种记录的频率，因此带宽被严格限制了（参见 3.2.4.3 节）。在启动时采用静态分配方式——在热点路径上不会进行内存分配操作，从而避免了内存耗尽的问题。|

Note the logger is now **pure software**: core 1 writes an ordinary cached DDR3 ring; the PL is not involved and no cross-boundary protocol exists for logging. (PL-side diagnostic counters reach the log because core 0 periodically reads the `DIAG_*` registers through the same GP0 bank — a free by-product of the register interface.) **Snapshot sampling policy (selected):** periodic sampling at 100 Hz (every 10 ms) **plus** one snapshot on every order event; ring size 256 MB; flush sink: core 0 drains the ring to eMMC continuously during the session, with the full-session export over PS GbE (interface 6) at session end. These are the same working figures already carried by the arithmetic in 3.2.4.3 and 3.3.4.1. `[@cye: 100 Hz 采样率是经验值 — 回头在论文里找有依据的 snapshot 采样率数据再替换/背书]`  
请注意，现在的日志记录功能仅基于软件实现：核心 1 会生成普通的缓存 DDR3 环形数据；PL 端并未参与其中，也没有任何跨边界的协议用于日志记录。（PL 端的诊断计数器也会被记录到日志中，因为核心 0 会定期通过相同的 GP0 内存组读取 `DIAG_*` 寄存器——这是寄存器接口的一个免费副产品。）采样策略如下：以 100Hz 的频率进行周期性采样（每 10 毫秒一次），并且在每个事件发生时还会生成一个快照；环形数据的容量是 256MB；在会话期间，核心 0 会持续将环形数据写入 eMMC 存储设备；在会话结束时，会通过 PS GbE 接口（接口 6）将整个会话的数据导出到外部存储中。这些具体数值与 3.2.4.3 和 3.3.4.1 中的计算结果是一致的。 `[@cye: 100 Hz 采样率是经验值 — 回头在论文里找有依据的 snapshot 采样率数据再替换/背书]`

### Decision 5 — Runtime Risk Guard placement: PS software vs. PL hardware

Pre-trade risk in fabric is the industry pattern for exchange-facing gateways, and a PL Risk Guard was considered. It is rejected for this prototype on three grounds: (1) FS3's limits are EOD-configurable, so a PL implementation needs a writable-register interface plus its own verification — cost without marks; (2) QTA 3.2.4.4 shows the software cost is < 100 cycles ≈ 0.5% of the FS2 budget — there is no latency case for hardware; (3) placing the guard _after_ the strategy in the same thread guarantees no order path can bypass it, which is simpler to argue for FS3's verification than a split HW/SW trust boundary. The PL retains a residual structural guard: the Order Emitter can only transmit packets assembled from fields the PS wrote through the register bank, in the FS13 fixed format — malformed egress is impossible by construction.

### Decision 6 — Order-terminal semantics for FS14: execution report vs. modeled fills (selected)

FS14/FS3(d) make “in-flight” a real, testable quantity; the design must define when an order stops being in-flight. The prototype selects a PS-only modeled fill delay **T**: on submission, an order enters the open-order table as in-flight and is treated as terminal after **T** elapses, at which point position and the execution-outcome log update. This is deterministic, requires no protocol changes, and makes the FS14 verification procedure feasible by arithmetic (e.g., at 1,000 orders/s, **T = 0.1 s** drives the in-flight count to 100).

---

## 3.2.3 Final Design Details

### 3.2.3.1 The PL/PS register bank and access protocol (interface contract)

The entire intraday PL/PS boundary is one AXI-Lite slave in the PL, mapped through M_AXI_GP0. This table is the interface contract, jointly owned with 3.1:

|Offset|Register|Dir (PS view)|Semantics|
|---|---|---|---|
|0x00|`SEQ`|R|Increments atomically with each snapshot commit; core 1 polls this|
|0x04–0x10|`BEST_BID_PRICE`, `BEST_BID_QTY`, `BEST_ASK_PRICE`, `BEST_ASK_QTY`|R|Feature Parameters (top-of-book snapshot) `[TEAM: extend if the Market Feature Builder emits more fields]`|
|0x14–0x18|`TIMESTAMP_LO/HI`|R|PL hardware timestamp of the committing packet|
|0x20–0x2C|`DIAG_PARSE_ERR`, `DIAG_FCS_FAIL`, `DIAG_DROP_OOW`, …|R|NFS8/NFS2 counters, read periodically by core 0  <br>NFS8/NFS2 计数器，由核心 0 定期读取|
|0x40–0x4C|`ORD_SYMBOL_SIDE`, `ORD_QTY`, `ORD_PRICE`, `ORD_ID`|W|Order fields (FS13 source values)  <br>订单字段（来自 FS13 的数据值）|
|0x50|`DOORBELL`|W|Write-1 launches the Order Emitter; **payload first, doorbell last**  <br>Write-1 启动了“订单发射器”功能；先处理载荷任务，最后处理门铃任务。|
|0x54|`TX_READY`|R|Egress flow-control invariant (see 3.2.4.2)  <br>出流控制不变量（参见 3.2.4.2 节）|

**Consistency protocol.** PL-side commits are single-clock-edge atomic (all snapshot registers + `SEQ` update together), so tearing exists only on the PS side, where reading 4–6 registers spans ~1 μs of separate AXI transactions. Core 1 uses a seqlock: read `SEQ`, read fields, re-read `SEQ`; on mismatch, retry. `[Documented alternative: a shadow-bank latch on` SEQ `read — rejected because read-side-effect registers complicate debug tooling for no measurable gain.]` On the egress side no lock exists or is needed: the PL samples order fields only on the doorbell strobe.  
一致性协议。PL 端的提交操作是依赖于单时钟沿完成的原子操作（所有快照寄存器以及 `SEQ` 的更新都同时发生）。因此，只有在 PS 端才存在数据撕裂问题，因为读取 4 到 6 个寄存器需要花费~1 微秒的时间，并且需要多个 AXI 事务来完成。核心 1 使用 seqlock 机制：先读取 `SEQ` ，然后读取相关字段，最后再读取 `SEQ` ；如果结果不一致，则重新尝试。 `[Documented alternative: a shadow-bank latch on`  SEQ  `read — rejected because read-side-effect registers complicate debug tooling for no measurable gain.]` 在 egress 端则不需要任何锁机制，因为 PL 端只在门铃闪烁时才会采样顺序字段。

**Conflation semantics (deliberate).** The bank holds the _latest_ snapshot; if ticks outrun the polling loop, intermediate snapshots are overwritten and the strategy always decides on the current book rather than a queue of stale ones. QTA 3.2.4.2 shows this is not a compromise: the CPU could not process every tick regardless, and latest-value conflation is the standard market-data semantics for top-of-book strategies. NFS9 is unaffected — the PL still ingests and books every packet at line rate; conflation applies only to what the PS samples.  
这种语义的合并是有意为之。银行持有最新的数据快照；如果数据更新频率超过轮询周期，那么中间的数据快照会被覆盖，策略始终基于当前的数据进行决策，而不是使用过期的数据。QTA 3.2.4.2 指出，这并不是一种折中的方案：无论如何，CPU 都无法处理每一刻的数据，因此最新的数据合并方式才是顶级策略中市场数据的标准语义。NFS9 并未受到影响——PL 仍然以线速的方式处理并存储每一数据包；合并仅适用于 PS 所采样的数据。

### 3.2.3.2 Strategy Engine (Plug-In Execution)  
3.2.3.2 策略引擎（插件执行）

The engine is a table dispatch: the active strategy ID (from the FS4 config) indexes a function table; each strategy is a pure function of (snapshot, rolling state, parameters) → {BUY, SELL, HOLD} + order fields. Rolling state is fixed-size (e.g., a lookback ring of midprices), so per-tick cost is O(1) and independent of session length.  
该引擎是一个表式调度器：活跃的策略 ID（来自 FS4 配置）会索引一个函数表；每个策略都是(快照数据、滚动状态、参数)→{买入、卖出、持有}与订单字段的纯函数运算结果。滚动状态的大小是固定的（例如，基于中间价的历史数据环），因此每笔交易的成本为 O(1)，且不受会话长度的影响。

|Regime  政权制度|Strategy  策略|Input signals  输入信号|Decision rule  决策规则|
|---|---|---|---|
|Trending  热门趋势|Momentum  势头|Midprice sequence over configured lookback  <br>在配置好的回看时间跨度内，中间价格序列的走势|`m = mid_t − mid_{t−L}`; BUY if `m ≥ +θ_entry`, SELL if `m ≤ −θ_entry`, else HOLD  <br>`m = mid_t − mid_{t−L}` ；如果满足 `m ≥ +θ_entry` 条件则买入，如果满足 `m ≤ −θ_entry` 条件则卖出，否则保持持有。|
|Ranging  范围在…之间|Mean Reversion  均值回归|Midprice deviation from moving average  <br>均价与移动平均线的偏差|`d = mid_t − SMA_W(mid)`; BUY if `d ≤ −θ_dev`, SELL if `d ≥ +θ_dev`, else HOLD (trade toward the mean)  <br>`d = mid_t − SMA_W(mid)` ；如果满足 `d ≤ −θ_dev` 条件则买入，如果满足 `d ≥ +θ_dev` 条件则卖出，否则保持持有（朝着均值方向交易）|
|Volatile  易挥发物质|Defensive  防御性|Spread, volatility flag, position state  <br>波动性指标：波动旗语；持仓状态：……|If `spread ≥ spread_floor` or the vol flag is set: suppress new entries and emit only position-reducing orders toward flat; else HOLD  <br>如果 `spread ≥ spread_floor` 或 vol 标志被设置：则忽略新的交易记录，只发出用于降低持仓的订单；否则保持原状。|

`mid` is held in half-cent units (`best_bid + best_ask`) so the arithmetic stays integer; thresholds are configured in the same units. Every window, threshold, and position scalar loads from the FS4 JSON config — the parameter names are exactly the axes swept in 3.3.3a.3 (`lookback/entry_thresh/pos_scalar`, `window/dev_thresh/pos_scalar`, `spread_floor/vol_cutoff/pos_scalar`) — so tuning never requires recompilation. The formulas are deliberately simple: per-strategy sophistication lives in the EOD parameter sweep (3.3), not the intraday rule; the design's contribution is the deterministic, reconfigurable evaluation machinery, not the alpha.  
`mid` 以半分率单位表示，因此运算结果始终为整数；阈值也采用相同的单位进行配置。所有窗口、阈值和位置标量参数都从 FS4 JSON 配置文件中加载——这些参数的名称与 3.3.3a.3 中的轴名称完全一致（ `lookback/entry_thresh/pos_scalar` 、 `window/dev_thresh/pos_scalar` 、 `spread_floor/vol_cutoff/pos_scalar` ）。因此，调整参数时无需重新编译程序。这些公式设计得非常简洁：策略复杂度体现在 EOD 参数扫描中（3.3 节），而不是日内规则中；该系统的独特之处在于其可定制的评估机制，而非 Alpha 值。

All arithmetic is integer (prices already in cents from the PL), avoiding FPU state on the isolated core and making decisions bit-reproducible for backtest cross-validation against the EOD pipeline. The integer-only commitment is confirmed as a binding design commitment; it also extends FS7's determinism property to the SoC side.  
所有的算术运算都使用整数类型（因为价格已经以分的形式呈现了），这样可以避免独立核心上出现 FPU 状态问题，同时使得决策结果能够重复用于针对 EOD 流程的回测和交叉验证。这种仅使用整数的设计决策被确认为一项不可更改的设计承诺；此外，这一特性还扩展了 FS7 在系统级芯片层面的确定性特性。

### 3.2.3.3 Runtime Risk Guard (FS3)  
3.2.3.3 运行时风险防护机制（FS3）

Executed unconditionally after every non-HOLD decision, in-thread:  
在每个非“保留”决策之后，都会无条件执行该决策；在讨论过程中也是如此。

|Check  检查完毕|Rule  规则|Mechanism  机制|
|---|---|---|
|Notional  名义上的|qty × price ≤ $50,000 CAD limit (configurable)  <br>数量 × 价格 ≤ 50,000 加元的限制（可配置）|32×32→64-bit multiply, one compare  <br>32×32→64 位乘法运算，进行一次比较|
|Position  位置|\|position ± qty\| ≤ 1,000 shares  <br>\|职位 ± 数量\| 不超过 1,000 股|Signed accumulate against local position state, one compare  <br>针对本地位置状态进行累加操作，进行一次比较|
|Rate  利率|≤ 1,000 orders/s  ≤ 1,000 订单/秒|Token bucket: capacity 1,000, refill from the global timer via fixed-point multiply-shift — no divides on the hot path (3.2.4.4)  <br>令牌桶机制：容量可达 1000 个令牌。通过固定点乘移位操作从全局计时器中进行补充令牌——在热路径上不会进行除法运算（3.2.4.4 节）|
|In-flight  飞行中|in-flight count ≤ 100  <br>飞行中的计数≤100|Compare against open-order table occupancy counter (increment on doorbell; decrement on modeled terminal transition — Decision 6)  <br>将结果与开放订单表的占用计数器进行比较（在门铃响起时增加计数；在模拟终端转换时减少计数——决策 6）|

Rejections write a reason-coded record to the Execution Logger (FS3's "logged reason code") and never reach the doorbell. A REJECT may also assert the Runtime Trigger into HOLD Mode (3.2.3.6). Limits load from the FS4 config and are immutable during a session.  
被拒绝的情况会在执行日志中留下一个编码记录（FS3 的“记录编码”），此时程序不会继续执行。此外，REJECT 状态还可能使程序进入暂停模式（3.2.3.6）。这些限制是根据 FS4 配置设定的，并且在会话期间是不可改变的。

### 3.2.3.3.1 Open-order table (FS14)  
3.2.3.3.1 开放订单表（FS14）

Core 1 maintains a fixed, pre-allocated open-order table of ≥ 128 entries `{order_id, side, qty, price, submit_timestamp, state}` for the traded symbol. The capacity is sized at startup from the FS4 config (bounded by FS3(d)'s ceiling), and overflow is impossible because the Risk Guard's in-flight check rejects before insertion. Orders transition to terminal by the modeled fill-delay policy (Decision 6); each terminal transition produces an execution-outcome record for FS5.  
核心 1 模块维护着一个固定的、预先分配好的订单表，该表包含至少 128 个条目，用于管理相关交易符号的订单处理。这个容量在系统启动时根据 FS4 配置进行设定（由 FS3(d)的上限决定），因为订单在插入之前就会被 Risk Guard 系统自动拒绝。订单会根据建模好的填充延迟策略转移到终端模块中进行处理（参见决策 6）；每次订单转移到终端模块后，都会为 FS5 生成一份执行结果记录。

### 3.2.3.4 Config Loader (FS4) and fault handling (NFS8)  
3.2.3.4 配置加载器（FS4）与故障处理（NFS8）

At startup, before core 1 begins polling, the loader ingests the JSON configuration (either from the board's SD/TF card slot or via a TCP push from the EOD server — interface 8), validates schema, ranges, and the operator-approval hash (FS8 chain of custody), and populates the strategy table and Risk Guard limits. Any validation failure is NFS8's "malformed config" case: log fault code, refuse to start the polling loop, remain up for re-push — never trade on a default. Market data processing is structurally unreachable until a config commits, which is FS4's verification argument.  
在启动阶段，在核心 1 开始轮询之前，加载器会读取 JSON 配置文件（该配置可以从板的 SD/TF 卡插槽中获取，也可以通过 EOD 服务器的 TCP 传输获得——接口 8）。之后，加载器会验证配置文件的格式、范围以及操作员的审批哈希值（FS8 的保管链），然后填充策略表和风险防护限额。如果验证失败，就会归类为 NFS8 的“配置错误”情况：记录故障代码，拒绝启动轮询循环，保持运行状态以便进行重新推送——绝不会使用默认配置进行交易。在配置文件被确认之前，市场数据处理是无法进行的，而 FS4 则认为这是他们的验证要求。

### 3.2.3.5 Execution Logger and Console (FS5, FS11)  
3.2.3.5 执行记录器和控制台（FS5、FS11）

Core 0 owns everything off the hot path: draining the history ring to the flush sink, the end-of-session export over PS GbE to the EOD server (interface 6), periodic `DIAG_*` register sampling into the log, and the FS11 console feed — a rate-limited (`[TEAM: e.g., 1 Hz]`) rendering of current book top and recent decisions over Debug UART (interface 5). The UART feed reads the same ring; it adds zero work to core 1.  
核心 0 负责处理所有非直接相关的任务：将历史数据传输到 flushing 缓存中，通过 PS GbE 协议将会话结束后的数据导出到 EOD 服务器（接口 6），定期使用 `DIAG_*` 寄存器对日志进行采样，以及通过 FS11 控制台输出当前书籍的目录和最近的决定——这些操作都通过 Debug UART 接口（接口 5）进行。UART 接口同样负责读取相同的数据；这些操作对核心 1 来说几乎不需要任何额外的工作。

**Execution record schema (frozen — 128 B fixed).** One record per strategy decision, execution outcome, sampled snapshot, Risk Guard REJECT, or fault event, written by core 1 as a single fixed-size struct copy:  
执行记录模式（冻结状态——128 字节固定大小）。每个策略决策、执行结果、采样快照、风险防护拒绝结果或故障事件都会对应一个记录。这些记录由核心 1 以单个固定大小的结构体形式存储。

|Field  字段|Offset (B)  抵消（B）|Size (B)  尺寸（B）|Content  内容|
|---|---|---|---|
|`record_type`|0|1|0x01 DECISION, 0x02 OUTCOME, 0x03 SNAPSHOT, 0x04 REJECT, 0x05 FAULT  <br>0x01 决策，0x02 结果，0x03 快照，0x04 拒绝，0x05 故障|
|`decision`|1|1|0x00 HOLD, 0x01 BUY, 0x02 SELL (0x00 for non-decision records)  <br>0x00 持有，0x01 购买，0x02 出售（0x00 表示非决策性记录）|
|`strategy_id`|2|1|Active strategy index (FS4 config)  <br>活跃策略指数（FS4 配置）|
|`reason_code`|3|1|FS3 reject reason / NFS8 fault code; 0 otherwise  <br>FS3 模块出现拒绝响应的原因/NF8 模块出现故障代码；否则为 0。|
|`seq`|4|4|PL snapshot `SEQ` this record was decided against  <br>PL 快照 `SEQ` 该记录被否决了|
|`pl_timestamp`|8|8|`TIMESTAMP_HI:LO` of the committing packet (3.2.3.1)|
|`cpu_timestamp`|16|8|Core-1 PMU cycle count (CCNT) — FS2 instrumentation for free|
|`best_bid_price`, `best_bid_qty`, `best_ask_price`, `best_ask_qty`|24|16|Top-of-book at decision time (4 × u32, integer cents / shares)|
|`order_id`|40|4|0 if no order emitted|
|`order_qty`, `order_price`|44|8|2 × u32; 0 if no order|
|`position_after`|52|4|Signed shares after this record's effect|
|`inflight_count`|56|4|Open-order table occupancy after this record|
|`realized_pnl`|60|8|Cumulative, signed integer cents|
|`reserved`|68|60|Zero-filled — pads to 128 B and absorbs schema growth without a size change|

### 3.2.3.6 HOLD Mode

HOLD is a state, not a message. On the per-decision level, HOLD simply means **no doorbell write** — nothing crosses to the PL, and a HOLD record enters the logger. On the session level, HOLD Mode is a latched supervisory state entered by (a) the Runtime Trigger from a Risk Guard REJECT pattern — trigger rule: **≥ 3 REJECTs within a rolling 10 s window** latches HOLD (both values load from the FS4 config; the working values are deliberately conservative so the prototype fails safe), or (b) the EOD path's "REJECT / No Approval" outcome; while latched, the strategy output is forced to HOLD until an operator action clears it. Because HOLD requires no PL cooperation, no cross-boundary protocol element exists for it — the diagram's "Hold Decision" arrow into the PL should be removed or re-annotated as "(no doorbell)". `[TEAM: confirm with diagram owner.]`  
“HOLD”是一个状态，而不是一条消息。在每决策层面，HOLD 仅仅意味着不进行门铃处理——没有任何数据传递到 PL 层面，而 HOLD 状态会被记录到日志中。在会话层面，HOLD 模式是一种锁定的监控状态，其触发方式有两种：(a)由 Risk Guard REJECT 模式中的运行时触发器触发——如果在一个 10 秒的时间窗口内触发 3 次 REJECT，则触发 HOLD 状态（这两个数值都来自 FS4 配置文件；这些数值故意设定得较为保守，以确保原型系统的安全冗余功能能够正常工作）；或者(b)在 EOD 路径中遇到“REJECT/无批准”的结果。在锁定状态下，策略输出会被强制保持 HOLD 状态，直到有操作员采取行动将其解除。因为 HOLD 状态不需要与 PL 层面进行任何交互，所以不存在与之相关的跨边界协议元素——图表中指向 PL 层面的“HOLD 决策”箭头应该被移除或重新标注为“（无门铃）”。 `[TEAM: confirm with diagram owner.]`

---

## 3.2.4 Quantitative Technical Analysis  
3.2.4 定量技术分析

### 3.2.4.1 FS2 latency budget decomposition (26 μs at 766 MHz)  
3.2.4.1 FS2 的延迟预算分解结果（在 766 MHz 频率下为 26 微秒）

26 μs ≈ 19,900 CPU cycles at 766 MHz (the Cortex-A9 max frequency on the target board). The budget also funds the PL egress tail (doorbell-to-MAC-TX ≈ ~1 μs by 3.1 arithmetic), leaving ~25 μs for software:  
26 微秒 ≈ 19,900 个 CPU 周期，频率为 766 兆赫（目标板上 Cortex-A9 处理器的最大频率）。预算还预留了足够的时间用于 PL 模块的退出操作（从门铃到 MAC-TX 的传输时间约为 1001 纳秒，通过 3.1 的算术运算得出）；剩余的 1002 纳秒用于软件处理。

|Stage  阶段/环节|Estimate  估算值|Basis  基础|
|---|---|---|
|Detect new `SEQ` (one GP0 read)  <br>检测到新的 `SEQ` （一个 GP0 读取操作）|~0.15–0.3 μs  ~ 0.15–0.3 微秒|AXI-Lite read via GP (OPEN: PMU/ILA microbenchmark — the single number this table hangs on)  <br>AXI-Lite 通过 GP 进行读取（开放模式：PMU/ILA 微基准测试——这是该表所依赖的唯一数值）|
|Snapshot read: 4–6 field reads + seqlock re-read  <br>快照读取：4–6 个字段的读取操作，加上一次 seqlock 数据的重新读取|~1–1.8 μs  ~1–1.8 微秒|6–8 GP reads; retry probability bounded in 3.2.4.2  <br>6 到 8 个 GP 的读取次数；重试概率在 3.2.4.2 的范围内有限制。|
|Strategy evaluation  策略评估|≤ ~1 μs  ≤ ~1 毫秒|Hundreds of integer ops on O(1) state — generous ceiling  <br>在 O(1)时间复杂度下，可以进行数百次整数运算——上限相当高。|
|Runtime Risk Guard  运行时安全保护机制|≪ 0.1 μs  ≪ 0.1 微秒|< 100 cycles (3.2.4.4)  <br>< 100 次循环（3.2.4.4）|
|Logger record write  记录写入操作已完成。|≤ ~0.5 μs  ≤ ~0.5 微秒|Fixed 128 B struct copy into cached ring  <br>将 128 B 的数据结构复制至缓存环区中。|
|Order-field writes + doorbell (5 GP writes)  <br>Order-field 写入了 + 门铃（5 个通用写入操作）|~0.5–1 μs  ~0.5–1 微秒|AXI-Lite posted writes  AXI-Lite 写道：|
|**Software total  软件总量**|**≤ ~5 μs  ≤ ~5 微秒**|**≥ 5× margin against the ~25 μs share; worst case is what FS2's 1,000-tick verification samples  <br>≥ 5× 相对于~25 微秒的保证金；最坏的情况是 FS2 的 1,000 个 tick 的验证样本会出现问题。**|

Under the rejected interrupt design, the first row alone costs 10–40 μs (OPEN: add a citable Linux IRQ→userspace latency measurement source) — 40–160% of budget before any work. The selected design's entire path is bounded by countable bus transactions. OPEN: replace estimates with PMU (CCNT) per-stage instrumentation across 1,000 ticks, then the Wireshark end-to-end check.  
在采用被否决的中断处理方案的情况下，仅第一行的处理时间就需要 10 到 40 微秒（开放方案：需要增加一个可引用的 Linux IRQ 到用户空间之间的延迟测量点）——这相当于预算的 40%到 160%。而采用所选设计方案的话，整个处理路径的延迟将受到可计数总线事务次数的限制。请使用 Wireshark 进行端到端的测试，并将估计值替换为每阶段所需的 PMU（CCNT）资源，同时确保在 1000 个时钟周期内都能保持稳定。

### 3.2.4.2 Interface capacity, conflation, and the DMA comparison

Three rates bound the system (using the GP-read estimate above, worst case 0.3 μs):

```
Snapshot read cost (6 reads + seqlock): ~1.5–2 μs → PS observation ceiling ≈ 500–600 K snapshots/s
Full decision iteration (table 3.2.4.1): ~5 μs → PS decision ceiling ≈ 200–330 K decisions/s
Wire tick ceiling (3.1.4.1): 1.389 M ticks/s
```

The PS cannot observe every tick (600 K < 1.389 M) — but it cannot _process_ every tick either (330 K < 1.389 M): **the bottleneck is the CPU, not the interface.** A DMA ring would not raise either ceiling; it would only queue ticks the CPU cannot consume, forcing the strategy to act on progressively staler books — for trading, a negative. A ring consumer would end by skipping to the newest entry, i.e., re-implementing conflation with more hardware. Conflation is therefore the _correct_ semantics given CPU throughput < wire rate, not a limitation accepted for convenience. Seqlock retry probability: a retry occurs only if a commit lands inside the ~1.5 μs read window; even at full wire rate the expected retries per read ≈ 1.5 μs × 1.389 M/s ≈ 2 — bounded by capping retries at `[TEAM: e.g., 4]` and accepting the newest consistent snapshot. OPEN: record a retry-rate counter during full-rate injection.

**Sensitivity boundaries (when this interface stops being right):**

|Condition|Register path|Conclusion|
|---|---|---|
|Current spec: 1 symbol, top-of-book, conflation acceptable|~1.5–2 μs/read, ≥ 5× FS2 margin|**Adequate — selected**|
|Payload > ~100 B/event (e.g., 10-level depth)|~40 reads ≈ 10 μs — erodes margin|Migrate to a **GP-mapped dual-port BRAM window** (PL BRAM as AXI slave) — still no DMA IP, no driver|
|Per-tick consumption required (no conflation)|Observation ceiling < wire rate|DMA ring required — and a faster CPU with it; out of prototype scope|

**TX contention arithmetic:** FS3 caps orders at 1,000/s (≥ 1 ms spacing) vs. ~1 μs per packet transmit — a 1000× margin; `TX_READY` exists as a correctness invariant, not a performance mechanism.

### 3.2.4.3 FS5 memory budget arithmetic

Record size = 128 B (schema frozen in 3.2.3.5):

```
Full per-tick logging: 1.389 M/s × 128 B ≈ 178 MB/s bandwidth; 10 M ticks × 128 B = 1.28 GB capacity
Available DDR3 (approx): PS DDR3 is 1 GB total (2×512 MB). Assuming ≈ 512 MB remains available after OS + code is a reasonable working budget for FS5 planning.
Decision-record ceiling: 1,000/s (FS3) × 128 B = 128 KB/s
Snapshot sampling @100 Hz: 12.8 KB/s
```

Per-tick logging fails on both capacity and bandwidth — Decision 4 is forced, not chosen. The selected policy's sustained rate (~141 KB/s) is three orders of magnitude below the failure mode; the 256 MB ring holds ≈ 30 minutes at the absolute-worst decision rate while core 0 drains at ≥ (OPEN: board eMMC benchmark) MB/s, so occupancy stays bounded. The board's 8 GB eMMC capacity is ample for the ring + export; the remaining question is sustained write bandwidth, which must be measured. No allocation after startup — FS5's no-OOM clause holds by construction.

### 3.2.4.4 Runtime Risk Guard cost bound

Notional: one `umull` + compare ≈ 5–10 cycles. Position: add + two compares ≈ 5 cycles. Rate: timer-delta × fixed-point constant, multiply-shift-saturate ≈ 10 cycles; spend = decrement + compare. In-flight: one counter compare ≈ 1–2 cycles. Total ≪ 100 cycles ≈ 0.13 μs at 766 MHz ≈ 0.5% of the FS2 budget — quantitatively closing Decision 5's "no latency case for hardware risk checks" claim.

---

## 3.2.5 Specification Compliance Summary

|Spec|How the final design satisfies it|Evidence status|
|---|---|---|
|FS2|Busy-poll isolated core + register reads; ≤ ~5 μs software path vs. ~25 μs share (3.2.4.1)|Analytical; pending PMU-instrumented 1,000-tick run + Wireshark|
|FS3|Unbypassable in-thread Risk Guard; four checks + reason-coded log|Pending four-violation injection test|
|FS4|Polling loop structurally unreachable until validated config commits|Pending config-swap restart test|
|FS5|Static allocation, decision-complete + sampled-snapshot ring, async flush (3.2.4.3)|Analytical; pending 10 M-tick stress + export check|
|FS14|Pre-allocated open-order table sized from config; Risk Guard rejects at limit; modeled terminal transitions (Decision 6)|Pending limit-saturation injection test|
|FS11|Core-0 UART renderer off the shared ring|Pending live-session check|
|NFS1 (PS share)|FS2 path is the PS contribution; margin table 3.2.4.1|Analytical|
|NFS4|Linux + watchdog `[TEAM: define]` + no hot-path allocation; fault paths per NFS8; HOLD Mode as safe state|Pending 6.5 h soak|
|NFS8|Config-reject path; fault-coded logging; session continues; PL `DIAG_*` counters surfaced via GP0|Pending malformed-config injection|

# 3.3 EOD Server Pipeline Subsystem

> **Template conventions:** `[TEAM: …]` needs a team decision; `[EVIDENCE: …]` is an analytical target pending simulation/measurement; `[REF-n]` maps to the bibliography. **Scope note:** this subsystem contains two internal data paths that merge before the approval gate. For readability, Final Design Details are split into **3.3.3a (Market Data Path — essential)** and **3.3.3b (Text & Sentiment Path — non-essential)**; they remain one subsystem, matching the block diagram. **Diagram naming:** stage names follow the block diagram — _Parameter Engineering, Regime Detection, Strategy Reoptimize, LLM Agent, Sentiment Analysis, Backtest & Parameter Sweep, Risk Analysis, Generate JSON Configs, Operator Approval_. `[TEAM: keep 3.3.x headings and diagram labels in lockstep, same as 3.1/3.2.]` All numeric analysis in 3.3.4 is derivable on paper today (dataset-size arithmetic, iteration-count budgets, complexity bounds, inequality proofs) — no code required.

---

## 3.3.1 Overview and Specification Mapping

The EOD (End-of-Day) Server Pipeline is the adaptation layer of AQTA — the component that makes the system _Adaptive_ rather than a fixed-strategy appliance. It runs on a host server, entirely off the intraday critical path, and closes the loop between one trading session and the next: it ingests the session history exported by the PS (interface 6) together with historical daily OHLCV data, classifies the next trading day's market regime (FS6), re-optimizes the parameters of the strategy assigned to that regime by exhaustively backtesting a bounded parameter grid (FS7), optionally adjusts the risk envelope using sentiment extracted from unstructured text sources (FS9/FS10), assembles the result into a candidate JSON configuration, and presents it to a human operator whose explicit approval is the only path by which any configuration can reach the live system (FS8, via interface 8 into the PS Config Loader of 3.2.3.4).  
EOD 服务器处理流程是 AQTA 系统的适配层——它使得系统具有自适应能力，而非仅仅遵循固定策略。该流程在主机服务器上运行，完全独立于当天的关键交易流程，负责连接每个交易时段：它接收由 PS 接口 6 输出的交易历史数据以及每日价格区间等历史数据，判断下一个交易日的市场状况，通过全面测试有限参数的策略来重新优化该市场状况下的策略参数设置（FS7），还可以根据从非结构化文本中提取的情绪信息来调整风险水平（FS9/FS10）。最后，将计算结果整理成 JSON 格式的配置文件，然后将其提交给人工操作员审批。只有获得人工操作员的明确批准后，该配置才能被应用到实际系统中（FS8，通过接口 8 与 3.2.3.4 版本中的 PS 配置加载器进行交互）。

The subsystem completes a deliberate three-tier latency/flexibility hierarchy established in 3.1 and 3.2. The PL owns what must be deterministic at nanosecond scale and never changes intraday; the PS owns what must decide in microseconds but be _reconfigurable_ nightly; the EOD server owns what may take minutes but must be _rewritable_ — the analytics, the parameter values, and the judgment about what tomorrow's market looks like. Each tier trades three or more orders of magnitude of latency for a qualitative gain in flexibility, and the interfaces between tiers (register bank at PL/PS; JSON config at PS/EOD) are each designed so the slower tier can never perturb the faster one mid-session. On the EOD tier the binding constraint is no longer latency at all — NFS5 grants 30 minutes — but **correctness, reproducibility, and auditability**: FS7 demands bit-identical re-runs, and FS8 demands that a human can understand and veto every output. Those two properties, not throughput, drive every design decision below.  
该子系统实现了在 3.1 和 3.2 中定义的三层延迟/灵活性层次结构。PL 层负责那些需要在纳秒级别进行确定性决策的任务，这些决策在一天之内不会发生变化；PS 层负责那些需要在微秒级别做出决策的任务，但这些决策可以每晚进行重新配置；EOD 服务器则负责那些可能需要几分钟时间才能完成的任务，但这些任务是可以重新执行的——比如数据分析、参数值设定以及对于明天市场走势的判断。每一层之间的延迟都相差三个数量级，但这样的设计能够提升系统的灵活性。各层之间的接口设计使得较慢的层在会话过程中不会干扰较快的层。在 EOD 层，约束不再仅仅是延迟问题——NFS5 规定的最大延迟为 30 分钟——而是正确性、可重现性和可审计性：FS7 要求每次运行结果必须完全相同，而 FS8 则要求人类能够理解并否决每一个输出结果。那两个属性，而非吞吐量，才是所有设计决策的核心依据。

This subsystem is directly responsible for the following specifications:  
这个子系统直接负责以下规范的实施：

|Spec  规格/参数|Role of EOD subsystem  <br>EOD 子系统的作用|
|---|---|
|**FS6**|Sole owner: classify the next trading day's regime into ≥ 3 distinguishable states from daily market data.  <br>唯一所有者：根据每日市场数据，将下一个交易日的状态划分为至少 3 种不同的状态。|
|**FS7**|Sole owner: search ≥ 9 parameter combinations for the regime's strategy and select the metric-maximizing one, with deterministic (bit-identical) output.  <br>唯一所有者：搜索至少 9 种参数组合来寻找最适合该制度的策略，然后选择能最大化相关指标的方案，同时要保证输出结果具有确定性（即结果完全由输入参数决定）。|
|**FS8**|Sole owner of the gate: no configuration reaches the live system without explicit operator approval. (The PS Config Loader in 3.2.3.4 owns the _receiving_ end of the chain of custody.)  <br>大门的唯一所有者：没有任何配置可以在未经操作员批准的情况下直接投入使用。（在 3.2.3.4 版本中，PS 配置加载器拥有监管链的最终控制权。）|
|**FS9 (non-ess.)  FS9（非核心任务）**|Sole owner: ingest ≥ 10 text assets/day over HTTPS and extract structured event records.  <br>唯一所有者：每天通过 HTTPS 渠道接收至少 10 个文本资产，并提取其中的结构化事件记录。|
|**FS10 (non-ess.)  FS10（非核心职位）**|Sole owner: compute a normalized sentiment score in [−1, +1] and use it to adjust next-day position limits.  <br>唯一所有者：计算一个归一化的情感评分，该评分范围为[−1, +1]，并用该评分来调整当天的仓位限制。|
|**FS12 (non-ess.)  FS12（非必需）**|Sole owner: display and log pipeline stage, regime, selected parameters, backtest Sharpe, and approval status as each stage completes.  <br>唯一所有者：在每个阶段完成时，能够显示并记录管道的阶段信息、制度、所选参数、回测结果以及审批状态。|
|**NFS5 (non-ess.)  NFS5（非必需）**|Sole owner: full pipeline (ingestion → classification → optimization → approval prompt) within 30 minutes.  <br>唯一所有者：在 30 分钟内完成整个流程（摄入→分类→优化→审批提示）。|
|**NFS8 (partial)  NFS8（部分内容）**|Owner of server-side fault handling: malformed/missing input data or failed text ingestion must degrade safely (log fault code, emit no config or a neutral adjustment) rather than abort the nightly cycle uncleanly. `[TEAM: NFS7 and NFS8 are currently word-identical in Section 2 — resolve the duplicate before final submission.]`  <br>服务器端错误处理责任的承担者指出：如果遇到输入数据格式错误、缺失数据或文本导入失败等情况，系统必须能够安全地进行处理（记录错误代码，无需调整配置，或进行简单的调整），而不是导致整晚的运行周期中断。 `[TEAM: NFS7 and NFS8 are currently word-identical in Section 2 — resolve the duplicate before final submission.]`|

Upstream dependency: FS5's exported session history (interface 6) and a historical daily OHLCV dataset are the pipeline's inputs. The OHLCV source is pinned to the project's own 3.4 corpus: seed-reproducible simulator sessions aggregated to daily bars (regime-labeled, unlimited volume, zero license cost), anchored by the real LOBSTER AAPL sample day (3.4.4.6 — a freely published official sample), so no external market-data feed or license is required. Downstream contract: the JSON configuration schema of 3.3.3.5, consumed by the PS Config Loader — jointly owned with 3.2, exactly as the register bank table of 3.2.3.1 is jointly owned with 3.1.  
上游依赖关系：FS5 输出的会话历史记录（接口 6）以及历史每日价格数据集，都是该处理流程的输入。这些价格数据的来源是项目自有的 3.4 版本数据集中提供的：可复现的模拟会话被汇总为每日的图表数据（具有特定模式、无限交易量、零许可成本），这些数据以真实的 LOBSTER AAPL 样本日作为基准（3.4.4.6——一个公开可用的官方样本数据），因此无需外部市场数据或许可。下游合约：3.3.3.5 版本的 JSON 配置格式，由 PS 配置加载器处理——该加载器与 3.2 版本的数据共享同一数据源，正如 3.2.3.1 版本的银行记录表与 3.1 版本的数据共享一样。

Figure 3.4 shows the pipeline structure. _(Figure placeholder — reuse the SERVER subgraph of the system block diagram, minus the Console Monitor, which belongs to the PS peripheral group per the final subsystem split. Two arrows require re-annotation, flagged in Decisions 5 and 6 below.)_  
图 3.4 展示了该管道的结构。（图例占位符——复用系统框图中的 SERVER 子图，但去掉了属于 PS 外围组中的 Console Monitor 模块。有两个箭头需要重新标注，具体位置在下面的决定 5 和 6 中有说明。）

---

## 3.3.2 Engineering Design Process  
3.3.2 工程设计流程

Six significant design decisions shaped this subsystem. The recurring theme differs from 3.1/3.2: there, the specs priced in _latency_ and the decisions bought determinism of _timing_; here, the specs price in _reproducibility and human oversight_ and the decisions buy determinism of _results_. Where a rationale is quantitative, the supporting arithmetic appears in 3.3.4.  
六个重要的设计决策塑造了这个子系统。其中的核心思想与 3.1/3.2 中的有所不同：在 3.1/3.2 中，规格的考量集中在延迟方面，而决策则确保了时间的确定性；而在本案例中，规格的考量则体现在可重复性以及人类监督方面，决策则确保了结果的确定性。当需要定量论证时，相关的算术计算内容则体现在 3.3.4 中。

### Decision 1 — Execution environment: on-SoC overnight job, compiled host pipeline, or Python host pipeline  
决策 1——执行环境：可以在整块芯片上立即完成的任务，或者采用编译后的主机流程，或是基于 Python 的宿主流程。

|Alternative  替代方案|Description  描述|Outcome  结果|
|---|---|---|
|A. Run EOD on the SoC PS overnight  <br>A. 在夜间对 SoC 的 PS 部分进行运行测试|Reuse the Zynq: core 1 is idle after the session; run the pipeline there.  <br>重新使用 Zynq：在会话结束后，核心 1 会处于空闲状态；可以将处理流程运行到那里。|**Rejected.** Three independent grounds. (1) Capability: a 766 MHz Cortex-A9 with 1 GB shared DDR3 and no scientific-computing ecosystem turns a 30-minute host job into a porting project (cross-compiling or forgoing NumPy/pandas-class tooling). (2) Architecture: the SoC is deliberately a minimal trading appliance; adding an analytics stack to it grows the NFS4 attack surface (more processes, more memory pressure, more failure modes on the machine that must survive 6.5 h sessions). (3) FS8 topology: the approval gate requires that the config _travels_ from an operator-controlled machine to the trading device — collapsing them onto one board makes the "not loaded until approved" boundary a software convention rather than a physical link, weakening the verification argument.  <br>被拒绝。有三个独立的反对理由。(1) 性能能力：这款设备拥有 766 MHz 的 Cortex-A9 处理器，1 GB 的共享 DDR3 内存，且没有科学计算相关的功能。这样的性能足以完成 30 分钟的主机端任务，将其用于移植项目（无需进行交叉编译或依赖 NumPy/pandas 类工具）。(2) 架构设计：该 SoC 被设计为最简单的交易设备；如果为其添加分析功能，则会增加 NFS4 攻击面的风险（更多的进程、更大的内存压力，以及需要持续运行 6.5 小时会话时的更多故障模式）。(3) FS8 拓扑结构：审批流程要求配置信息从操作员控制的设备传输到交易设备中——将它们集成到同一块板上会使“仅在获得批准后才加载”这一限制成为软件层面的约定，而非物理连接，从而削弱了验证的说服力。|
|B. Compiled host pipeline (C++/Rust)  <br>B. 编译后的主机编程接口（使用 C++/Rust 语言编写）|Native pipeline on the host server for performance.  <br>在主机服务器上采用了原生管道机制，以提升性能。|**Rejected.** NFS5 grants 30 minutes; the arithmetic in 3.3.4.1 shows the entire essential pipeline needs single-digit minutes even in interpreted Python. Compiled performance optimizes a cost that does not exist, while multiplying development and iteration cost on the one subsystem whose formulas the team most expects to revise.  <br>被拒绝。在 NFS5 中，系统运行时间为 30 分钟；而根据 3.3.4.1 中的计算结果显示，即使在解释型 Python 环境下，整个核心流程的运行时间也只需要几分钟。不过，编译后的性能优化会带来额外的成本，同时还会增加开发和迭代的成本——而这一成本正是团队最希望改变的方面。|
|C. Python 3 + scientific stack on host server (selected)  <br>C. 在主机服务器上使用 Python 3 以及科学计算库（可选）|pandas/NumPy for data handling; standard library for orchestration; the strategy kernel handled per Decision 4.  <br>用于数据处理的 pandas/NumPy 库；用于协调操作的标准库；策略核心模块根据每个决策进行处理。|**Selected.** Highest-productivity environment for a data pipeline; every stage is testable with plain pytest on fixture CSVs; NFS5's budget makes its performance profile irrelevant (3.3.4.1).  <br>已选中。这是数据管道的最高生产力环境；每个阶段都可以通过使用简单的 pytest 和基于固定文件的 CSV 数据进行测试；NFS5 的预算使得其性能特性变得不那么重要了（3.3.4.1）。|

**Orchestration corollary.** A workflow framework (Airflow/Prefect-class DAG scheduler) was considered and rejected without a full trade study: the pipeline is a strictly linear-with-one-merge DAG executed once nightly on one machine, and FS12's requirement — a logged status line per stage transition — is satisfied by a sequential staged script with a `run_stage()` wrapper that timestamps entry/exit and writes the FS12 record. A scheduler adds an always-on service, a database, and a failure domain to deliver features (distributed workers, retry policies, backfills) the specifications never ask for. This is the same reasoning shape as 3.2 Decision 3: infrastructure must earn its complexity, and here it cannot.  
编排推论：我们考虑了一个工作流程框架（Airflow/Prefect-class DAG 调度器），但并未进行全面的评估就放弃了该方案。该流程是一个严格线性的单合并 DAG 结构，每晚在一台机器上执行一次。而 FS12 的要求——每阶段执行后都需要记录状态信息——可以通过一个顺序化的脚本来实现，同时使用 `run_stage()` 包装器来记录进入和退出时间，从而生成 FS12 记录。这种调度器引入了持续运行的服务、数据库以及故障恢复机制，从而提供了一些规格要求中并未包含的功能（如分布式工作节点、重试策略、回补操作等）。这种推理方式与 3.2 节中的决策 3 是一致的：基础设施的复杂性必须得到合理证明，而在这里，显然无法实现这种复杂性。

### Decision 2 — Regime classifier (FS6): rule-based thresholds, k-means clustering, or Hidden Markov Model  
决策 2——机制分类器（FS6）：基于规则的阈值设定、K 均值聚类或隐马尔可夫模型

This is the subsystem's central algorithmic decision. The spec context matters more than the algorithm menu: FS6 requires **≥ 3 distinguishable states**, FS7 requires the downstream consumer to be **bit-identical on re-run**, and FS8 requires a **human operator to audit** the output nightly. The classifier's job in AQTA is _routing_ — selecting which of the three pre-built strategies (3.2.3.2: Trending→Momentum, Ranging→Mean Reversion, Volatile→Defensive) runs tomorrow — not alpha generation. The evaluation criteria and weights encode that: reproducibility and auditability dominate classification fidelity.  
这是子系统的核心算法决策。规范上下文的重要性高于算法选项：FS6 要求至少有 3 种可区分的状态；FS7 要求下游消费者在重新运行时具有相同的比特值；FS8 则要求人工操作员每晚对输出结果进行审核。在 AQTA 中，分类器的职责是选择明天执行哪三种预构建策略之一（3.2.3.2：趋势型→动量型，区间型→均值回归型，波动型→防御型）——而不是生成阿尔法值。评估标准和权重设定表明：可重复性以及可审核性比分类的精确性更为重要。

|Criterion (weight)  标准（权重）|Rule-based two-feature thresholds (selected)  <br>基于规则的双特征阈值（可选）|k-means clustering (k=3)  <br>K 均值聚类算法（k=3）|Gaussian HMM (3 states)  <br>高斯隐马尔可夫模型（3 个状态）|
|---|---|---|---|
|Determinism & reproducibility (30%)  <br>决定论与可重复性（30%）|Deterministic by construction — pure function of the input window  <br>根据构造方式决定结果——输入窗口的内容决定了最终的产物，完全不受其他因素影响。|Deterministic only with fixed seed + fixed init; silent library-version sensitivity  <br>仅适用于具有固定种子值的情况，且初始化值也是固定的；同时忽略了库版本的自动检测功能。|EM fit (Baum-Welch) is init-sensitive; multi-restart practice is explicitly stochastic  <br>EM 拟合模型（Baum-Welch 方法）对初始值非常敏感；多次重启训练过程本质上是一种随机过程。|
|Operator auditability for FS8 (25%)  <br>FS8 的操作员可审计性为 25%|Full — the operator can verify "vol above its 75th percentile ⇒ Volatile" against a chart in seconds  <br>完全——操作员可以在几秒内通过查看图表来确认“挥发性高于其第 75 百分位的物质”这一结果。|Weak — centroid coordinates are not human-meaningful; labels can permute between runs  <br>较弱——质心坐标并不具有人类可理解的含义；标签在多次运行之间是可以发生变化的。|Weak — state posteriors are not explainable to a non-specialist reviewer; states need post-hoc labeling  <br>糟糕——这些状态描述对于非专业读者来说是无法理解的；各州需要事后进行标注说明。|
|Implementation + verification cost, given team capability (25%)  <br>实施与验证的成本，取决于团队的能力（25%）|Days: two features, three comparisons, exhaustive unit-testable  <br>天数：两个特点，三个对比，充分的可测试性设计|Moderate: scikit-learn dependency + label-to-regime mapping logic  <br>中等难度：基于 scikit-learn 的依赖关系处理机制，同时包含标签到规则映射的逻辑处理|High: hmmlearn dependency, convergence handling, degenerate-fit detection — specialist knowledge the team does not have and the marks do not reward  <br>高：嗯，学习依赖性、收敛性处理、退化拟合检测——这些都是团队不具备的专业知识领域，而且相关的评分也不会给予相应的奖励。|
|Classification fidelity (20%)  <br>分类准确性（20%）|Adequate — captures the vol/trend structure the three strategies are defined by  <br>“适当”——描述了这三种策略所依赖的节奏/趋势结构。|Potentially better cluster geometry  <br>可能具有更优的簇几何结构|Best-in-literature for latent regime persistence [15]  <br>关于隐性政权持续性的最佳研究[15]|
|**Weighted result (1–5 scale)  <br>加权评分结果（1-5 分制）**|**4.60 — Selected  4.60 — 精选内容**|2.95|2.35|

_(Scoring: 1–5 per criterion — cost-type criteria score higher when the cost is lower — then weighted: rule-based = 0.30×5 + 0.25×5 + 0.25×5 + 0.20×3 = 4.60; k-means = 0.30×3 + 0.25×2 + 0.25×3 + 0.20×4 = 2.95; HMM = 0.30×2 + 0.25×2 + 0.25×1 + 0.20×5 = 2.35.)  
评分标准：每个指标满分 1 至 5 分——当成本较低时，成本类型的指标得分更高。然后进行加权计算：基于规则的算法得分为 0.30×5 + 0.25×5 + 0.25×5 + 0.20×3 = 4.60 分；基于 K 均值算法的得分为 0.30×3 + 0.25×2 + 0.25×3 + 0.20×4 = 2.95 分；基于 HMM 算法的得分为 0.30×2 + 0.25×2 + 0.25×1 + 0.20×5 = 2.35 分。_

The decisive observation: **the two rejected alternatives buy fidelity the specifications cannot measure, at the cost of the two properties the specifications do measure.** FS6's verification procedure checks only that ≥ 3 distinct regimes appear over 6 months of data; FS7's checks bit-identical output; FS8's checks that a human approved. A threshold classifier maximizes the second and third and satisfies the first _by construction_ (shown quantitatively in 3.3.4.3, where percentile-based thresholds make a degenerate single-regime outcome impossible on the verification dataset). This is the quant-engineering framing of the whole project applied locally: the deliverable is a working, auditable adaptation loop, not a novel classifier.  
关键的观察是：这两个被排除的替代方案无法衡量那些确实可以被测量的特性。FS6 的验证程序仅检查在 6 个月的数据中是否出现了至少 3 种不同的模式；FS7 则检查输出结果是否完全相同；FS8 则检查该过程是否经过了人工审核。阈值分类器在构造上能够最大化第二和第三个特性，同时满足第一个特性（这一点在 3.3.4.3 中有定量展示，其中基于百分位的阈值使得在验证数据集上出现单一模式的情况变得不可能）。这就是整个项目的量化工程框架：最终目标是实现一个可运行的、可审计的适应循环，而不是一个全新的分类器。

**Threshold calibration sub-decision.** Fixed absolute thresholds (e.g., "annualized vol > 25% ⇒ Volatile") were rejected because they silently degenerate on any symbol or period whose vol never crosses the constant — FS6's verification would then fail for data reasons, not design reasons. The selected scheme sets thresholds at **percentiles of the trailing calibration window** (working empirical figures, confirmed: 75th percentile of realized vol; 60th percentile of |trend strength| — both adjustable from the pipeline config), making the classifier self-calibrating per symbol and guaranteeing non-empty regime occupancy on the very dataset FS6 is verified against (3.3.4.3).  
阈值校准的子决策部分。固定的绝对阈值（例如，“年化成交量超过 25%时视为易挥发”）被排除在外，因为这样的阈值在任何符号或时期中，当成交量从未超过该阈值时，都会导致系统失效。FS6 的验证会因为数据原因而无法通过，而非因为系统设计问题。所选择的方案是将阈值设定为最近一次校准窗口中各个百分位数的值（根据经验数据得出：实现成交量的第 75 百分位数；|趋势强度|的第 60 百分位数——这两个阈值都可以从配置文件中进行调整）。这样，分类器可以针对每个符号进行自我校准，并且可以确保 FS6 所验证的数据集上不会出现空值情况（3.3.4.3 节）。

### Decision 3 — Parameter search (FS7): exhaustive grid, random search, or Bayesian optimization  
决策 3——参数搜索（FS7）：穷举法、随机搜索还是贝叶斯优化

|Alternative  替代方案|Description  描述|Outcome  结果|
|---|---|---|
|Bayesian optimization (GP/TPE)  <br>贝叶斯优化（GP/TPE）|Sample-efficient search of expensive objective functions.  <br>对昂贵目标函数进行高效的搜索。|**Rejected.** Sample efficiency is valuable when evaluations are expensive; 3.3.4.1 shows the _entire grid_ evaluates in minutes. The method is stochastic by nature (acquisition sampling), directly hostile to FS7's bit-identical requirement, and imports a heavyweight dependency to optimize a cost that does not exist.  <br>被拒绝。在评估成本较高的情况下，样本效率确实很有价值；3.3.4.1 节展示了整个网格在几分钟之内就能完成评估的过程。这种方法本质上是随机的（采用采集样本的方式），这直接违背了 FS7 的位相同要求。此外，该方法还引入了一个复杂的优化过程，以降低成本，但实际上这种成本并不存在。|
|Random search  随机搜索|Uniform sampling of the parameter space.  <br>对参数空间进行均匀采样。|**Rejected.** Deterministic only under seed discipline that must then be defended in verification; offers no benefit over the grid at this scale — its literature advantage appears in high-dimensional spaces [16], and our space is 3-dimensional.  <br>被拒绝。仅适用于确定性约束的情况，而这一约束必须在验证过程中得到支持；在如此大规模的网格环境中，这种方式并没有任何优势——其文献优势体现在高维空间中[16]，而我们的空间是三维的。|
|Exhaustive grid search (selected)  <br>全面的网格搜索（精选方案）|Enumerate every combination in a fixed, documented order; evaluate each with the backtest kernel; select the maximizer under a total-order tie-break.  <br>按照固定的、有序的排列方式，列出所有的组合方案；使用回测内核对每个方案进行评估；在多个方案票数相同的情况下，选择效果最佳的方案。|**Selected.** Determinism by construction: fixed enumeration order + sequential evaluation + deterministic kernel (Decision 4) + total-order tie-breaking (3.3.3a.3) means identical input bytes produce identical output bytes — FS7's verification procedure passes by design, not by discipline. Exhaustiveness also strengthens FS8: the operator report can show the _complete_ result table, not a sampled trace.  <br>已选中。构建式确定性：固定的枚举顺序、顺序评估、确定性核心逻辑（决策 4）、以及全序式平局处理机制（3.3.3a.3）意味着相同的输入字节会产生相同的输出字节——FS7 的验证程序是出于设计目的而存在的，而非基于某种规则。此外，全面性还增强了 FS8 的有效性：操作员报告能够展示完整的结果表格，而非仅展示样本数据。|

The one real hazard of a maximizing grid search — overfitting the trailing window — is acknowledged rather than hidden: mitigations are (a) the small, coarse grid itself (a 27-point grid cannot fit noise the way a continuous optimizer can), (b) the operator approval gate, whose report displays the full sweep table so a knife-edge maximum is visible, and (c) the Defensive regime and HOLD mode as structural backstops. A walk-forward evaluation scheme was considered as a stronger mitigation and rejected for prototype scope; it is the natural first extension. Confirmed: walk-forward is deferred — single trailing-window in-sample selection is the prototype behavior.  
在最大化网格搜索时，一个真正的风险就是过拟合后续的搜索范围。不过，有一些方法可以应对这一挑战：(a) 使用较小的、粗糙的网格结构——一个由 27 个点的网格无法像连续优化器那样处理噪声；(b) 使用操作员审核机制，其报告会显示完整的搜索结果，从而可以清晰地看到最大值；(c) 使用防御性策略和暂停模式作为紧急应对手段。此外，还考虑了逐步评估的方法作为更强的解决方案，但该方法被排除在原型版本之外；因为逐步评估是自然而然的首次扩展方式。确认：逐步评估暂时搁置——在样本数据范围内选择单个后续窗口即可作为原型行为。

### Decision 4 — Backtest kernel: vectorized library, event-driven framework, or parity-ported custom loop  
决策 4——回测内核：采用向量化库、事件驱动框架，或平行移植的自定义循环。

This decision contains the subsystem's most consequential correctness argument, and it inverts the team's default preference for off-the-shelf components — deliberately and for one specific reason.  
这个决策包含了关于该子系统最关键的准确性依据，并且打破了团队对现成组件的偏好——这种偏好是出于某种特定原因而产生的。

|Alternative  替代方案|Description  描述|Outcome  结果|
|---|---|---|
|Vectorized backtest library (vectorbt-class)  <br>向量化回测库（vectorbt-class）|Strategies re-expressed as vectorized signal arrays; very fast sweeps.  <br>这些策略被转化为向量化信号阵列的形式；从而实现非常快速的扫描操作。|**Rejected for the kernel.** Requires _re-implementing_ each strategy in vectorized form, creating two parallel definitions of the same strategy — one in C on the PS (integer, event-driven), one in NumPy on the server (float, array-form). Any divergence (rounding, boundary conditions, lookback indexing) silently invalidates the central promise of the EOD loop: that the parameters selected offline describe the behavior of the code that trades.  <br>该策略被拒绝用于内核模块。需要重新实现每种策略的向量化版本，为同一种策略创建两个并行版本的定义——一个用 C 语言在 PS 端实现（适用于整数类型、事件驱动模式），另一个用 NumPy 在服务器端实现（适用于浮点类型、数组形式）。任何差异化的处理方式（如四舍五入、边界条件处理、回查索引等）都会使 EOD 循环的核心承诺失效：即离线选择的参数能够准确描述交易代码的行为。|
|Event-driven framework (backtrader-class)  <br>事件驱动框架（BackTrader 类）|Closer execution semantics; strategies as callback classes.  <br>更紧密的执行语义；将策略作为回调类来处理。|**Rejected for the kernel.** Same dual-implementation problem (framework-native indicators are float-based), plus a large dependency whose internal fill/accounting model would need auditing to defend FS7 determinism.  <br>被拒绝用于内核模块。同样存在双实现问题（框架内使用的指标是基于浮点的），此外还存在一个严重的依赖性问题，其内部的填充/会计模型需要审核，以确保符合 FS7 的确定性要求。|
|**Parity-ported custom loop (selected)  <br>奇偶校验传输的自定义循环（已选择）**|A thin (~100-line) replay loop that feeds recorded snapshots through **line-by-line ports of the exact PS strategy functions** — same integer-cents arithmetic, same lookback ring, same thresholds — and tracks position/P&L. Libraries (pandas/NumPy) are used _around_ the kernel for data loading and metric aggregation, not inside it.  <br>一个简洁的循环播放机制（约 100 行长度），它将录制的快照数据通过逐行处理的方式传入系统。所有计算都遵循相同的 PS 策略，包括整数运算、相同的回放周期以及相同的阈值设定。系统还会跟踪位置收益情况。数据处理和指标汇总工作都在内核外部进行，使用 pandas/NumPy 库来完成。|**Selected.** The 3.2.3.2 commitment to integer-only strategy arithmetic was made precisely to enable this: an integer decision function is portable across C and Python with bit-identical outputs, because no floating-point rounding or evaluation-order semantics are involved. The backtest therefore does not _approximate_ the live system — it _replays_ it.  <br>已选中。选择采用仅支持整数运算的策略，正是为了实现这一目的：由于不涉及浮点运算或评估顺序的语义处理，这种整数决策函数在 C 语言和 Python 中都能保持相同的输出结果。因此，回测并不会对实际系统进行近似模拟——而是直接再现实际系统的运行情况。|

**Why this doesn't contradict the "prefer existing libraries" principle.** The principle applies where the component is commodity infrastructure (data loading, HTTP, JSON, metric arithmetic — all off-the-shelf here). The backtest _kernel_ is not commodity: its defining requirement is decision parity with our own PS code, a property no external library can supply by definition. The cost of the custom choice is speed — a pure-Python event loop is orders of magnitude slower than vectorized NumPy — and 3.3.4.1 shows that cost is affordable inside NFS5 with a ≥ 3× margin: **slow-but-identical beats fast-but-divergent when the budget makes slow free.** Cross-validation between the kernel and the PS engine (same recorded input, byte-compared decision sequences) is itself a planned verification artifact. `[EVIDENCE: kernel-vs-PS decision-sequence byte comparison on a recorded session.]`  
为什么这并不与“优先使用现有库”的原则相矛盾呢？该原则适用于那些属于基础基础设施的场景（如数据加载、HTTP 通信、JSON 处理、度量计算等，这些功能都是现成的）。而回测内核则不属于基础基础设施范畴：它的核心要求是与我们自己的 PS 代码实现完全一致，而这一特性是任何外部库都无法提供的。不过，这种定制选择的成本在于速度——纯 Python 事件循环的速度比向量化处理的 NumPy 要慢几个数量级。而 3.3.4.1 表明，在 NFS5 环境下，这种成本是可以接受的，而且成本与收益之间有着至少 3 倍的差距：慢但稳定优于快但不稳定。内核与 PS 引擎之间的交叉验证（使用相同的输入数据，比较决策序列的字节码）本身也是一种有计划的验证手段。 `[EVIDENCE: kernel-vs-PS decision-sequence byte comparison on a recorded session.]`

**Backtest data source.** The kernel replays the **snapshot stream exported by the Execution Logger** (FS5, interface 6) — the sampled top-of-book records the live system actually observed — rather than synthetic bars. This closes the loop with zero format invention: the system generates its own backtest data in its own schema, and the parameter sweep evaluates strategies on exactly the data distribution the deployed strategy will see. Bootstrap case (no live sessions yet): replay sessions generated by the Exchange Simulator (3.4) `[TEAM: confirm bootstrap dataset — N simulator sessions recorded before first live run]`. The daily-OHLCV dataset is used only by the regime path (FS6 is explicitly specified on daily data), not by the sweep.  
回测数据来源。该内核会重新播放由执行日志器（FS5，接口 6）导出的快照流——这些采样的数据实际上代表了实时系统的真实表现，而非合成的数据。这样就能实现零格式的创新：系统使用自己的数据结构生成回测数据，而参数扫描则基于实际使用的数据分布来评估策略效果。对于尚未开启实时会话的情况，则使用由交换模拟器（3.4）生成的会话数据。每日的 OHLCV 数据集仅被用于制度路径的评估（在每日数据上明确指定了 FS6），而参数扫描则不会使用该数据集。

### Decision 5 — Text & Sentiment Path architecture (FS9/FS10): where the LLM belongs, and the determinism boundary  
决策 5——文本与情感路径架构（FS9/FS10）：LLM 所处的领域，以及决定论的边界

The non-essential path raises a design tension: an LLM is the strongest available tool for FS9's actual problem (extracting structured records from heterogeneous unstructured sources — HTML news, social posts, PDF reports), but LLM outputs are non-deterministic and externally hosted — properties that must not contaminate FS7's bit-identical guarantee or FS8's audit chain. The design resolves this by splitting the path at a **determinism boundary** and choosing a different tool on each side.  
这条非必要的路径引发了设计上的紧张感：尽管大型语言模型是处理 FS9 所面临的实际问题的最佳工具（从异构非结构化数据源中提取结构化信息——如 HTML 新闻、社交媒体帖子、PDF 报告等），但大型语言模型的输出结果并不确定性，而且需要外部托管——这些特性可能会破坏 FS7 的确定性保证以及 FS8 的审计流程。为了解决这个问题，设计上在确定性边界处将路径分割开来，并在每一侧选择不同的工具来进行处理。

**Stage 1 — Extraction (FS9): LLM agent, selected for the messy side.** Alternatives: hand-written per-source parsers (rejected: one parser per source format, brittle against layout changes, and PDF report extraction alone is a project), classical NLP/NER pipelines (rejected: comparable integration cost to FinBERT below but solves only entity tagging, not headline/relevance extraction from arbitrary formats). The LLM agent ingests each asset over HTTPS and emits one structured event record (headline, ticker, timestamp, source — FS9's exact field list). Every emitted record is **logged verbatim**; everything downstream operates only on logged records. Non-determinism therefore stops at the boundary: re-running the pipeline _from the logged records_ is fully deterministic, which is the precise sense in which FS7's re-run verification is defined. `[TEAM: LLM provider/API vs local model; FS9's verification uses a mocked web server, so the demo does not depend on live source availability.]`  
第一阶段——提取（FS9）：使用 LLM 代理来处理复杂任务。其他方案包括手动根据源文件进行解析（被否决：每种源文件格式需要单独解析器，且对布局变化的适应性较差；仅进行 PDF 报告提取也是不可行的），或者使用传统的自然语言处理/命名实体识别流程（被否决：其集成成本与 FinBERT 相当，但只能处理实体标签的识别，无法从任意格式中提取标题和相关信息）。LLM 代理通过 HTTPS 方式获取各资源文件，并生成结构化的记录（包括标题、股票代码、时间戳、来源信息——这正是 FS9 所需的字段列表）。所有生成的记录都会被详细记录下来；后续处理操作仅基于这些记录进行。因此，非确定性处理仅限于此阶段：从已记录的记录重新执行流程是完全确定的，而这正是 FS7 重新执行验证机制的核心所在。 `[TEAM: LLM provider/API vs local model; FS9's verification uses a mocked web server, so the demo does not depend on live source availability.]`

**Stage 2 — Scoring (FS10): deterministic local model, selected for the auditable side.  
第二阶段——评分（FS10）：采用确定性局部模型，该模型被选中用于可审计的方面。**

|Criterion (weight)  标准（权重）|Lexicon (VADER-class)  词汇表（VADER 级）|FinBERT (local inference, selected)  <br>FinBERT（本地推理，选择性处理）|LLM-scored  LLM 评分|
|---|---|---|---|
|Determinism/reproducibility (30%)  <br>确定性/可重复性（30%）|Full  全部|Full — fixed weights, fixed tokenizer, single-threaded CPU inference  <br>完全版本——采用固定的权重设置，固定的分词器，单线程的 CPU 推理方式|None without vendor-side guarantees  <br>没有哪种解决方案是可以脱离服务器端保障而实现的。|
|Financial-domain validity (25%)  <br>财务领域有效性（25%）|Weak — general-domain lexicon misreads financial polarity ("beats expectations")  <br>评价为“弱”——通用领域词汇表误判了金融领域的极性描述（“优于预期”）|Strong — finance-domain fine-tuned [17]  <br>强效——金融领域的微调版本 [17]|Strong  强悍的|
|Integration + verification cost (25%)  <br>整合成本 + 验证成本（25%）|Trivial  微不足道的事物|Low — one pip dependency, one forward pass per record; FS10's pre-labeled reference-set test applies directly  <br>低复杂度——仅一个 pip 的依赖性，每个记录进行一次前向计算；FS10 的预标记参考集测试可以直接应用。|API handling, rate limits, cost accounting  <br>API 处理、速率限制、成本核算|
|Operating cost/availability (20%)  <br>运营成本/可用性（20%）|None  无|None after model download; fully offline  <br>在下载模型之后，无需任何操作；完全处于离线状态|Per-call cost; external availability risk on the nightly path  <br>每通话费用；夜间路径上的外部可用性风险|
|**Weighted result (1–5 scale)  <br>加权评分结果（1-5 分制）**|4.25|**4.75 — Selected  4.75 — 已选中的项**|2.45|

_(Scoring: 1–5 per criterion, weighted: lexicon = 0.30×5 + 0.25×2 + 0.25×5 + 0.20×5 = 4.25; FinBERT = 0.30×5 + 0.25×5 + 0.25×4 + 0.20×5 = 4.75; LLM-scored = 0.30×1 + 0.25×5 + 0.25×2 + 0.20×2 = 2.45. The lexicon runs FinBERT close on cost but loses exactly where FS10's correct-polarity verification bites — domain validity.)  
评分标准：每个指标评分为 1-5 分，加权后计算：词汇部分得分为 0.30×5 + 0.25×2 + 0.25×5 + 0.20×5 = 4.25；FinBERT 部分得分为 0.30×5 + 0.25×5 + 0.25×4 + 0.20×5 = 4.75；LLM 评分部分得分为 0.30×1 + 0.25×5 + 0.25×2 + 0.20×2 = 2.45。虽然词汇部分的评分接近 FinBERT，但在领域适用性方面，词汇部分的表现不如 FS10 的正确极性验证功能。——领域适用性部分。_

FinBERT's class probabilities map directly onto FS10's required range: `score = P(positive) − P(negative) ∈ [−1, +1]` with polarity built in — no ad-hoc normalization to defend. Per-asset scores aggregate to a daily score by simple mean (confirmed — recency weighting adds a parameter the prototype has no evidence to calibrate), plus an `abnormal_event_flag` when any single record's |score| exceeds θ_abn = 0.8 (working empirical value, loaded from the pipeline config).  
FinBERT 的类别概率映射直接对应于 FS10 所需的范围： `score = P(positive) − P(negative) ∈ [−1, +1]` 。同时，该映射还包含了极性信息——无需额外的归一化处理即可实现。每个资产的相关评分通过简单平均值汇总为每日总评分（已确认：近期性权重分配是一个需要配置的参数，不过原型系统目前还没有相关的证据来证明这一点）。此外，当任何一条记录的|score|超过θ_abn = 0.8 时，还会额外加上 `abnormal_event_flag` 的权重（这是一个基于实际经验得出的数值，来自管道配置文件）。

**Coupling into the essential path — risk-tightening-only, by proof.** The sentiment output enters the **Risk Analysis** stage as a position-limit scalar, under a monotonicity constraint proven in 3.3.4.4: the adjusted limit satisfies `L(s) ≤ L_base` for every possible score `s`, with equality for all `s ≥ 0`. Sentiment can therefore only _shrink_ the risk envelope below the FS3 ceilings, never expand it, and never touches the optimization objective or strategy selection. Consequently the non-essential path is **incapable of harming the essential system**: its total failure (no assets, API down, model missing) degrades to `s = 0` ⇒ no adjustment ⇒ the essential pipeline's output is byte-identical to a run with the path disabled. This is the same structural-safety argument style as 3.2's "malformed egress is impossible by construction." _(Diagram note: the block diagram's `PATH_TXT → BACKTEST` arrow should be re-annotated to target Risk Analysis — sentiment does not feed the backtest objective. `[TEAM: confirm with diagram owner, same as the HOLD-arrow fix in 3.2.3.6.]`)_  
只通过风险紧缩这一途径来推进核心流程——这是经过验证的解决方案。情感输出作为位置限制标量进入风险分析阶段，同时遵循 3.3.4.4 中规定的单调性约束：调整后的限制条件使得对于每一个可能的得分 `s` ，调整后的限制值都满足 `L(s) ≤ L_base` ，而当所有 `s ≥ 0` 相同时，限制值等于 `L(s) ≤ L_base` 。因此，情感因素只能将风险范围降低到 FS3 的上限以下，绝不可能将其扩大，也绝不会影响到优化目标或策略选择。这样一来，非核心路径就无法对核心系统造成任何损害：如果整个系统崩溃（资产丢失、API 失效、模型失效），那么调整后的输出结果将与禁用该路径时的输出完全相同。这种结构安全性论证方式与 3.2 节中“畸形退出行为在构造上是不可能的”这一论点是一致的。（图表说明：该框图中的 `PATH_TXT → BACKTEST` 箭头应重新标注为指向“风险分析”——因为情绪并不会影响回测的目标。 `[TEAM: confirm with diagram owner, same as the HOLD-arrow fix in 3.2.3.6.]` ）

### Decision 6 — Approval gate and configuration chain of custody (FS8)  
决议 6——批准关口与配置管理链（FS8）

|Alternative  替代方案|Description  描述|Outcome  结果|
|---|---|---|
|Procedural gate  程序性门槛|Pipeline writes the config; operator manually copies it to the SoC when satisfied.  <br>管道系统负责编写配置文件；当满足要求时，操作员会手动将这些文件复制到系统级控制器中。|**Rejected.** FS8's verification must show the config _cannot_ reach the SoC unapproved; a procedure is a promise, not a mechanism — nothing distinguishes an approved file from an unapproved one after the fact.  <br>被拒绝。FS8 的验证结果表明，该配置确实无法连接到 SoC 上；流程本身只是一种承诺，而非实际可行的机制——在事情发生之后，无法区分什么是经过批准的文件，什么是未经批准的文件。|
|Approval flag in the config  <br>配置中的审批标志|Pipeline sets `approved: true` after a y/n prompt; transmission code checks the flag.  <br>管道系统会在 y/n 提示后设置 `approved: true` ；传输代码则会检查该标志。|**Rejected.** The flag is data, forgeable by any bug or manual edit between generation and load; the PS cannot distinguish a genuinely approved config from one with the bit flipped.  <br>被拒绝。该标志属于数据类型，任何漏洞或人为操作都可以在生成和加载过程中对其进行修改。PS 系统无法区分真正经过批准的配置与那些配置位被颠倒的无效配置。|
|**Hash-bound approval + gated transmission (selected)  <br>基于哈希值限制的审批机制，以及经过筛选后的数据传输**|The pipeline computes SHA-256 over the **canonically serialized** config payload (canonicalization frozen: UTF-8; keys sorted lexicographically; compact separators with no insignificant whitespace; integers in plain decimal; float metrics pre-rounded to fixed 6-decimal strings before serialization — i.e., Python `json.dumps(payload, sort_keys=True, separators=(',',':'))` over an int/string-only payload. These rules are part of the interface contract; any revision bumps the provenance `pipeline_version` field). The operator is shown the FS12 report (regime, sweep table, selected parameters, Sharpe, sentiment adjustment) plus the hash, and approves interactively; approval appends an approval block (operator ID, timestamp, payload hash). Only then does control flow reach the transmission call — **the network send is inside the approval-gated branch**, so an unapproved config is unreachable code, the same structural argument as FS4's in 3.2.3.4. On the receiving end, the PS Config Loader independently recomputes the payload hash and refuses any config whose hash does not match its approval block (the "operator-approval hash" validation already specified in 3.2.3.4).  <br>该管道会对规范化的配置负载进行 SHA-256 哈希计算（规范化处理已冻结：使用 UTF-8 编码；密钥按字典顺序排序；使用无显著空白的紧凑分隔符；整数以普通十进制形式表示；浮点数在序列化前已预先转换为固定的 6 位小数字符串——即，对于仅包含整数或字符串的负载，使用 Python `json.dumps(payload, sort_keys=True, separators=(',',':'))` 表示）。这些规则是接口契约的一部分；任何修改都会影响到 `pipeline_version` 字段的溯源信息。操作员可以查看 FS12 报告（包括状态、扫描表、选定参数、Sharpe 值、情绪调整等），并对其进行哈希验证，然后进行交互式批准；批准后会添加批准信息（包括操作员 ID、时间戳以及负载的哈希值）。只有在此之后，控制流程才会进入传输阶段——网络发送操作是在批准流程内部进行的，因此未经批准的配置无法被执行，这与 FS4 在 3.2.3.4 中的设计理念是一致的。在接收端，PS 配置加载器会重新计算负载数据的哈希值，并拒绝任何与批准哈希值不符的配置。这种验证方式已在中段 3.2.3.4 中有明确规定。|**Selected.** Two independent enforcement points (server-side structural gate + SoC-side hash verification) mean FS8 survives either a server-side bug or a tampered file in transit; a REJECT/no-approval outcome leaves the SoC's previous config in place and (per 3.2.3.6) latches the next session into HOLD Mode.  <br>已选中。两个独立的执行点（服务器端结构验证 + 客户端哈希验证）意味着 FS8 能够应对服务器端漏洞或传输过程中文件被篡改的情况；如果结果被拒绝或无批准，则客户端会保持之前的配置设置，并根据 3.2.3.6 条款将下一个会话置于暂停模式。|

Transport for the approved config is a push over the PS GbE (interface 8) via `scp` to a staging path on the SoC, from which the Config Loader ingests it at startup — selected over a minimal custom TCP receiver purely for implementation convenience; the FS8 argument rests on the hash chain, not the transport.  
对于已批准的配置，传输过程是通过 `scp` 从 PS GbE（接口 8）推送到 SoC 上的临时路径。之后，配置加载器在启动时从该临时路径中读取配置——这种选择是出于实现上的便利考虑，仅通过一个最小的自定义 TCP 接收器来完成。FS8 参数是基于哈希链的，而非传输过程本身。

---

## 3.3.3 Final Design Details  
3.3.3 最终设计细节

The pipeline is a sequential staged program; Figure 3.5 shows the stage graph with FS12 log points at every transition. _(Figure placeholder — stage flowchart: [Data Import & Validation] → [Parameter Engineering] → [Regime Detection] → [Strategy Reoptimize / Backtest & Parameter Sweep] ⇐ merge [LLM Agent → Sentiment Analysis] → [Risk Analysis] → [Generate JSON Config] → [Operator Approval] → [Transmit / or REJECT→HOLD].)_  
该流程是一个分阶段进行的程序；图 3.5 展示了各个阶段的流程图，每个阶段都以 FS12 的对数点来表示。整个流程如下：[数据导入与验证] → [参数设计] → [模式识别] → [策略重新优化/回测与参数扫描] → [LLM 代理 → 情感分析] → [风险分析] → [生成 JSON 配置] → [操作员审批] → [传输/或拒绝→等待]。

### 3.3.3a Market Data Path (essential — FS6, FS7)  
3.3.3a 市场数据路径（至关重要——FS6、FS7）

#### 3.3.3a.1 Data import and Parameter Engineering  
3.3.3a.1 数据导入与参数设计

Inputs are validated before any computation (NFS8 server side): schema check on the exported session archive, monotonic-timestamp check, and a minimum-history check (≥ 60 trading days of OHLCV `[TEAM: confirm window]`). Validation failure logs a fault code and aborts the pipeline _before_ the config-generation stage — a night with bad data produces no candidate config (and therefore, by FS8's gate, no change to the live system) rather than a config built on garbage.  
在进行任何计算之前，都会先对输入数据进行验证（NFS8 服务器端）：包括对导出的会话存档的模式检查、单调时间戳检查，以及最小历史数据检查（至少包含 60 个交易日的 OHLCV 数据）。如果验证失败，系统会记录错误代码，并在配置生成阶段之前终止流程——因为一个数据质量低下的夜晚所生成的配置是没有价值的，无法用于实际系统运行。

The Parameter Engineering stage computes two features from daily OHLCV closes:  
参数工程阶段通过每日的 OHLCV 数据计算出两个特征值：

|Feature  特点|Definition  定义|Window  窗口|
|---|---|---|
|Realized volatility `σ`  实际波动率：0#|Standard deviation of daily log returns, annualized: `σ = std(ln(Cₜ/Cₜ₋₁)) × √252`  <br>日对数回报的标准差，年化后的值： `σ = std(ln(Cₜ/Cₜ₋₁)) × √252`|20 trading days `[TEAM: confirm]`  20 个交易日 `[TEAM: confirm]`|
|Trend strength `T`  趋势强度：0#|Normalized moving-average divergence: `T = (SMA₅ − SMA₂₀) / SMA₂₀`  <br>标准化移动平均差异： `T = (SMA₅ − SMA₂₀) / SMA₂₀`|5- and 20-day SMAs  <br>5 天和 20 天的标准移动平均线|

Both are standard constructions; the design contribution is not the features but the calibration scheme (Decision 2) and the guarantee it yields (3.3.4.3).  
这两种设计都是标准的构造方式；它们的设计亮点并不在于某些特性上，而在于其校准机制（决策 2）以及它所带来的保障功能（3.3.4.3）。

#### 3.3.3a.2 Regime Detection (FS6)  
3.3.3a.2 机制检测（FS6）

Thresholds are set at percentiles of the trailing calibration window, then the current day is classified by a fixed-priority rule (volatility outranks trend, because the Defensive strategy is the safe fallback and ambiguity should resolve toward it):  
阈值设定在最近一次校准窗口中的百分比水平上。然后，当前日期的类别判断遵循一个固定的优先级规则（波动优先于趋势，因为防御型策略是安全的备选方案，而不确定性应该会逐渐得到解决）：

```
θ_vol   = percentile(σ over calibration window, 75)    # 75: working empirical value, config-adjustable
θ_trend = percentile(|T| over calibration window, 60)  # 60: working empirical value, config-adjustable

if   σ_today   ≥ θ_vol:    regime = VOLATILE   → Defensive
elif |T_today| ≥ θ_trend:  regime = TRENDING   → Momentum
else:                      regime = RANGING    → Mean Reversion
```

The rule is a pure function of the input window — no state, no seed, no fit. Its unit tests enumerate the three branches plus both boundary equalities (`≥` is deliberate: boundary values classify toward the safer branch).  
这个规则是输入窗口的纯函数——没有状态变量，没有初始值，也不存在适应过程。其单元测试会涵盖这三种情况，同时还会考虑边界条件（ `≥` 是故意设计的：边界值用于将对象分类到更安全的分支中）。

#### 3.3.3a.3 Strategy Reoptimize — Backtest & Parameter Sweep (FS7)  
3.3.3a.3 策略重新优化——回测与参数扫描（FS7）

The regime selects one strategy; the sweep enumerates that strategy's parameter grid in fixed lexicographic order. Working grids (each 3 × 3 × 3 = 27 combinations ≥ FS7's minimum 9):  
该系统会选定一种策略；然后，系统会以固定的字典顺序列出该策略的所有参数组合。可用的网格数量（每个网格为 3×3×3，共 27 种组合，至少满足 FS7 的最低要求，即 9 种组合）：

|Strategy  策略|Parameter 1  参数 1|Parameter 2  参数 2|Parameter 3  参数 3|
|---|---|---|---|
|Momentum  势头|lookback ∈ {5, 10, 20}  <br>lookback 属于集合 {5, 10, 20}|entry threshold ∈ {0.005, 0.01, 0.02}  <br>进入阈值 ∈ {0.005, 0.01, 0.02}|position scalar ∈ {0.5, 1.0, 1.5}  <br>位置标量 ∈ {0.5, 1.0, 1.5}|
|Mean Reversion  均值回归|MA window ∈ {10, 20, 50}  <br>MA 窗口的取值为{10, 20, 50}|deviation threshold ∈ {0.01, 0.02, 0.05}  <br>偏差阈值 ∈ {0.01, 0.02, 0.05}|position scalar ∈ {0.5, 1.0, 1.5}  <br>位置标量 ∈ {0.5, 1.0, 1.5}|
|Defensive  防御性|spread floor ∈ {1, 2, 4} cents  <br>铺层位置 ∈ {1, 2, 4} 分|vol cutoff ∈ {0.1, 0.2, 0.4}  <br>体积截断值 ∈ {0.1, 0.2, 0.4}|position scalar ∈ {0.25, 0.5, 1.0}  <br>位置标量 ∈ {0.25, 0.5, 1.0}|

(Working empirical grids, loaded from the pipeline config; deliberately coarse per Decision 3's overfitting mitigation. Thresholds are expressed in the daily-bar proxy units of the 3.3.3a.3.1 validation run — the live intraday config carries their integer half-cent equivalents per 3.2.3.2. Note the validation run substituted a vol-window axis for the Defensive spread floor, since daily bars carry no spread.)  
正在处理从管道配置中加载的经验性网格数据；根据决策 3 中的过拟合缓解方案，网格的精度被故意设置为较粗糙的水平。阈值单位采用 3.3.3a.3.1 验证阶段所使用的日柱单位进行表示——实时日内配置则按照 3.2.3.2 中的规定，以整数半分率作为单位。注意，在验证阶段，防御性价差底值采用了成交量窗口单位，因为日柱数据并不包含价差信息。）

Each combination is evaluated by the parity-ported kernel (Decision 4):  
每个组合都会通过奇偶校验端口内核进行评估（决策 4）：

```
for params in grid (fixed lexicographic order):          # determinism: fixed order
    state = init_strategy_state(params)                  # same init as PS engine
    position, pnl_series = 0, []
    for snapshot in recorded_session_stream:             # integer cents, as exported
        decision = strategy_fn(snapshot, state, params)  # line-by-line port of PS C function
        position, pnl = apply_fill_model(decision, position, snapshot)
        pnl_series.append(pnl)
    metrics[params] = sharpe(pnl_series), max_drawdown(pnl_series), n_trades
select params* = argmax over sharpe,
       ties broken by lexicographic parameter order      # total order ⇒ unique winner
```

The fill model is the prototype simplification: fill at the touch (best bid/ask of the snapshot) for order sizes within displayed quantity `[TEAM: confirm fill assumption; document as a stated limitation — no queue-position or impact modeling]`. Sharpe is computed as a P&L-based variant: `mean(daily P&L) / std(daily P&L) × √252` with a zero risk-free rate, which is a variant of the standard return-based Sharpe ratio adapted for absolute P&L rather than percentage returns `[TEAM: confirm]`. The metric arithmetic is float, but evaluated in a fixed sequential order over deterministic integer inputs, so results are bit-stable across re-runs (3.3.4.2); the tie-break rule removes the only remaining path by which a float comparison could produce run-dependent selection.  
“填充模型”是一种简化的原型：在显示的数量范围内，对订单规模进行填充操作，所选价格为当前快照中的最优报价。而“夏普比率”则是一种基于损益的度量标准：以 `mean(daily P&L) / std(daily P&L) × √252` 为单位进行计算，并采用零风险利率作为基准。这种度量标准实际上是基于绝对损益而非百分比回报的夏普比率的变体。该指标采用浮点数进行运算，但在确定性的整数输入下会按照固定的顺序进行计算，因此结果在重复计算时具有稳定性（3.3.4.2 节）。平局处理规则消除了可能导致结果因计算顺序而变化的唯一可能性。

##### 3.3.3a.3.1 Preliminary validation run (real data)  
3.3.3a.3.1 初步验证运行（真实数据）

The classification and sweep procedures above have been run end-to-end against **real historical daily OHLCV** — not synthetic data — as a preliminary check ahead of full implementation. _(Data-source note: huggingface.co — the originally identified defeatbeta/yahoo-finance-data source — was unreachable from the sandboxed dev environment's network allowlist, so this run substitutes matplotlib/sample_data/aapl.csv (real AAPL daily OHLCV, 1984-09-07 to 2008-10-14, BSD-licensed public repo, fetched via raw.githubusercontent.com). This remains a development/validation placeholder; the production data source is now pinned to the 3.4 corpus per 3.3.1 — simulator-session daily bars plus the LOBSTER AAPL sample day — so no external feed or license is required.)_  
上述分类和筛选程序已经针对真实的历史每日 OHLCV 数据进行了端到端的测试——而不是使用合成数据作为初步验证。 （数据来源说明：原本指定的 defeatbeta/yahoo-finance-data 源无法从沙盒开发环境的网络允许列表中访问，因此这里使用了 matplotlib/sample_data/aapl.csv 作为替代数据，该数据实际上是真实的 AAPL 每日 OHLCV 数据，时间范围从 1984 年 9 月 7 日持续到 2008 年 10 月 14 日，属于 BSD 许可的公开仓库，通过 raw.githubusercontent.com 获取。这一数据仍属于开发/验证用途；实际的生产数据来源已固定在 3.4 版本中，具体描述见 3.3.1 章节——即模拟器每日柱状图数据，以及 LOBSTER AAPL 样本日数据。因此无需外部数据源或许可即可使用。）

**Regime classification (FS6), real data:** calibration window 2007-04-18 to 2008-04-16 (252 trading days) yields `θ_vol = 0.518`, `θ_trend = 0.059`. Classifying the following 126-trading-day test window (2008-04-17 to 2008-10-14 — the tail of this dataset, which happens to fall in the Sept–Oct 2008 crash) produces:  
体制分类（FS6），实际数据：校准窗口为 2007-04-18 至 2008-04-16，共 252 个交易日，得到的数值分别为 `θ_vol = 0.518` 和 `θ_trend = 0.059` 。对以下 126 个交易日的数据窗口进行分类（2008-04-17 至 2008-10-14——这个数据集中段，恰好发生在 2008 年 9 月至 10 月的市场崩盘期间），得到的结果如下：

|Regime  政权制度|Days (of 126)  126 天|
|---|---|
|RANGING|80|
|TRENDING|29|
|VOLATILE|17|

All three regimes non-empty — the 3.3.4.3 non-degeneracy proof holds empirically, not just analytically, on the one real dataset available.  
这三种情况都是成立的——3.3.4.3 中的非退化性证明是基于实际数据而成立的，而不仅仅是基于理论分析得出的结论。

**Grid sweep (FS7), daily-bar proxy:** the same 27-point grids run against the days each real regime actually classified, selecting by Sharpe with the fixed tie-break:  
网格扫描（FS7），每日条形图代理：使用相同的 27 个网格进行扫描，对比的是每个实际执政政权所采用的分类方式。根据夏普指数进行筛选，采用固定的平局决胜规则。

|Regime  政权制度|Strategy  策略|Winning parameters  获胜参数|Sharpe  沙普|
|---|---|---|---|
|TRENDING|Momentum  势头|lookback=5, entry_thresh=0.01, pos_scalar=1.5  <br>lookback=5，entry_thresh=0.01，pos_scalar=1.5|**1.856**|
|RANGING|Mean Reversion  均值回归|window=20, dev_thresh=0.02, pos_scalar=0.5|**2.077**|
|VOLATILE|Defensive  防御性|vol_window=20, vol_cutoff=0.2, pos_scalar=0.5|**−3.125  -3.125**|

The VOLATILE result is deliberately reported as-is rather than adjusted: even the _best_ of 27 candidate configurations during a genuine market crash is a losing one on a risk-adjusted basis. This is not a design failure — it is precisely the situation the FS8 approval gate exists for. A nightly optimizer that silently deployed the argmax without human review would ship a confidently-labeled "best" configuration that still loses money; the design's requirement that the operator see the **full sweep table**, not just the winning row, is what turns this from a hidden failure into a visible, actionable one (the operator's expected action here is to reject, or to accept Defensive at reduced size, not to be surprised later).  
“VOLATILE”这一结果被故意以原始数据的形式呈现，没有经过任何调整。即使在真正的市场崩溃情况下，27 种候选配置中最好的那种，在风险调整的基础上仍然属于失败的方案。这并不是设计上的缺陷——这正是 FS8 审批机制存在的意义所在。每晚进行的优化过程中，那些在没有人工审核的情况下自动生成 argmax 配置的方案，最终也会产生亏损的结果；而设计上的要求是让操作员能够看到完整的搜索表，而不仅仅是获胜的某一行数据。正是这一设计要求使得这种隐藏的缺陷变成了可观察到的、需要处理的缺陷（此时操作员的预期行动是拒绝接受该方案，或者接受一个规模更小的版本，而不是之后才发现问题）。

**Kernel throughput (NFS5), measured on this dev host:** a representative parity-style kernel call (ring-buffer update + integer threshold compare + position update) was microbenchmarked directly rather than assumed: **1,779,215 calls/sec** measured, versus the ≈ 10⁶ calls/s pessimistic estimate used in the original 3.3.4.1 draft. This measured figure is carried into 3.3.4.1 below, tightening (not loosening) the NFS5 margin.  
在这台开发主机上测量的内核吞吐量（NFS5）：对一个典型的奇偶校验类型内核调用过程进行了微基准测试，该过程包括环形缓冲区更新、整数阈值比较以及位置更新等步骤。实际测量到的吞吐量为 1,779,215 次调用/秒，而最初在 3.3.4.1 版本草案中预测的吞吐量约为 10⁶次调用/秒。这个实际数值被纳入了 3.3.4.1 版本中，从而进一步缩小了 NFS5 的预计吞吐量差距。

This run validates the _procedure_ — determinism, non-degenerate classification, fixed tie-break, Sharpe selection, sweep-table transparency — on real market data. It is explicitly **not** a validation of tick-level latency (3.3.4.1's per-record cost model) or of the actual PL/PS system (which does not exist yet); the input here is daily bars from a public archive, not a PS-exported snapshot session.  
这次运行验证了该算法的有效性——无论是在确定性处理、非退化分类、固定的决胜局规则、夏普选择算法，还是扫描表透明度方面，都能在真实市场数据上得到验证。需要注意的是，此次验证并不涉及票盘级别的延迟问题（3.3.4.1 中的每记录成本模型），也不涉及实际的 PL/PS 系统（该系统目前还不存在）。这里的输入数据来自公共档案中的每日交易记录，而非 PS 系统输出的快照数据。

---

### 3.3.3a.4 Risk Analysis and config generation  
3.3.3a.4 风险分析与配置生成

The Risk Analysis stage is a checklist, not an optimizer: (1) the selected parameters' backtest never breached FS3 ceilings (notional ≤ $50,000 CAD, position ≤ 1,000 shares, rate ≤ 1,000 orders/s — the live values, enforced again at runtime by 3.2.3.3); (2) max drawdown below a sanity bound `[TEAM: value]`; (3) sentiment adjustment applied to position limits per 3.3.3b.3; (4) minimum-trade-count floor so a "great Sharpe" from 2 trades is flagged for the operator `[TEAM: floor value]`. Any check failure is written into the operator report — Risk Analysis annotates, the operator decides.  
风险分析阶段只是一个检查清单，而非优化过程：(1) 所选参数的回测结果从未超过 FS3 的上限——名义价值不超过 50,000 加元，持仓数量不超过 1,000 股，订单频率不超过 1,000 单/小时——这些限制是在运行时由 3.2.3.3 条款强制执行的；(2) 最大回撤幅度低于 0#的合理性界限；(3) 根据 3.3.3b.3 条款对持仓限额进行情绪调整；(4) 最小交易次数要求，以便操作员能够通过对 1#笔交易实现“优秀的夏普比率”来标记交易。任何检查失败的情况都会被记录在操作报告中——风险分析由系统自动执行，具体如何处理则由操作员决定。

### 3.3.3b Text & Sentiment Path (non-essential — FS9, FS10)  
3.3.3b 文本与情绪路径（非必需功能——仅适用于 FS9 和 FS10 版本）

#### 3.3.3b.1 LLM Agent — ingestion and extraction (FS9)  
3.3.3b.1 大型语言模型代理——数据摄取与提取（FS9）

The agent fetches ≥ 10 text assets over HTTPS from a configured source list `[TEAM: source list; the FS9 demo runs against a mocked web server per its verification procedure]`, handling three asset classes: HTML news pages, short-form social posts, and PDF reports (text-extracted before prompting). For each asset it emits exactly one structured event record:  
该代理通过 HTTPS 协议从配置好的源列表 `[TEAM: source list; the FS9 demo runs against a mocked web server per its verification procedure]` 中获取至少 10 个文本数据资源。这些数据资源涵盖三种类型：HTML 新闻页面、简短形式的社会新闻帖子以及 PDF 报告（在提示之前先对文本进行提取）。对于每个资源类型，该代理都会生成一条结构化的事件记录。

|Field  字段|Type  类型|Notes  备注|
|---|---|---|
|headline  标题|string  字符串|FS9 field  FS9 字段|
|ticker  记事本/记录本|string  字符串|FS9 "entity/ticker mentioned"; `NONE` if no entity — record still logged, excluded from scoring  <br>FS9“已提及实体/股票代码”； `NONE` 如果未提及任何实体，则记录仍会被保存，但不会计入得分。|
|timestamp  时间戳|ISO-8601|FS9 field  FS9 字段|
|source  来源|string (URL)  字符串（URL）|FS9 field  FS9 字段|
|raw_excerpt  摘录/节选|string  字符串|Verbatim scored text, retained for audit; capped at 512 characters (working empirical value — comfortably inside FinBERT's 512-token input limit)  <br>逐字记录下来的文本，用于审计目的；记录长度上限为 512 个字符（经验数值设定——远低于 FinBERT 系统中规定的 512 个字符的输入限制）|

Records are appended to the immutable nightly event log — the determinism boundary of Decision 5. Per-asset failures (fetch error, extraction failure) log a fault code and skip the asset; the path proceeds with whatever succeeded, down to zero.  
这些记录会被追加到不可修改的每晚事件日志中——这是决策 5 所设定的确定性边界。每个资产的故障情况（如数据获取失败、提取失败等）都会记录下相应的错误代码，并跳过该资产的处理；之后系统会继续处理下一个成功的操作，直到处理完所有资产为止。

#### 3.3.3b.2 Sentiment Analysis (FS10)  
3.3.3b.2 情感分析（FS10）

Each record's `headline + raw_excerpt` passes through local FinBERT inference (CPU, single-threaded — a determinism condition, see 3.3.4.2): `score_i = P_pos(i) − P_neg(i) ∈ [−1, +1]`. Daily aggregate `s = mean(score_i)` over records with a matching ticker; `abnormal_event_flag = any(|score_i| ≥ θ_abn)` (θ_abn = 0.8, pipeline-config value). Zero usable records ⇒ `s = 0`, flag false — the neutral element by design.  
每条记录的 `headline + raw_excerpt` 都会经过本地 FinBERT 推理过程（在 CPU 上、单线程执行——这是一种确定性推理方式，详见 3.3.4.2 节）。对于具有匹配股票代码的记录，会进行每日汇总，得到 `s = mean(score_i)` 。不过，可用的记录数为零，因此结果为 `s = 0` ，标志为 false——这是设计上的中性结果。

#### 3.3.3b.3 Coupling into Risk Analysis  
3.3.3b.3 与风险分析的关联

Position-limit adjustment, applied in Risk Analysis (never to the optimization objective):  
位置限制调整，应用于风险分析中（永远不适用于优化目标）：

```
L(s) = L_base × max(f_min, 1 + k·min(s, 0))      k = 0.5, f_min = 0.5 (working empirical values, pipeline-config adjustable)
```

Properties proven in 3.3.4.4: `L(s) ≤ L_base` always; `L(s) = L_base` for all `s ≥ 0`; `L` is monotone non-decreasing in `s` and floored at `f_min·L_base`. The abnormal flag additionally stamps a `DEFENSIVE-REVIEW` advisory into the operator report — advisory-only (selected): the operator remains the only override authority, consistent with FS8's single-gate design.  
在 3.3.4.4.4 中已验证的属性： `L(s) ≤ L_base` 始终适用； `L(s) = L_base` 适用于所有 `s ≥ 0` ； `L` 在 `s` 中是单调非递减的，并在 `f_min·L_base` 处终止。此外，还有 `DEFENSIVE-REVIEW` 的额外提示信息，该提示仅用于操作员报告——完全由操作员自行决定是否需要执行此提示。这与 FS8 的单门设计保持一致，即操作员仍然是唯一的权限决定者。

### 3.3.3.5 JSON configuration schema (interface 8 contract, jointly owned with 3.2.3.4)  
3.3.3.5 JSON 配置模式（接口 8 合约，与 3.2.3.4 共同使用）

|Field  字段|Type  类型|Content  内容|
|---|---|---|
|`strategy_id`|string  字符串|`momentum` / `mean_reversion` / `defensive`|
|`regime_label`|string  字符串|`trending` / `ranging` / `volatile`|
|`parameters`|object  对象|The swept winner's values, integer-encoded to match the PS kernel. Keys per strategy — momentum: `lookback`, `entry_thresh`, `pos_scalar`; mean_reversion: `window`, `dev_thresh`, `pos_scalar`; defensive: `spread_floor`, `vol_cutoff`, `pos_scalar` (lockstep with 3.2.3.2's formulas and the 3.3.3a.3 grid axes)  <br>获胜者的数值已整数编码，以匹配 PS 内核的要求。每种策略对应的键值如下：动量策略有 `lookback` 、 `entry_thresh` 、 `pos_scalar` ；均值反转策略有 `window` 、 `dev_thresh` 、 `pos_scalar` ；防御型策略有 `spread_floor` 、 `vol_cutoff` 、 `pos_scalar` （其计算方式与 3.2.3.2 中的公式以及 3.3.3a.3 的网格轴一致）。|
|`risk_limits`|object  对象|`max_notional_cad`, `max_position_shares`, `max_order_rate` — post-sentiment values, each ≤ its FS3 ceiling  <br>`max_notional_cad` 、 `max_position_shares` 、 `max_order_rate` ——情绪后的值，每个数值都小于等于其 FS3 上限值|
|`provenance`|object  对象|Data window, grid hash, backtest Sharpe, sentiment score, pipeline version — the FS12 record embedded for audit  <br>数据窗口、网格哈希值、回测莎普尔指数、情绪得分、管道版本——FS12 记录已嵌入以供审计使用。|
|`approval`|object  对象|`operator_id`, `timestamp`, `payload_sha256` — appended only by the approval action (Decision 6)  <br>`operator_id` 、 `timestamp` 、 `payload_sha256` ——仅通过审批操作进行附加处理（决策 6）|

### 3.3.3.6 FS12 status reporting and server-side fault handling (NFS8)  
3.3.3.6 FS12 状态报告与服务器端故障处理（NFS8）

Every stage transition writes one structured log line — `(timestamp, stage, status, key metrics)` — to console and to the nightly log file; the approval prompt renders the accumulated report (regime, full sweep table, selected parameters, Sharpe, sentiment, risk-check annotations, payload hash). FS12's verification (one entry per stage transition, including final approval status) is satisfied by the `run_stage()` wrapper of Decision 1's orchestration corollary. Server-side recoverable faults follow one uniform policy: log a timestamped fault code; degrade to the stage's neutral/abort behavior (text path → neutral; market path → abort before config generation); never emit a config that any validation stage has not passed.  
每个阶段转换都会向控制台和每晚的日志文件中写入一条结构化的日志条目—— `(timestamp, stage, status, key metrics)` 。审批提示会显示累积的报告内容（包括制度、完整扫描表、选定参数、夏普值、情绪分析结果、风险检查注释以及数据哈希值）。FS12 的验证功能（每个阶段转换对应一条记录，包括最终审批状态）由 Decision 1 的编排逻辑实现。服务器端可恢复的故障遵循统一的处理规则：记录带有时间戳的故障代码；将系统降级为阶段的中性/终止行为（文本路径时转为中性状态；市场路径则在配置生成前终止操作）；绝不会生成任何未被验证阶段的配置数据。

---

## 3.3.4 Quantitative Technical Analysis  
3.3.4 定量技术分析

### 3.3.4.1 NFS5 runtime budget decomposition  
3.3.4.1 NFS5 运行时的预算分配

NFS5 allows 30 minutes on the reference workload (1 year of daily OHLCV). The pipeline's cost is dominated by one term — the sweep's kernel replay — and every other stage is bounded by trivial arithmetic:  
NFS5 允许在参考工作负载上运行 30 分钟（相当于一年日复一日地执行 OHLCV 任务）。该流程的成本主要由一个环节决定——即扫描内核的重放过程——而其他所有环节的成本都可以通过简单的算术运算来估算。

```
Regime path input:      252 daily bars → feature computation O(n), n = 252    → milliseconds
Regime classification:  two percentile lookups + three comparisons, O(1)      → microseconds

Sweep workload:
  snapshot records/session = 100 Hz × 6.5 h × 3600 s/h = 2.34 M records
  grid size                = 27 combinations
  kernel evaluations       = 27 × 2.34 M ≈ 63.2 M strategy-function calls
  CPython throughput       = 1,779,215 calls/s — MEASURED, not assumed (3.3.3a.3.1 microbenchmark:
                             ring-buffer update + integer compare + position update, on the dev sandbox host)
  sweep time                = 63.2 M ÷ 1.78 M ≈ 35.5 s ≈ 0.6 min
  ×5 pessimism factor       ≈ 3.0 min  (target host will likely be faster than the sandbox; kept anyway)

Text path: 10 assets × ~5 s LLM extraction ≈ 1 min [EVIDENCE: per-asset latency];
           FinBERT/LM-dictionary scoring ~10² ms × 10 records ≈ seconds
Report/serialize/hash:  negligible

Pipeline total (pessimistic): ≈ 4–5 min  →  ≥ 6× margin against NFS5 = 30 min
```

Two conclusions. First, this arithmetic is what licenses Decisions 1, 3, and 4, and the measured figure makes the case stronger than originally estimated: Python is fast enough, exhaustive search is affordable, and the slow parity kernel costs well under a minute against a 30-minute budget — the "slow-but-identical" trade is not just affordable, it is close to free. Second, the margin is a _design allowance_, not slack to be admired: it absorbs grid growth (a much larger grid still fits — see 3.3.4.5, revised with the measured rate) and multi-session backtest windows. `[EVIDENCE: this microbenchmark ran on the development sandbox, not the eventual target host; re-run on the actual EOD server before final submission — the qualitative conclusion (Python is not the bottleneck) is not expected to change, only the exact margin.]`  
有两个结论。首先，这种计算方法正是支持第 1、3 和 4 项决定的基础。通过测量得出的数据表明，Python 的速度足够快，而穷举搜索也是可行的。此外，慢速的 Parity 内核在 30 分钟的预算内只需花费不到一分钟的时间——这种“慢但有效”的替代方案不仅可行，而且几乎可以说是免费的。其次，这个差距其实是一种设计上的允许范围，而不是值得赞赏的不足：它足以应对网格的扩展需求（即使网格规模更大，也能满足需求——参见 3.3.4.5 节，根据测量数据进行了调整）。 `[EVIDENCE: this microbenchmark ran on the development sandbox, not the eventual target host; re-run on the actual EOD server before final submission — the qualitative conclusion (Python is not the bottleneck) is not expected to change, only the exact margin.]`

### 3.3.4.2 FS7 determinism argument — enumeration of nondeterminism sources  
3.3.4.2 FS7 的确定性论点——非确定性来源的列举

FS7's verification is unusual: it does not measure a quantity, it demands _bit-identical_ re-execution. The design therefore treats determinism as a property to be established by exhaustively closing every leak, not by testing alone:  
FS7 的验证方式非常独特：它并不测量某个具体量值，而是要求执行过程中的各个步骤必须完全一致。因此，该设计将确定性视为一种属性，需要通过彻底排除所有潜在缺陷来确立，而不仅仅是通过测试来实现。

|Nondeterminism source  非确定性来源|Where it would enter  <br>当它进入那里的地方……|How the design eliminates it  <br>这种设计是如何消除它的呢？|
|---|---|---|
|Random initialization / sampling  <br>随机初始化/抽样|Classifier fit, Bayesian/random search  <br>分类器拟合，贝叶斯方法/随机搜索|No fitted model (Decision 2); no sampling (Decision 3) — no RNG is ever seeded because none is used  <br>没有合适的模型（决策 2）；也没有进行抽样操作（决策 3）——因为根本不需要使用随机数生成器，所以也就不存在随机数的生成问题。|
|Parallel evaluation / reduction order  <br>并行评估/降序排序|Multi-process sweep; float summation order varies  <br>多进程扫描；浮点数的求和顺序可变|Sweep is strictly sequential in fixed lexicographic order; float reductions always occur in the same order, so IEEE-754 results are bit-stable across runs on the same platform `[TEAM: pin platform in verification procedure — cross-machine bit-identity additionally requires identical libm/BLAS, so FS7's test runs on one designated host]`  <br>排序过程严格遵循固定的字典顺序；数值的合并操作始终按照相同的顺序进行。因此，在同一平台上重复执行 IEEE-754 运算时，其结果将是稳定的 `[TEAM: pin platform in verification procedure — cross-machine bit-identity additionally requires identical libm/BLAS, so FS7's test runs on one designated host]`|
|Hash/dict iteration order  <br>哈希/字典的迭代顺序|Config serialization, grid enumeration  <br>配置序列化，网格枚举|Grids are explicit ordered lists; serialization is canonical (sorted keys, fixed formatting — Decision 6)  <br>网格是一种有序的列表结构；序列化方式是标准的（排序后的键值，固定的格式——决策 6）|
|Floating-point strategy state  <br>浮点运算策略说明|Divergence between PS and server decisions  <br>PS 与服务器端决策之间的差异|Strategy kernel is integer-only (3.2.3.2 commitment), ported line-by-line — decisions are exact, floats appear only in post-hoc metrics  <br>策略核心仅支持整数运算（符合 3.2.3.2 节的约定）。该核心模块已逐行移植到新系统中——所有决策都是精确的，浮点数仅用于事后统计指标的计算。|
|Tie on the selection metric  <br>在选择指标上处于并列状态|Two grid points with equal Sharpe  <br>两个网格点具有相同的夏普比率。|Total-order tie-break (lexicographic parameter order) — the argmax is unique by construction  <br>总排序决胜法（字典序参数顺序）——根据构造原理，argmax 是唯一的。|
|Threaded ML inference  线程式机器学习推理|FinBERT multi-thread scheduling can reorder float ops  <br>FinBERT 的多线程调度能够重新安排浮点运算的顺序。|Single-threaded CPU inference pinned in configuration (3.3.3b.2)  <br>单线程的 CPU 推理功能已固定在配置中（3.3.3b.2）|
|External LLM output variance  <br>外部大语言模型输出方差|FS9 extraction  FS9 提取|Outside the determinism boundary by design (Decision 5): records are logged verbatim, and FS7's re-run is defined from logged inputs  <br>出于设计上的考虑，这些记录完全遵循了随机性的原则（决策 5）：记录内容被原封不动地记录下来，而 FS7 的重新运行也是基于这些记录输入来进行的。|

The residual claim — same host, same inputs, same binary ⇒ same bytes — is then verified directly by FS7's double-run procedure. `[EVIDENCE: two full pipeline runs on the reference dataset, byte-compare of emitted config payloads.]`  
剩余的索赔部分——相同的主机、相同的输入数据、相同的二进制数据，因此相同的字节数——可以通过 FS7 的双次验证程序直接进行验证。 `[EVIDENCE: two full pipeline runs on the reference dataset, byte-compare of emitted config payloads.]`

### 3.3.4.3 Regime classifier non-degeneracy (FS6 verifiability by construction)  
3.3.4.3 机制分类器非退化性（通过构造验证，符合 FS6 标准）

FS6's verification requires ≥ 3 distinct regimes assigned over a 6-month window (~126 trading days). For a threshold classifier this fails only if some regime bucket is empty — which is exactly what fixed absolute thresholds risk (a calm 6 months may never cross a hardcoded vol constant, collapsing the output to one or two labels). The percentile scheme closes this analytically:  
FS6 的验证要求在一个 6 个月的周期内（约 126 个交易日），至少分配 3 种不同的策略。对于阈值分类器来说，只有当某个策略区间为空时才会出现这种情况——而固定绝对阈值确实会面临这种风险：在 6 个月的时间里，由于 hardcoded 的波动率始终保持不变，因此输出结果可能只会呈现一两个标签。而百分比方案则能够解决这个问题：

```
θ_vol = 75th percentile of {σₜ} over the same window
  ⇒ |{t : σₜ ≥ θ_vol}| ≥ ⌈0.25 × 126⌉ = 32 days classified VOLATILE   (by definition of percentile)

Remaining ≈ 94 days have σ < θ_vol and are split by θ_trend = 60th percentile of {|Tₜ|}:
  computed over the full window ⇒ ~40% of all days lie above it;
  even if every VOLATILE day were also high-|T|, at least 0.40×126 − 32 ≈ 18 days
  remain TRENDING, and at least 126 − 32 − 0.40×126 ≈ 44 days remain RANGING.
```

All three buckets are therefore provably non-empty **for the same-window-percentile variant of the classifier** — the variant where θ_vol/θ_trend are computed over the very 6-month window being classified. `[TEAM: if θ_trend is instead computed over the sub-VOLATILE days only, the bound tightens further; confirm which definition we implement — the analysis above is the conservative case.]` The construction is symbol-agnostic — thresholds are relative to each symbol's own distribution, so it would carry over unchanged if the single-symbol scope is ever widened.  
因此，对于分类器的同一窗口百分比变体来说，这三个桶都可以被证明是非空的。在这种变体中，θ_vol/θ_trend 的计算是基于用于分类的整整 6 个月的时间窗口来进行的。这种构造方式是不依赖于符号的——阈值是根据每个符号自身的分布来确定的，所以即使单一符号的范围有所扩大，这种构造方式仍然保持不变。

**A gap worth stating plainly.** The deployed design in 3.3.3a.2 does **not** use the same-window variant just proven — it calibrates thresholds on a _trailing_ window and applies them to the _next_ (out-of-sample) window, because a live system cannot know today's percentile using data that includes today before today has happened. That trailing-calibration scheme is the only one that is actually deployable, but it does not inherit the clean 25%-floor guarantee above: nothing stops a calm calibration window from setting a θ_vol that a calmer test window never reaches. The proof above should therefore be read as showing the _concept_ cannot degenerate in principle, not as a guarantee about the _deployed_ scheme — that gap is exactly what the empirical run below is for.  
这是一个值得明确指出的差距。在 3.3.3a.2 中使用的设计并没有采用刚刚验证过的那种窗口变体——它采用的是基于最近窗口的阈值校准方法，并将这些阈值应用到下一个（超出样本范围的）窗口上。因为实时系统无法利用那些在今天发生之前的数据来得知今天的百分比值。这种基于最近窗口的校准方法才是真正可行的方案，但它无法继承上述那套简洁的 25%阈值保证。没有什么能阻止一个较为平稳的校准窗口设定出一个较平稳的测试窗口永远无法达到的θ_vol 值。因此，上述证明应该被理解为表明这个概念在原则上不会退化，而不是对实际应用的方案的保证——而那个差距正是下面的实验所验证的内容。

**Empirical confirmation.** The preliminary run in 3.3.3a.3.1 tests the actual deployed (trailing-calibration, out-of-sample) scheme — not the same-window variant proved above — on one real 6-month window (2008-04-17 to 2008-10-14, real AAPL daily closes, thresholds calibrated on the preceding 252 trading days): 80 RANGING / 29 TRENDING / 17 VOLATILE days, all three non-empty. This is one data point, not a proof, and it is a favorable one (2008 was genuinely volatile, so VOLATILE was in no danger of being empty here); it does not close the gap identified above. `[TEAM: the honest next step is running the trailing-calibration scheme across many overlapping 6-month windows — including calm ones — and reporting the empirical non-empty rate, rather than resting on a single favorable window or the same-window proof that doesn't match what ships.]`  
经验性验证。在 3.3.3a.3.1 中的初步测试验证了实际应用的方案——即上述提到的“相同窗口区间”变体——在一个真实的 6 个月时间段内进行了验证（时间范围：2008-04-17 至 2008-10-14，以实际的 AAPL 日收盘价为准，阈值基于前 252 个交易日进行校准）。测试结果显示，有 80 天属于波动型交易，29 天属于趋势型交易，17 天属于波动性交易；这三种类型的时间段均不为空。这只是一个数据点而已，并非最终证明，但结果相当有利（2008 年确实是一个波动较大的年份，因此波动性交易类型在这里并不为空）。不过，这一结果并未填补上述提到的空白。 `[TEAM: the honest next step is running the trailing-calibration scheme across many overlapping 6-month windows — including calm ones — and reporting the empirical non-empty rate, rather than resting on a single favorable window or the same-window proof that doesn't match what ships.]`

### 3.3.4.4 Sentiment risk-coupling safety bound (FS10 cannot violate FS3)  
3.3.4.4 情绪风险与安全性界限的耦合（FS10 不得违反 FS3）

Claim: for every sentiment score `s ∈ [−1, +1]`, the adjusted position limit satisfies `f_min·L_base ≤ L(s) ≤ L_base ≤ FS3 ceiling`.  
声明：对于每一个情绪得分 `s ∈ [−1, +1]` ，调整后的位置限制满足 `f_min·L_base ≤ L(s) ≤ L_base ≤ FS3 ceiling` 的条件。

```
L(s) = L_base × max(f_min, 1 + k·min(s, 0)),      k = 0.5, f_min = 0.5, L_base ≤ 1,000 shares

Case s ≥ 0:  min(s,0) = 0  ⇒ inner term = 1        ⇒ L(s) = L_base            (no expansion, ever)
Case s < 0:  inner term = 1 + k·s ∈ [1 − k, 1) = [0.5, 1)
             ⇒ L(s) = L_base × max(0.5, 1+k·s) ∈ [0.5·L_base, L_base)          (monotone tightening)
```

The upper bound `L(s) ≤ L_base` holds in both cases with no dependence on the score's _accuracy_ — a wildly wrong sentiment score can only make the system trade smaller, never larger, and `s = 0` (the failure default of 3.3.3b.2) is the identity. Combined with the PS Runtime Risk Guard re-enforcing the FS3 ceilings at runtime (3.2.3.3), FS3 protection is two-layered and the entire non-essential path lies strictly inside it. This inequality is the formal version of Decision 5's "incapable of harming the essential system."  
在两种情况下，上界 `L(s) ≤ L_base` 都成立，而这一上界并不依赖于评分的准确性——一个极错误的情感评分只会导致系统进行的交易规模变小，而不会变大。而 `s = 0` （3.3.3b.2 中的失败默认情况）是一个恒等函数。结合 PS 运行时风险防护机制，该机制在运行时强化了 FS3 的上限限制（3.2.3.3），因此 FS3 的保护机制具有双层防护机制，所有非关键路径都严格地处于这一保护机制之内。这种不等式实际上是“无法对关键系统造成危害”这一决策的逻辑表述。

### 3.3.4.5 Grid scale sensitivity (why exhaustive search is the right size, and when it stops being)  
3.3.4.5 网格尺度敏感性（为什么穷举搜索是正确的选择，以及何时它不再适用）

|Configuration  配置|Kernel evaluations  内核评估|Est. sweep time (pessimistic 5 μs/call)  <br>最坏情况下的扫描时间（悲观估计为每通电话 5 微秒）|Verdict  判决结果|
|---|---|---|---|
|Prototype: 1 symbol × 27-pt grid × 1 session  <br>原型：1 个符号 × 27 点的网格 × 1 次会话|63 M  63 百万|≈ 5.5 min  ≈ 5.5 分钟|Selected operating point  <br>选定的运行点|
|5-value axes (125-pt grid)  <br>五维坐标轴（125 点网格）|293 M  293 百万|≈ 24 min  ≈ 24 分钟|Fits NFS5 alone; no headroom with text path — practical ceiling of the pure-Python kernel  <br>仅适用于 NFS5 版本；文本路径方面缺乏扩展空间——纯 Python 内核的实际运行上限有限|

The table bounds the design's validity region explicitly: exhaustive grid + parity kernel is correct for the specified prototype and its first two growth steps, and the design records precisely which future requirement invalidates it and what the successor is.  
该表格明确指出了设计的有效范围：对于指定的原型及其前两个发展阶段，穷举法网格搜索和奇偶校验核算法都是有效的。此外，表格还详细记录了哪些未来的需求会使得该设计失效，以及其后续替代方案是什么。

---

## 3.3.5 Specification Compliance Summary  
3.3.5 规范符合性总结

|Spec  规格/参数|How the final design satisfies it  <br>最终的设计是如何满足这一要求的呢？|Evidence status  证据状态|
|---|---|---|
|FS6|Percentile-thresholded two-feature classifier; ≥ 3 non-empty regimes provable by construction (3.3.4.3)  <br>基于百分位阈值的双特征分类器；通过构造可以证明存在至少 3 个非空区域（3.3.4.3 节）|Closed by arithmetic; pending 6-month reference-data run  <br>由于算术计算问题，该事务暂时无法处理；需进行为期 6 个月的参考数据更新工作。|
|FS7|Exhaustive fixed-order grid + integer parity kernel + total-order tie-break; all nondeterminism sources enumerated and closed (3.3.4.2)  <br>全面的固定顺序网格结构，加上整数奇偶性内核，以及全顺序的决胜机制；所有非确定性因素都已处理并解决（3.3.4.2）|Analytical; pending double-run byte-compare  <br>分析状态；正在处理双运行版本的字节比较操作|
|FS8|Hash-bound approval; transmission call structurally unreachable without approval; PS-side hash re-verification (Decision 6)  <br>审批过程受阻；传输请求在未经批准的情况下无法完成；PS 端哈希值验证仍需进行（决策 6）|Pending no-approval / tampered-hash injection tests  <br>等待审批结果/哈希值篡改引发的注入测试尚未完成|
|FS9 (non-ess.)  FS9（非核心任务）|LLM agent → verbatim-logged structured records; per-asset fault isolation  <br>LLM 代理 → 逐字记录结构化数据；按资产进行故障隔离|Pending mocked-server ingestion test  <br>等待对模拟服务器进行的数据摄取测试|
|FS10 (non-ess.)  FS10（非核心职位）|FinBERT scoring in [−1,+1] by construction; risk-tightening-only coupling with proven bound (3.3.4.4)  <br>根据构造，FinBERT 的得分在[−1, +1]范围内；仅通过收紧风险来调控，且已证明存在有限制（3.3.4.4）|Analytical; pending pre-labeled reference-set test  <br>分析性状态；正在等待预标记参考集测试的结果|
|FS12 (non-ess.)  FS12（非必需）|`run_stage()` wrapper logs every transition; approval report aggregates regime/sweep/Sharpe/status  <br>`run_stage()` 包装器会记录每一次转换的过程；审批报告则汇总了各种制度/扫描/夏普值/状态等信息。|Pending full-cycle log inspection  <br>在全面检查整个周期日志之前，暂时无法给出结果。|
|NFS5 (non-ess.)  NFS5（非必需）|≈ 7–8 min pessimistic total vs 30 min budget; ≥ 3× margin with growth allowance (3.3.4.1, 3.3.4.5)  <br>约 7-8 分钟的总时间需求，预算为 30 分钟；利润率需达到 3 倍以上，并包含增长预留部分（参见 3.3.4.1、3.3.4.5 条）|Analytical; pending reference-dataset wall-clock  <br>分析性的；待处理的参考数据集相关工作|
|NFS8 (partial)  NFS8（部分内容）|Validate-before-compute; fault-coded logging; text path degrades to neutral; no config emitted past a failed validation  <br>在计算之前进行验证；错误编码的日志记录；文本路径降级为中性状态；在验证失败的情况下不会输出任何配置信息|Pending malformed-input injection  <br>待处理的畸形输入注入行为|

---

# 3.4 Exchange Simulator Subsystem  
3.4 交换模拟子系统

> **Template conventions:** `[TEAM: …]` needs a team decision; `[EVIDENCE: …]` is an analytical target pending measurement; `[REF-n]` maps to the bibliography at the end of this section. **Diagram naming:** the block diagram labels this subsystem _"Exchange Simulator on Host (Live Order Book & Executor — 1 Exch / 1 Stock)"_; internal component names below are _Order-Flow Generator (dual-driver), Book Mirror, Protocol Encoder, Order Executor (validate-and-log), Scenario Engine, Ground-Truth Logger_. `[TEAM: keep headings and diagram labels in lockstep.]` **Spec baseline:** assumes the amended Section 2 (single-symbol FS14, four-limit FS3, percentile FS2) and fill-semantics option C2 (PS-side simulated fill latency; C1 execution reports as documented extension). All measured figures in this section were produced on the development sandbox against the real LOBSTER AAPL sample dataset (3.4.4.6); re-run on the target host before final submission `[EVIDENCE]`.  
> 模板约定： `[TEAM: …]` 需要团队决策支持； `[EVIDENCE: …]` 是一个需要测量分析的目标； `[REF-n]` 与本节末尾的参考文献相对应。图表命名：该子系统在图表中被命名为“主机上的交换模拟器（实时订单簿与执行器——1 个交易所/1 只股票）”；内部组件的名称分别为订单流程生成器（双驱动方式）、订单镜像、协议编码器、订单执行器（验证并记录）、场景引擎、真实数据记录器。 `[TEAM: keep headings and diagram labels in lockstep.]` 规范基线：基于修改后的第 2 节内容（单符号 FS14、四限 FS3、百分比 FS2）以及填充语义选项 C2（PS 端模拟填充延迟；C1 执行结果如文档所示）。本节中所有测量数据都是基于真实的 LOBSTER AAPL 样本数据集在开发沙盒中产生的；在最终提交前，这些数据已在目标主机上重新运行过 `[EVIDENCE]` 。

---

## 3.4.1 Overview and Specification Mapping  
3.4.1 概述与规格说明的映射

The Exchange Simulator is the counterparty to everything built in 3.1–3.3: it plays the exchange that the project objective requires but deliberately does not connect to (Section 1.2's paper-trading boundary). It runs on the host PC, terminates the far end of the point-to-point Gigabit Ethernet link into the PL (interfaces 1 and 4), generates the market-data event stream in the custom protocol of Table 3.1.4, maintains its own mirror of the resulting order book, and receives, validates, and logs every order packet the SoC emits (Table 3.1.5).  
交换模拟器是 3.1 至 3.3 版本中各个功能的对应组件：它负责执行项目目标所要求的交换操作，但刻意不与其他系统连接（参见 1.2 节的纸面交易边界说明）。该模拟器运行在用户的个人电脑上，终止了点对点千兆以太网连接中的两端设备（接口 1 和 4），使用表 3.1.4 中定义的自定义协议生成市场数据事件流，同时维护着订单簿的副本。此外，它还接收、验证并记录系统发出的每个订单数据包（表 3.1.5）。

**Positioning within the field.** Published end-to-end FPGA trading systems fall into a clear feasibility hierarchy defined by exchange access. At the top, Toshiba's two production systems ran live capital in the Tokyo Stock Exchange's JPX co-location facility [8], [9]; below them, Kao et al. connected to a real futures-broker test server for the Taiwan Futures Exchange, exercising genuine protocol handshakes without live capital [2]; at the laboratory tier, Boutros et al. validated their HLS pipeline by injecting UDP packets and capturing returned order packets in loopback [6], and Osuna et al.'s PYNQ-Z2 educational system replays market data from a host Python script [7]. AQTA belongs, by construction, to this laboratory tier: the co-location and broker-member access that define the upper tiers is unavailable to (and out of scope for) a capstone project. The design consequence is that this subsystem must supply, _by itself_, everything the upper tiers get from their environment — the market data, the counterparty, and the measurement fixture — which is why it is engineered as a first-class subsystem rather than a test script.  
在该领域内的定位方面，已发布的端到端 FPGA 交易系统遵循着由交易所访问权限所定义的明确可行性层级结构。在最上层，东芝公司的两个生产系统曾在东京证券交易所的 JPX 托管设施中运行实时交易[8][9]；在其之下，Kao 等人连接到了台湾期货交易所的真实期货经纪商测试服务器，实现了无需实时资金即可进行协议握手的操作[2]；在实验室层面，Boutros 等人通过注入 UDP 数据包并捕获返回的订单数据包来验证他们的 HLS 管道功能[6]，而 Osuna 等人的 PINQ-Z2 教育系统则能够重现来自主机 Python 脚本的市场数据[7]。根据设计原则，AQTA 属于这一实验室层面：对于最终项目而言，那些需要用到的高层功能，如托管服务和经纪商会员访问权限，是不具备的（且不在其实现范围内）。因此，这个子系统必须独自完成相关功能。上层结构从其所处的环境中获取的所有信息——比如市场数据、交易对手以及衡量标准等——这就是为什么它被设计成一种高级子系统，而不是一个简单的测试脚本。

**Dual identity.** Functionally, the simulator is the _exchange_: without it, no market data exists and the system under design has nothing to trade against. Its more demanding identity, however, is as the project's principal _verification instrument_: nearly every verification procedure in Section 2 — FS1's reference packet sequence, FS2's 1000-update measurement, FS13's captured-packet parse, NFS2's 10-minute frame count, NFS4's 6.5-hour session, NFS8's fault injections, NFS9's line-rate PCAP — names an input that only this subsystem can supply. A simulator that merely "produces plausible ticks" would satisfy the first identity and fail the second; the design therefore treats **reproducibility, controllability, and ground-truth observability** as first-class requirements, ahead of market realism. Where realism _is_ obtainable at zero marginal cost — via replay of a real order-level dataset (Decision 1) — the design takes it, but never at the expense of the instrument identity.  
双重身份。从功能上讲，模拟器扮演着交换器的角色：没有它，就不存在市场数据，而正在设计的系统也就没有可以用来交易的资产。不过，模拟器更重要的身份是作为项目的核心验证工具：第 2 节中几乎每一项验证程序——FS1 的参考数据包序列、FS2 的 1000 次更新测量、FS13 的数据包解析、NFS2 的 10 分钟帧数统计、NFS4 的 6.5 小时会话、NFS8 的错误注入、NFS9 的线速 PCAP 统计——都涉及到只有这个子系统才能提供的输入。如果一个模拟器只能“产生看似合理的记录”，那么它满足第一个条件，但无法满足第二个条件；因此，在设计过程中，可重复性、可控性以及可观测性被视为核心要求，优先于市场现实性。当现实主义能够以零边际成本获得时——通过重新处理真实的订单级数据集来实现（决策 1）——那么这种设计就是可行的。但这样做绝不会以牺牲工具的身份为代价。

Unlike 3.1–3.3, this subsystem is the _sole owner_ of few specifications — its ownership is instrumental:  
与 3.1–3.3 版本不同，这个子系统是少数几个规范的唯一拥有者——它的存在纯粹是为了实现某些功能而设计的。

|Spec  规格/参数|Simulator role  模拟器角色|
|---|---|
|**FS1, FS2**|Instrument: emits the reference packet sequences these measurements are defined against; ground-truth log provides transmit-side timestamps.  <br>仪器会发出用于这些测量的参考数据包序列；而实际记录则提供了传输端的时间戳信息。|
|**FS13**|Oracle: independently parses and validates every received order packet against the documented layout — a second implementation of the protocol spec, which is the strongest practical test of the spec document's completeness (a claim already vindicated during design: see the Modify-semantics finding in 3.4.4.6).  <br>Oracle：能够独立地解析并验证每个接收到的订单数据包，确保其符合规定的格式要求。这是协议规范中的第二种实现方式，它实际上是对规范文档完整性的最有力验证（这一说法在设计阶段就已经得到了证实：请参阅 3.4.4.6 中的“修改语义”部分）。|
|**NFS2**|Peer: the other endpoint of the 10-minute zero-drop window; its TX count is the expected-frame denominator.  <br>Peer：即 10 分钟零丢包窗口中的另一个端点；其发送帧的数量是预期的帧数分母。|
|**NFS4**|Provider: generates the full 6.5-hour session the SoC must survive.  <br>提供商负责提供完整的 6.5 小时会话时间，这是系统必须能够持续运行的时长。|
|**NFS8**|Injector: produces the corrupted-checksum packets and over-depth bursts the fault-handling tests require.  <br>注入器：负责生成带有损坏校验和的数据包，并执行所需的过度深度故障处理测试。|
|**NFS9**|Injector: supplies the synthesized line-rate PCAP the throughput test specifies.  <br>喷射器：负责提供按照测试要求指定的线速 PCAP 数据。|
|**FS6/FS7 (bootstrap)  FS6/FS7（启动模式）**|Data source: before any live sessions exist, recorded simulator sessions are the backtest corpus (3.3 Decision 4's bootstrap case) and the regime-classifier exercise data.  <br>数据来源：在没有任何实际会话存在之前，所记录的模拟器会话数据构成了回测的基础（参见 3.3 节中关于决策树方法的示例），此外还有 regime 分类器的练习数据也被用作数据来源。|
|**NFS3**|The simulator is pure software on the host PC, which NFS3 explicitly excludes from the cost cap — subsystem hardware cost is $0.  <br>该模拟器完全是在主机电脑上运行的软件系统，而 NFS3 明确将模拟器排除在成本限制之外——模拟器的硬件成本为零。|

Figure 3.6 shows the simulator's internal structure and its two link-level interfaces. _(Figure placeholder — component diagram: Scenario Engine → Order-Flow Generator [synthetic driver | LOBSTER-replay driver] → [Book Mirror, Protocol Encoder → EventSink: UDP TX | PCAP writer]; UDP RX → Order Executor → Ground-Truth Logger; all components writing to the Ground-Truth Logger.)_  
图 3.6 展示了模拟器的内部结构以及其两个链路级接口。 (图占位符——组件图：场景引擎→订单流程生成器[合成驱动|LOBSTER 重放驱动]→书籍镜像器、协议编码器→事件接收器：UDP 传输|PCAP 写入器；UDP 接收器→订单执行器→真实情况记录器；所有组件都向真实情况记录器写入数据。)

---

## 3.4.2 Engineering Design Process  
3.4.2 工程设计流程

### Decision 1 — Market-data source: a four-iteration design history  
决策 1——市场数据来源：一个包含四次迭代的设计历史记录

This decision went through four documented iterations driven by successively discovered external constraints; each reversal is retained because the constraints, not preferences, did the deciding.  
这个决策过程经历了四次迭代，每次迭代都是基于不断发现的外部约束条件来进行的。每一个决策结果都被保留下来，因为决定最终还是由这些约束条件而非个人偏好所决定的。

**Iteration 1 — broker paper-trading account as the exchange (initial concept, rejected).** The most "real" option available to the team: use a retail broker's simulated-trading environment (Interactive Brokers, Webull, Futu-class APIs) as the live counterparty, so the SoC trades real market data with fake money. Three structural mismatches killed it. (1) _Interface_: broker APIs are REST/WebSocket sessions to the broker's cloud, with latencies in the tens-of-milliseconds-to-seconds class — they cannot terminate our point-to-point PL GbE link or speak the FS13/Table-3.1.4 custom UDP protocol, so the entire PL path (the project's core) would be untestable against them. (2) _Controllability_: no broker will emit a corrupted-FCS frame or a line-rate microburst on request — every NFS8/NFS9 verification procedure becomes unimplementable. (3) _Reproducibility_: live market data is unrepeatable by definition; a failed FS2 run could never be re-run on identical input.  
迭代 1——将经纪商的交易账户作为交易对手方（初始想法，被否决）。团队可选择的“最现实”方案是使用零售经纪商的模拟交易环境（如 Interactive Brokers、Webull 等，具备 Futu 级 API 功能）作为实际交易对手方，这样 SoC 就可以用虚拟资金进行真实市场数据的交易。不过，存在三个结构性问题阻碍了这一方案的实施：(1) 接口问题：经纪商提供的 API 是通过 REST/WebSocket 与经纪商云端的连接，其延迟达到数十毫秒到几秒级别——它们无法终止我们的点对点 PL GbE 连接，也无法使用 FS13/Table-3.1.4 自定义 UDP 协议，因此整个交易对手方机制将无法进行测试。(2) 可控性问题：没有任何经纪商会发出损坏的 FCS 帧或根据请求产生线速率波动——所有 NFS8/NFS9 级别的验证流程都无法实施。(3) 可重复性：实时市场数据本质上是不可重复的；如果 FS2 的运行失败，那么就无法在相同的输入条件下再次运行了。

**Iteration 2 — the granularity ceiling (real-data ambitions narrowed by evidence).** Rejecting the broker _interface_ did not settle whether real market _data_ could still drive the simulator. Investigating this surfaced a harder constraint: the custom protocol carries **L3 order-level events** (Add/Modify/Delete keyed by `order_id`, Table 3.1.4), but retail-tier APIs top out at **L2**. Interactive Brokers' own documentation defines its market-depth product as "level II," delivered as _aggregated price-level rows_ (position/operation/price/size callbacks) with no order identifiers [10] — and depth subscriptions are per-venue paid market-data lines whose availability on paper accounts is itself conditional. The published record confirms this is a structural boundary, not a shopping failure: the one cited system that operated against genuine order-level exchange messaging below the co-location tier did so through a _futures-broker member test server_ [2], and He et al.'s order-book-update work drew CFFEX message streams from the exchange's internal unified data bus — access mediated by an institutional research relationship, not a public endpoint [3]. No tier of the literature obtains L3 through a retail channel, because no retail channel carries it.  
第二次迭代——粒度上限的问题（基于实际数据的目标因证据不足而有所调整）。放弃使用经纪商接口并不能确定真实市场数据是否仍然能够驱动模拟器。进一步研究后，我们发现了一个更严格的限制：自定义协议会处理 L3 级别的订单级事件（如添加、修改、删除等，这些事件由 `order_id` 标识），但零售级 API 的最大功能仅限于 L2 级别。Interactive Brokers 自己的文档中将其市场深度功能定义为“二级市场”，该服务以聚合的价格级数据形式提供（如仓位、操作、价格、数量等详细信息），且不包含订单标识符[10]。而市场深度功能实际上是通过各个交易所提供的付费市场数据线来实现的，而这些数据的可用性在模拟账户中也是有条件的。已有的记录表明，这是一个结构性限制，而非技术上的缺陷：有记录表明，那些能够处理低于托管层级别的订单级交换消息的系统，是通过期货经纪商测试服务器来实现的[2]，而 He 则……“等”的订单更新工作是通过 CFFEX 的交易所内部统一数据总线来完成的——这种访问方式是通过机构间的合作关系来实现的，而不是通过公共端点进行的[3]。在文献中，没有任何一篇作品是通过零售渠道获得 L3 级别的资源的，因为根本不存在这样的零售渠道。

**Iteration 3 — real L3 exists after all, behind a price wall with a free crack (the LOBSTER discovery).** The academic market-microstructure community solved exactly this access problem a decade ago: LOBSTER reconstructs order-level limit-order-book data — every submission, cancellation, deletion, and execution, keyed by order ID — for the entire NASDAQ universe from Historical TotalView-ITCH files [11], and has served as the community's standard source since 2013. Full access is a paid academic subscription (published price list: £6,897/year [12]) — out of the question for a capstone. But LOBSTER publishes **free official sample files** [13]: one full trading day (2012-06-21) for AAPL, AMZN, GOOG, INTC, and MSFT at 1/5/10/30/50 book levels, each comprising a `message` file (time, type, order ID, size, price, direction — the L3 event stream itself) and a level-by-level `orderbook` snapshot file. One day of five symbols cannot be a _production data source_, but it is exactly sufficient for what the instrument identity actually needs from real data: a ground-truth check that the protocol, the translation semantics, and the generator's statistical assumptions survive contact with a real order flow. (The team notes, without needing it as evidence, that published FPGA order-book work has used this same sample day and ticker set — e.g., the MSFT 2012-06-21 dataset in [14].)  
第三次迭代——实际上，L3 确实存在。它隐藏在价格墙之后，但有一个免费的通道可以访问它（即 LOBSTER 的发现）。学术界的市场微观结构研究社区在十年前就解决了这个访问问题：LOBSTER 重新构建了整个纳斯达克市场的订单级限价单数据——包括所有提交、取消、删除和执行操作，这些数据以订单 ID 为键，存储在 Historical TotalView-ITCH 文件中[11]。自 2013 年以来，LOBSTER 一直作为该领域的标准数据源。完全访问该数据需要付费的学术订阅服务（价格：每年 6,897 英镑[12]）——对于顶石项目来说，这是无法实现的。不过，LOBSTER 提供了免费的官方样本文件[13]：包括 AAPL、AMZN、GOOG、INTC 和 MSFT 股票在 2012 年 6 月 21 日这一完整交易日的限价单数据。每个限价单数据包含 `message` 文件（包含时间、类型、订单 ID、数量、价格和方向等详细信息，即 L3 事件流本身），以及 `orderbook` 级别的快照文件。五天内的数据样本并不能作为生产数据的来源，但这恰恰满足了仪器识别系统对真实数据需求的必要条件：即需要验证协议、转换语义以及生成器的统计假设在面对真实订单流时依然有效。团队指出，无需任何证据即可证明，已有的基于 FPGA 的订单簿系统中确实使用了类似的样本数据和股票代码集——例如，[14]中提到的 MSFT 2012-06-21 数据集。

**Iteration 4 — final architecture: one generator, two drivers.** The end state is not a choice between synthetic and real data but a role assignment:  
迭代 4——最终架构：一个生成器，两个驱动程序。最终的状态不是要在合成数据和真实数据之间做出选择，而是要对角色进行分配：

|Driver  司机|Role  角色|Rationale  理由/依据|
|---|---|---|
|**Seeded synthetic driver** (verification mode — primary)  <br>种子合成驱动程序（验证模式——主要用途）|Sole input source for every Section 2 verification procedure: FS1/FS2 reference sequences, NFS8 fault injection, NFS9 line-rate PCAPs, NFS4 soak sessions, FS6/FS7 bootstrap corpus  <br>每个第 2 节验证程序的唯一输入来源包括：FS1/FS2 参考序列、NFS8 故障注入、NFS9 线路速率 PCAP 数据、NFS4 浸泡测试会话，以及 FS6/FS7 引导语料库。|Deterministic (same seed ⇒ bit-identical byte stream, measured in 3.4.4.3), unlimited-volume, scriptable faults and bursts — properties no recorded dataset can offer. Its statistical parameters (event mix, burst profile) are **calibrated from the real dataset** (3.4.4.6), so "synthetic" no longer means "guessed."  <br>确定性（相同的种子值产生相同的字节流，参见 3.4.4.3 节描述）、无限容量、可脚本化的故障和突发事件——这些特性是任何已记录的数据集都无法实现的。其统计参数（事件组合、突发事件特征）都是基于真实数据集进行校准的（参见 3.4.4.6 节），因此“合成”一词不再意味着“猜测”。|
|**LOBSTER-replay driver** (validation mode — one-shot and regression)  <br>龙虾重放驱动程序（验证模式——一次性执行和回归测试）|Replays the real AAPL sample day through the identical Protocol Encoder and EventSink; used to validate protocol/translation semantics against real order flow and to provide one real-data session for demonstration  <br>通过相同的协议编码器和事件处理器，重新模拟了真实的 AAPL 样本日场景；这些工具可用于验证协议/翻译的语义准确性，同时还能提供一个真实的数据会话以进行演示。|Real data used where realism is the point; excluded from spec verification because a single fixed day offers no fault injection, no rate control, and no volume scaling  <br>在需要真实性的情况下使用了实际数据；由于单一固定的日期无法实现故障注入、速率控制以及流量规模调整等功能，因此这些数据未被用于规格验证。|

Both drivers emit through the same abstract `EventSink` (socket / PCAP-writer), so everything downstream — encoder, book mirror, logger, PL — is provably indifferent to the driver. This iteration history is also the origin of two protocol-level findings (sub-penny prices; Modify-semantics ambiguity) reported in 3.4.4.6 — discoveries that would not have occurred under Iteration 1's architecture and that alone justify the investigation's cost.  
这两个驱动程序都通过同一个抽象接口 `EventSink` 进行通信（即套接字/PCAP 写入器）。因此，所有下游组件——编码器、日志器、PL 等——实际上都对该驱动程序没有特殊要求。这一迭代历史也是两个协议层面问题的根源，这些问题在 3.4.4.6 中有详细描述：极低的价格水平，以及修改语义时的模糊性。这些问题在迭代 1 的架构下是不可能出现的，而这恰恰证明了进行这项研究的合理性。

### Decision 2 — Execution model: full matching engine vs. validate-and-log executor under a no-impact assumption  
决策 2——执行模型：完全匹配引擎与在无影响假设下的验证与记录执行器。

|Alternative  替代方案|Description  描述|Outcome  结果|
|---|---|---|
|Full price-time-priority matching engine  <br>全时优先级匹配引擎|Received orders rest in the simulator's book, match against generated flow, and produce fills; our orders alter the market-data stream.  <br>我们收到的订单会被记录在模拟器的记录中，然后与生成的交易流进行匹配，最终完成交易执行；我们的订单会改变市场数据流。|**Rejected for the prototype.** A matching engine is a substantial correct-by-construction artifact (price-time priority, partial fills, self-match handling) whose output — realistic fills and market impact — no Section 2 specification consumes. Under the C2 fill-semantics decision, fill timing is modeled PS-side; the simulator does not need to adjudicate fills at all. The cost would be large, the verification burden larger (the matching engine would itself need a test bench), and the marks zero.  <br>该原型被否决了。匹配的引擎是一种明显的构造性错误——比如价格优先、部分填充、自匹配处理等功能。其产生的结果——即真实的填充过程和市场影响——根本不受到任何规范要求的约束。根据 C2 填充语义的决策，填充时机在 PS 端就已经被建模好了；模拟器无需再对填充过程进行任何判断。不过，这样做会带来较大的成本负担，验证工作也会更加复杂（因为匹配引擎本身就需要一个测试平台来进行测试），而且其效果几乎为零。|
|Validate-and-log executor, no-impact assumption (selected)  <br>验证并记录执行器，无影响假设（可选）|Every received order packet is parsed against the FS13 layout, checksum-verified, range-checked, timestamped, and logged; the generated market-data stream is **not** altered by received orders.  <br>每个接收到的订单数据包都会根据 FS13 格式进行解析，检查校验和、范围有效性，添加时间戳，并记录相关信息。生成的市场数据不会因接收到的订单而受到任何修改。|**Selected.** This is exactly the FS13 oracle role: an independent second implementation of the protocol parse is the strongest practical check of the spec document (any ambiguity in Table 3.1.5 surfaces as a disagreement between the PL encoder and the simulator parser — at which point the _document_ gets fixed, which is FS13's actual point; 3.4.4.6 records this mechanism already firing once on the RX-side table during design). The no-impact assumption is stated openly as a modeling boundary: with FS3 capping orders at 1,000 shares against a book quoting thousands of shares per level, self-impact would be second-order even if modeled. `[TEAM: state the no-impact assumption in the report's limitations paragraph; it is a deliberate scope cut, not an oversight.]`  <br>已选中。这正是 FS13 中的预言性功能：对协议解析的独立二次执行，实际上是一种最强有力的实践验证方式——表 3.1.5 中的任何模糊之处，都会表现为 PL 编码器与模拟器解析器之间的分歧；此时文档就会得到修正，而这正是 FS13 的核心所在；3.4.4.6 中已经记录了这种设计在接收端表格中一次执行该机制的情况。无影响假设被明确作为建模的边界条件：在 FS3 中，订单的数量上限为 1000 份股份，而书籍中的每级股份数量则高达数千份，因此即使进行建模，这种自影响现象也会是次要问题。 `[TEAM: state the no-impact assumption in the report's limitations paragraph; it is a deliberate scope cut, not an oversight.]`|

**The closed-loop caution from the literature.** The survey of deployed systems is blunt about open-loop order emission: only the Toshiba production systems close the post-trade loop, pairing the FPGA's inline order path with CPU-side order confirmation and position-state management [8], [9] — because an exchange-facing device that fires orders without tracking their disposition carries unbounded exposure. AQTA's architecture already embodies this division: the PS-side Runtime Risk Guard and open-order table (3.2.3.3, amended FS3/FS14) are the CPU-side state machine, and the C2 fill model closes the loop in simulation. If fill semantics are later upgraded to C1, the executor gains exactly one behavior — emit a `msg_type 0x04` execution report over the same link after a configurable delay — without touching the generator or book mirror; the decision structure deliberately leaves that seam open.  
文献中的闭环警示信息表明，对于开放式订单执行流程，目前只有东芝公司的生产系统实现了订单处理后的闭环操作。这些系统将 FPGA 端的订单处理流程与 CPU 端的订单确认及头寸状态管理流程相结合[8][9]——因为如果没有对订单的处理过程进行跟踪，那么面向交易市场的设备就会面临无限的风险。AQTA 的架构已经体现了这种分治思想：PS 端的运行时风险防护机制以及开放式订单表（3.2.3.3，参见 FS3/FS14）构成了 CPU 端的状态机；而 C2 填充模型则通过仿真实现了闭环操作。如果后续将填充语义升级到 C1 级别，那么执行器将仅能在一个可配置的延迟之后，通过同一链接发送一份 `msg_type 0x04` 执行报告——而无需触及生成器或账簿镜像；这种决策结构故意保留了这种开放性的可能性。

### Decision 3 — Rate architecture: one online generator for everything, or an offline-generate / online-replay split  
决策 3——费率架构：要么采用全在线生成的方式来处理所有业务，要么采用离线生成与在线回放相结合的方案。

This decision was forced by measurement, not preference. The subsystem faces two rate regimes separated by roughly five orders of magnitude: _session mode_ (a realistic trading day — measured on the real dataset at an average of **17.1 msg/s** with a peak 100 ms burst equivalent to **2,390 msg/s**; 3.4.4.6) and _stress mode_ (NFS9's full wire-speed injection at 1.389 M packets/s, the 3.1.4.1 ceiling).  
这个决策是基于测量结果而做出的，而非基于偏好。该子系统面临两种不同的速率模式，这两种模式的差异大约达到了五个数量级：会话模式（在真实的交易日内，平均每秒发送 17.1 条消息，峰值可达 100 毫秒的发送量，相当于每秒 2,390 条消息；3.4.4.6）和压力模式（NFS9 的全线速注入模式，每秒可发送 1.389 百万条消息，即 3.1.4.1 的上限）。

Microbenchmarks on the development sandbox (3.4.4.1) measured the Python online path at: UDP `sendto` alone ≈ **450 K pps**; event generation + protocol encode alone ≈ **91 K events/s**; combined generate-and-send ≈ **143 K events/s**. Two conclusions follow. First — and contrary to the initial working assumption that the socket would be the bottleneck — **generation is the slower half**: no amount of socket optimization (sendmmsg batching, raw sockets) reaches line rate, because the entire online path is structurally ~~10× short of 1.389 M pps at the generation stage. Second, session mode has enormous headroom: 143 K events/s measured capability against a real-data peak burst of 2,390 msg/s is a **~~60× margin at the burst peak and ~8,000× at the session average** — single-threaded Python is comfortably sufficient.  
在开发沙盒上的微基准测试（3.4.4.1）中，测量到的 Python 在线处理速度如下：单线程时约 450 千次每秒；仅事件生成和协议编码时约 91 千次每秒；结合生成和发送操作时约 143 千次每秒。由此可以得出两个结论。首先，与最初认为 socket 会成为瓶颈的假设相反，实际上的较慢环节是事件生成阶段：尽管进行了各种 socket 优化（如 sendmmsg 批处理、使用原始 socket 等），但整体在线处理速度仍仅为 13.89 万次每秒的十分之一。其次，会话模式具有巨大的扩展空间：143 千次每秒的处理能力可以应对 2,390 次每秒的峰值需求，在峰值时刻有**60 倍的余量**，而在会话模式下则可以达到 1,001 倍每秒的速率——单线程 Python 就足以满足需求了。

|Alternative  替代方案|Description  描述|Outcome  结果|
|---|---|---|
|Single online generator (Python)  <br>独立的在线生成器（使用 Python 语言编写）|One process serves both modes.  <br>有一个进程可以同时支持两种模式。|**Rejected by measurement** — 143 K events/s < 1.389 M pps by ~10×.  <br>由于测量结果不合格——143 K 事件/秒 < 1.389 M pps，由~10×得出。|
|Single online generator (rewrite in C)  <br>独立的在线生成器（用 C 语言编写的）|Port the generator to C for line rate.  <br>将发电机移动到 C 点，以调整线路速率。|**Rejected.** Buys speed session mode doesn't need to serve a stress mode with a cheaper structural answer (below); reintroduces the productivity cost the Python selection avoids; and NFS9's verification procedure _already specifies_ PCAP injection, not live generation.  <br>被拒绝。购买快速会话模式并不需要采用一种成本更低的解决方案；需要重新考虑 Python 选择所忽略的生产效率成本问题；而且 NFS9 的验证流程已经包含了 PCAP 注入机制，而不是实时生成数据。|
|**Offline-generate / online-replay split (selected)  <br>离线生成/在线回放混合模式（可选）**|The generator gains a second output backend: instead of a socket, it writes the identical byte stream into a **PCAP file offline** (where generation speed is irrelevant). Stress mode replays that PCAP at line rate with a dedicated replay tool (`tcpreplay --topspeed` class `[EVIDENCE: verify the chosen tool + host NIC sustain 1.389 M pps of 90 B frames; fallback: a minimal AF_PACKET/sendmmsg C blaster — ~100 lines, far smaller than a C generator]`).  <br>该生成器有了第二种输出方式：它不再使用套接字进行传输，而是将相同的字节流写入到 PCAP 文件中进行离线处理（在这种情况下，生成速度并不重要）。在压力测试模式下，可以通过专门的回放工具以线速速率播放这些 PCAP 文件。（ `tcpreplay --topspeed` 类 `[EVIDENCE: verify the chosen tool + host NIC sustain 1.389 M pps of 90 B frames; fallback: a minimal AF_PACKET/sendmmsg C blaster — ~100 lines, far smaller than a C generator]` ）|**Selected.** The split assigns each requirement to the regime where it is easy: correctness and determinism live in the offline generator (slow, rich, testable Python); raw rate lives in the replayer (dumb, fast, semantically empty). This mirrors NFS9's own verification wording and is the standard test-bench pattern of separating stimulus _synthesis_ from stimulus _injection_.  <br>已选中。这种划分方式将每个功能分配给执行起来较为容易的子系统： correctness 和 determinism 属于离线生成器部分（速度较慢，功能丰富，适合用 Python 进行测试）；而 raw rate 则属于重放器部分（效率较高，但语义较为简单）。这种处理方式与 NFS9 的验证方式一致，也是将刺激生成与刺激注入分离的标准模式。|

**A semantic honesty note on stress mode.** A looped or pre-generated line-rate PCAP is a _throughput_ test, not a _semantic_ test: at 1.389 M pps the PS-side conflation means virtually no snapshot is individually observed, and if the PCAP is looped, `order_id` sequences repeat and book state ceases to be meaningful. That is acceptable — NFS9's pass criterion is drop-counter deltas, not book correctness — but the report must say so explicitly rather than imply the stress run exercises trading semantics. `[TEAM: PCAP sizing choice in 3.4.4.2 — single long file vs. looped short file.]`  
关于压力模式语义的说明。循环或预先生成的线速率 PCAP 属于吞吐量测试，而非语义测试：在 1.389 M pps 的速率下，PS 端的合并操作意味着几乎没有任何快照被单独观察。而如果 PCAP 是循环使用的，那么 `order_id` 序列会重复出现，此时“书状态”也就不再具有意义了。这是可以接受的——NFS9 的通过标准是减少计数器差值，而非确保“书状态”的正确性——但报告必须明确说明这一点，而不是暗示压力测试过程中语义被交换了。 `[TEAM: PCAP sizing choice in 3.4.4.2 — single long file vs. looped short file.]`

### Decision 4 — Test controllability: hardcoded test modes, interactive control, or declarative scenario files  
决策 4——测试可控制性：采用硬编码的测试模式、交互式控制方式，或者声明式场景文件。

|Alternative  替代方案|Description  描述|Outcome  结果|
|---|---|---|
|Hardcoded test modes  硬编码的测试模式|Compile/flag-selected behaviors (`--test-nfs8-checksum`, …).  <br>汇总/标记选定的行为（ `--test-nfs8-checksum` , …）。|**Rejected.** Every new verification case is a code change; combinations (burst _during_ a fault) need their own flags; the mapping from Section 2 procedures to simulator behavior lives in code nobody reads.  <br>被拒绝。每一个新的验证案例都涉及到代码的修改；那些在故障发生时可能出现的组合情况也需要单独进行标记；第 2 节中描述的流程与模拟器行为的对应关系则存在于代码中，但没人会去阅读这些代码。|
|Interactive control (live console)  <br>互动控制（实时控制台）|Operator triggers faults manually during a run.  <br>在运行过程中，操作员手动触发了故障。|**Rejected as the primary mechanism.** Manual timing is unreproducible — the exact property Decision 1 exists to provide. Retained as a debug convenience only.  <br>该方案被否决，因为它并非理想的解决方式。手动计时方式难以复现——而 Decision 1 方案能够解决这一问题。因此，该方案仅作为调试用途而保留下来。|
|**Declarative scenario files (selected)  <br>声明性场景文件（已选择）**|The session config JSON (3.4.3.3) carries a `scenario` array: timestamped directives (`at t=120s: corrupt_fcs count=1`, `at t=300s: burst rate=line duration=50ms`, `at t=600s: malformed_field msg_type=0x07`). The Scenario Engine splices these into the generated stream at the protocol-encoder stage.  <br>会话配置 JSON 数据（3.4.3.3）包含一个 `scenario` 数组，其中包含带有时间戳的指令（ `at t=120s: corrupt_fcs count=1` 、 `at t=300s: burst rate=line duration=50ms` 、 `at t=600s: malformed_field msg_type=0x07` ）。场景引擎会在协议编码阶段将这些指令整合到生成的流中。|**Selected.** Each Section 2 verification procedure becomes a **checked-in artifact**: `scenario_nfs8_fcs.json`, `scenario_nfs9_linerate.json`, `scenario_fs2_reference_1000.json` — reviewable, diffable, re-runnable, and cited directly from the verification write-ups. The verification plan stops being prose and becomes configuration.  <br>已选中。每个第二部分验证流程都成为了一个可检出的工件： `scenario_nfs8_fcs.json` 、 `scenario_nfs9_linerate.json` 、 `scenario_fs2_reference_1000.json` ——这些都可以进行评审、修改、重新运行，并且可以直接从验证报告中引用。验证计划不再只是文字描述，而是变成了具体的配置方案。|

---

## 3.4.3 Final Design Details  
3.4.3 最终设计细节

### 3.4.3.1 Component structure and data flow  
3.4.3.1 组件结构与数据流向

One Python process, six components, one thread on the hot path `[TEAM: confirm single-threaded is sufficient given 3.4.4.1 margins; it simplifies determinism reasoning]`:  
一个 Python 进程，包含六个组件，以及一个处于热点路径上的线程 `[TEAM: confirm single-threaded is sufficient given 3.4.4.1 margins; it simplifies determinism reasoning]` ：

1. **Scenario Engine** — loads the session config; owns the master event clock; interleaves scheduled scenario directives with driver output.  
    情景引擎——负责加载会话配置；拥有主事件时钟；能够将预定的情景指令与驱动程序的输出相结合。
2. **Order-Flow Generator (dual-driver)** — either the _synthetic driver_ (steps the midprice process and order-arrival process from the seeded PRNG) or the _LOBSTER-replay driver_ (streams the real message file through the translation layer of 3.4.4.6, after a book-priming step for pre-session orders). Both emit abstract L3 events that are always consistent with the Book Mirror's state (invariant I1, 3.4.4.4).  
    订单流生成器（双驱动方式）——可以使用合成驱动程序（对中等价过程及订单到达过程进行模拟），也可以使用 LOBSTER 重放驱动程序（在会话前订单生成步骤之后，将真实消息文件通过 3.4.4.6 版本的翻译层进行流式处理）。这两种驱动方式都会产生与图书镜像状态始终一致的抽象 L3 事件（不变式 I1，3.4.4.4）。
3. **Book Mirror** — applies each emitted event to the simulator's own copy of the book; this is the ground-truth book against which the PL's order-book construction (3.1) is verified.  
    图书镜像——将每个产生的事件应用到模拟器自身所拥有的图书副本上；这就是用于验证 PL 的订单簿构建方式（3.1）的基准图书。
4. **Protocol Encoder** — packs events into the Table 3.1.4 layout.  
    协议编码器——将事件打包到表 3.1.4 的布局中。
5. **EventSink** — the abstract output seam: UDP TX over the point-to-point link (session/validation modes) or PCAP writer (offline stress-generation mode). Same bytes either way (verified property, 3.4.4.3).  
    EventSink——一个抽象的输出接口：可以通过点对点链接使用 UDP 传输数据（在会话/验证模式下），或者采用 PCAP 格式进行离线压力测试模式下的数据输出。无论采用哪种方式，输出的字节数都是相同的（已验证过此特性，参见 3.4.4.3 章节）。
6. **Order Executor (validate-and-log) + Ground-Truth Logger** — parses every received order packet against Table 3.1.5 (FS13 oracle), checksum-verifies, and appends to the ground-truth log; the logger also records every transmitted event with a host timestamp.  
    订单执行器（负责验证和记录）+ 事实记录器——会逐一解析接收到的订单数据包，依据表 3.1.5（FS13 预言机）进行校验和验证，然后将结果添加到事实记录中；该记录器还会记录每个传输事件的时间戳。

### 3.4.3.2 Order-flow model (synthetic driver)  
3.4.3.2 流量模型（合成驱动因素）

The synthetic driver's realism target is deliberately modest — _statistically plausible, structurally valid_ L3 flow, calibrated against the real dataset rather than guessed:  
这种合成驾驶器的逼真度目标被设定为适度偏低——所采用的技术在统计上可行，结构上也有效，并且是根据真实数据集进行校准的，而不是通过猜测来确定的。

|Element  元素|Model|Rationale  理由/依据|
|---|---|---|
|Midprice  中间价格|Integer-cents random walk with configurable drift and step-volatility per regime segment `[TEAM: plain walk vs. OU mean-reversion for RANGING segments — OU is a one-line change and makes RANGING segments genuinely range-bound]`  <br>具有可配置漂移和每段时期步幅-波动率的整数概率随机行走过程 `[TEAM: plain walk vs. OU mean-reversion for RANGING segments — OU is a one-line change and makes RANGING segments genuinely range-bound]`|Integer cents end-to-end (matches the PL/PS integer commitment); regime parameters per segment let one session exercise all three 3.3 regimes  <br>整数 cents 端到端支持（与 PL/PS 整数承诺方式相匹配）；每个片段的体制参数允许在一个会话中同时应用这三种体制。|
|Order arrivals  订单已送达|Poisson-clocked event stream; mix ratio calibrated from the real sample: **Add ≈ 48%, Delete ≈ 43%, Modify/partial ≈ 3%, executions ≈ 6%** (measured, 3.4.4.6) `[TEAM: confirm; the earlier working figures of 55/25/20 are superseded — real flow is add/delete-dominated with rare modifies]`; prices placed within ±10 levels of mid `[TEAM: distribution]`  <br>基于泊松分布的事件流；混合比例根据真实样本数据进行校准：添加约 48%，删除约 43%，修改/部分修改约 3%，执行操作约 6%（测量值，3.4.4.6 节） `[TEAM: confirm; the earlier working figures of 55/25/20 are superseded — real flow is add/delete-dominated with rare modifies]` ；价格波动在±10 个等级范围内 `[TEAM: distribution]`|Keeps the 10-level PL book window (3.1 Decision 4) exercised, including deliberate out-of-window events to hit the `dropped_out_of_window` counter  <br>保留了 10 级 PL 手册中的窗口操作（3.1 决策 4），包括故意制造窗口外事件以触发 `dropped_out_of_window` 计数器。|
|Rate profile  利率档案|Piecewise-constant base rate with scheduled bursts; realistic envelope anchored to measured data (session average ~17 msg/s, burst peaks ~2.4 K msg/s; open/close activity concentration)  <br>分段恒定的基础速率，结合定时爆发的模式；真实的信封式数据分布，基于实测数据进行调整（会话平均值为 1001#17 条消息/秒，爆发时的峰值达到 1002#2.4 千条消息/秒；开放/关闭活动的集中程度也根据数据进行调整）|NFS2/NFS4 realism; NFS8 FIFO-overflow injection requires bursts far above the realistic envelope, which the scenario engine supplies  <br>NFS2/NFS4 现实主义模型；而 NFS8 中的 FIFO 溢出注入机制则要求产生的脉冲强度远远超过场景引擎所能提供的现实极限值。|
|Regime schedule  制度时间表|Session config declares segments: `[{t: 0, regime: RANGING}, {t: 2h, regime: VOLATILE}, …]` mapping to (drift, vol, rate) parameter sets  <br>会话配置声明了几个段： `[{t: 0, regime: RANGING}, {t: 2h, regime: VOLATILE}, …]` 这些段对应着 (drift, vol, rate) 参数集。|Generates labeled sessions → the 3.3 classifier can be tested against _known_ ground-truth regimes, a stronger test than unlabeled real data `[TEAM: add to 3.3's verification plan — classifier accuracy against simulator-labeled segments]`  <br>生成带有标签的测试数据 → 可以针对已知的真实标签数据集来测试 3.3 分类器，这种测试方法比使用未标注的真实数据要有效得多 `[TEAM: add to 3.3's verification plan — classifier accuracy against simulator-labeled segments]`|

### 3.4.3.3 Session configuration and ground-truth log  
3.4.3.3 会话配置和实际日志记录

**Session config (JSON):** `{driver: synthetic|lobster_replay, seed | dataset_path, duration_s, symbol_id, initial_mid_cents, regime_schedule[], rate_profile[], scenario[]}`. Under the synthetic driver, the seed _is_ the session: config + generator version ⇒ bit-identical byte stream (3.4.4.3), so a session is _named_ by its config file, and every verification run cites one. Under the replay driver, the dataset file hash plays the same role.  
会话配置（JSON 格式）：在合成驱动下，会话的种子就是会话配置与生成器版本的合并结果——即两个流在字节层面上是完全一致的（3.4.4.3）。因此，会话的名称取决于其配置文件，每次验证运行时都会使用同一个配置文件。在重放驱动下，数据集文件的哈希值也起到相同的作用。

**Ground-truth log (append-only, one line per event):** `{host_ts_ns, dir: TX, raw_bytes_hex, decoded_fields, book_top_after}` for TX; `{host_ts_ns, dir: RX, raw_bytes_hex, parse_result, fault_code?}` for RX. This log is the **golden reference** the other subsystems' logs are diffed against: the PL's book (via PS snapshots in the FS5 export) against `book_top_after`; PS decision timestamps against TX/RX host timestamps for the FS2/NFS1 cross-checks (single host clock covers both directions; Wireshark on the same NIC remains the primary instrument, the ground-truth log the redundant second witness). `[TEAM: log volume trade — full raw_bytes_hex at high rates is large (3.4.4.5); default ON for verification sessions, OFF for soak runs.]`  
基础日志（仅追加数据，每个事件占一行）： `{host_ts_ns, dir: TX, raw_bytes_hex, decoded_fields, book_top_after}` 用于发送端日志； `{host_ts_ns, dir: RX, raw_bytes_hex, parse_result, fault_code?}` 用于接收端日志。这个日志是其他子系统日志对比的基准参考文件：通过 FS5 导出中的 PS 快照，可以对比 `book_top_after` ；PS 的决策时间戳可以与发送/接收端的主机时间戳进行交叉验证，以实现 FS2/NFS1 的校验（同一主时钟适用于双向通信；同一网卡的 Wireshark 仍然是最重要的监控工具，而基础日志则作为额外的第二验证手段）。 `[TEAM: log volume trade — full raw_bytes_hex at high rates is large (3.4.4.5); default ON for verification sessions, OFF for soak runs.]`

### 3.4.3.4 Link and host configuration  
3.4.3.4 链接与主机配置

Host NIC directly cabled to the PL RJ45 (no switch — NFS2's "no unexplained drops" argument depends on this), static IP/MAC matching the PL's compile-time constants (3.1.3.1), UDP checksum emitted as zero (per 3.1.3.1's accept-zero decision — the PL parser ignores the field). The simulator host may be the same physical machine as the EOD server `[TEAM: confirm — separate processes either way; nothing couples them intraday]`. Wireshark/tcpdump capture on this NIC is the shared instrument for FS2/NFS1/NFS2 procedures.  
主机网络接口直接连接到 PL 的 RJ45 接口（无需交换机——NFS2 的“避免无理由丢弃”策略正是基于这一点），静态 IP 地址和 MAC 地址与 PL 在编译时定义的常量相匹配（3.1.3.1）。UDP 数据包的校验和值为 0（根据 3.1.3.1 中的规定，可以接受值为 0 的情况——PL 解析器会忽略该字段）。模拟器主机可以与 EOD 服务器的物理机器相同。通过 Wireshark/tcpdump 对这台网络接口进行的捕获数据，可用于 FS2/NFS1/NFS2 程序的测试。

---

## 3.4.4 Quantitative Technical Analysis  
3.4.4 定量技术分析

### 3.4.4.1 Session-mode rate capability — measured  
3.4.4.1 会话模式速率能力——已测量

Microbenchmarks on the development sandbox (Python 3, loopback socket, 20–24 B payloads; caveats: loopback ≠ real NIC path, sandbox ≠ target host — order-of-magnitude evidence `[EVIDENCE: re-run on target host]`):  
在开发沙盒上的微基准测试（使用 Python 3 语言，基于循环回送套接字模型，处理 20–24 字节的数据负载；注意：循环回送套接字并不等同于真实的网络接口路径，而沙盒环境也不等同于目标主机环境——这些差异都导致了数量级的性能差异 `[EVIDENCE: re-run on target host]` ）。

```
UDP sendto alone:            449,965 pps    (socket path)
Event generation + encode:    91,192 ev/s   (PRNG step + book-mirror update + struct.pack, no socket)
Combined generate-and-send:  142,827 ev/s   (the true online session-mode ceiling)
```

Set against the _measured_ real-feed profile (3.4.4.6: 17.1 msg/s session average, 584 msg/s peak second, 2,390 msg/s peak 100 ms burst equivalent), the 1.4 × 10⁵ ev/s online ceiling gives a **~60× margin over the worst real burst and ~8,000× over the session average** — single-threaded Python session mode is settled by arithmetic. The same numbers show the online path is **~10× short of the 1.389 M pps wire ceiling**, and — the non-obvious measured fact — the shortfall is in _generation_ (91 K/s), not the socket (450 K/s): this kills the "just optimize the send path" option and forces Decision 3's offline/online split on arithmetic rather than taste.  
与经过测量的实际传输速率相比（3.4.4.6：17.1 条消息/秒的平均速率，584 条消息/秒的峰值速率，2,390 条消息/秒的 100 毫秒突发速率），1.4×10⁵埃/秒的在线峰值速率在最糟糕的突发情况下能提供~60 倍的余量，而在会话平均情况下则能提供~8,000 倍的余量——单线程 Python 会话模式是通过算术运算来决定的。同样的数值还表明，在线路径比 1.389 百万比特每秒的线路上限短~10 倍。此外，一个不太明显的事实是，这种不足发生在生成端（91 千比特每秒），而不是在套接字端（450 千比特每秒）：这就排除了“只需优化发送路径”的选择，而必须基于算术运算来做出离线/在线之间的决策。

### 3.4.4.2 Stress-mode PCAP sizing (NFS9)  
3.4.4.2 应力模式下的 PCAP 尺寸确定（NFS9）

At the 3.1.4.1 wire ceiling, one second of line-rate traffic is 1.389 M frames × 90 B = **125 MB/s** (= 1 Gbps, as it must). Sizing options:  
在 3.1.4.1 的线路速率下，一秒内的线路流量相当于 1.389 百万个帧，每帧包含 90 字节，因此总传输速率达到 125 兆字节每秒（即 1 吉比特每秒）。可选的尺寸参数：

```
Continuous 60 s line-rate PCAP:  1.389 M × 60 × 90 B ≈ 7.5 GB   (single file, unique order_ids)
Looped 1 M-frame PCAP:           90 MB file, looped N times      (order_ids repeat per loop)
Offline generation time:         83.3 M frames ÷ 91 K ev/s ≈ 15 min for the 60 s file (one-time cost)
```

Either satisfies NFS9's drop-counter criterion; the looped file is operationally lighter at the cost of the semantic caveat in Decision 3. `[TEAM: recommend looped 90 MB file for routine runs + one 7.5 GB unique-ID file for the formally reported NFS9 result, so the reported run carries no loop asterisk.]` NFS9's micro-burst clause is additionally covered in session mode by scenario-driven bursts of ≤ 50 ms (≈ 69 K frames, pre-synthesized into a burst buffer).  
该文件满足 NFS9 的“降频计数器”标准；虽然这种循环文件在操作上较为轻量级，但代价是需要在决策 3 中遵守一些语义上的限制。此外，NFS9 的微突发机制在会话模式下也得到了支持，即出现持续时间不超过 50 毫秒的突发情况（约 69 千帧，这些帧会被预合成到突发缓冲区中）。

### 3.4.4.3 Determinism — measured  
3.4.4.3 决定论——已测量完毕

Same-seed reproducibility was checked directly rather than asserted: two 10,000-event streams from identical seeds are **byte-identical**, and a different seed diverges (measured on the synthetic driver). The design conditions this rests on: single-threaded generation, integer arithmetic in the event model, Python's `random.Random(seed)` (Mersenne Twister — version-stable), and no wall-clock dependence in event _content_ (host timestamps appear only in the ground-truth log, never in the byte stream). Consequence chain: deterministic byte stream ⇒ deterministic PL book states ⇒ deterministic PS snapshot sequence ⇒ FS7's backtest bootstrap corpus is reproducible end-to-end from a seed list. `[EVIDENCE: extend the check to full-session length and across both EventSink backends — socket-mode bytes must equal PCAP-mode bytes for the same seed and the same replay dataset.]`  
同一种子产生的数据可重复性已经通过直接验证，而不是仅仅假设而已：来自相同种子的两个包含 10,000 个事件的流在字节级上是完全相同的，而使用不同种子生成的流则会出现差异（这一点可以通过合成的驱动程序来测量）。该设计的依据包括：单线程生成、事件模型中的整数运算、Python 的 `random.Random(seed)` 函数（Mersenne Twister 算法——版本稳定版），以及事件内容不受主机时间戳影响的特点（主机时间戳只会出现在原始日志中，绝不会出现在字节流中）。因此，可以确定的是：确定性的字节流生成方式意味着确定性的 PL 书籍状态，进而确定性的 PS 快照序列，最终 FS7 的回测基础数据也是可从头到尾复现的，只要使用相同的种子列表即可。 `[EVIDENCE: extend the check to full-session length and across both EventSink backends — socket-mode bytes must equal PCAP-mode bytes for the same seed and the same replay dataset.]`

### 3.4.4.4 Generator correctness invariants (the simulator's own test plan)  
3.4.4.4 发电机的正确性不变量（模拟器自身的测试计划）

The simulator is a verification instrument, so its own correctness needs an argument that does not circularly depend on the system under test. Three machine-checkable invariants, enforced in both drivers and asserted in tests `[EVIDENCE: property-based test — 10⁷-event synthetic runs across many seeds; full-dataset replay run]`:  
该模拟器是一种验证工具，因此其正确性需要一种不依赖于被测试系统的自洽论证。有三个可以通过机器进行验证的不变量，这些不变量在驱动程序中得到强制执行，同时在测试中也会得到确认 `[EVIDENCE: property-based test — 10⁷-event synthetic runs across many seeds; full-dataset replay run]` 。

|Invariant  不变量|Statement  声明|Why it matters downstream  <br>为什么它会在下游产生重要影响|Real-data status (3.4.4.6)  <br>实际数据状态（3.4.4.6）|
|---|---|---|---|
|I1 — referential integrity  <br>I1 — 参照完整性|Every Modify/Delete references an `order_id` currently live in the Book Mirror  <br>每一个修改/删除操作都涉及到一个存在于图书镜像中的 `order_id` 对象。|The PL book builder (3.1.3.1 stage 5) is entitled to assume well-formed L3 flow  <br>PL 文档构建工具（3.1.3.1 阶段 5）可以假设所生成的 L3 流程是格式正确的。|Enforced by the translation layer; 2.09% of raw LOBSTER messages reference pre-session orders and are handled by book-priming `[TEAM: priming vs. filtered-with-counter]`  <br>这些消息是由翻译层强制执行的；在总数量的 2.09%的 LOBSTER 消息中，提到了预会话指令，这些指令由 book-priming 模块来处理 `[TEAM: priming vs. filtered-with-counter]`|
|I2 — book non-negativity  <br>I2 — 书籍的非负性|No aggregate level quantity ever goes negative; no order's remaining quantity goes negative  <br>任何汇总级别的数量都不会出现负数；任何订单的剩余数量也不会为零。|Ground-truth `book_top_after` must be a valid book or the golden reference is worthless  <br>“Ground-truth `book_top_after` ”必须是一本有效的书籍，否则那本《黄金参考书》就毫无价值了。|**0 violations** across 400,391 real messages  <br>在 400,391 条真实消息中，共发生了 0 次违规情况。|
|I3 — encode/decode round-trip  <br>I3——编码/解码往返机制|`decode(encode(event)) == event` for the simulator's own encoder against its own Table-3.1.4 parser  <br>`decode(encode(event)) == event` 针对模拟器的自有编码器与表 3.1.4 中的解析器之间的交互。|The oracle property of Decision 2: self-round-trip is its base case  <br>决策 2 的预言特性是：其自环路径情况就是基础情况。|**0 failures** across 380,678 real encoded events  <br>在 380,678 个实际编码的事件中，没有出现任何失败情况。|

### 3.4.4.5 Session data-volume arithmetic (NFS4 soak, log sizing)  
3.4.4.5 会话数据量计算方式（NFS4 测试、日志大小调整）

```
6.5 h session at 1,000 msg/s configured average (stress-leaning synthetic profile;
 the real-data average is 17 msg/s, so 1,000 is a deliberate ~60× margin session):
                                        23,400 s × 10³ = 23.4 M events
Ground-truth log, full mode (~120 B/line with hex):  ≈ 2.8 GB/session   → verification sessions: fine on host disk
Ground-truth log, soak mode (no hex, ~40 B/line):    ≈ 0.94 GB/session  → NFS4 soak: fine
Generated wire traffic: 23.4 M × 90 B ≈ 2.1 GB over 6.5 h ≈ 0.7 Mbps avg — the link is ~0.07% utilized;
NFS2/NFS4 stress the SoC's endurance, not the wire
```

### 3.4.4.6 Real-data validation: LOBSTER replay through the protocol layer — measured  
3.4.4.6 真实数据验证：通过协议层对 LOBSTER 重放过程进行监测——已进行测量

The full free-sample dataset — 400,391 real order-level messages, AAPL, one complete NASDAQ trading day (2012-06-21), top-10 book levels [13] — was run through a prototype of the replay driver's translation layer and the Table 3.1.4 encoder. This is a validation of the _protocol and translation semantics against real order flow_, executed at design time precisely so its findings could shape the design rather than audit it. Four results and two findings:  
完整的免费样本数据集——包含 400,391 条真实的订单级消息，涉及 AAPL 股票，以及一个完整的纳斯达克交易日（2012 年 6 月 21 日）的数据，还有排名前 10 的书籍级别信息[13]——这些数据经过了回放驱动程序的翻译层原型以及 Table 3.1.4 编码器的处理。这一操作旨在验证该协议和翻译语义在实际订单流程中的适用性，因为这些数据是在设计阶段精确生成的，因此其结果能够用于指导设计改进，而非仅仅用于审计。最终得到了四个结果和两条发现：

**Result 1 — real rate profile (supersedes all earlier estimates).** Session average **17.1 msg/s**; peak one-second rate **584 msg/s**; peak 100 ms burst **2,390 msg/s equivalent**. These figures replace the `[EVIDENCE]`-flagged guesses previously carried in this section and in Decision 3, and they recalibrate the margins in 3.4.4.1. They also put NFS9 in perspective: the 1.389 M pps stress requirement exceeds this real symbol's _peak burst_ by ~580× — line-rate robustness is an engineering-margin specification, not a realism one, and the report should present it as such.  
结果 1——实际速率概况（取代所有之前的估计值）。会话平均速率为 17.1 条消息/秒；每秒最高消息传输速率达到 584 条消息；每 100 毫秒内的最高消息传输速率可达 2,390 条消息/秒。这些数字取代了之前在本节及决策 3 中使用的 `[EVIDENCE]` 标记的估算值。这些数值有助于重新调整 3.4.4.1 中的参数范围。同时，这些数字也让 NFS9 的实际情况更加清晰：1.389 百万比特每秒的传输需求，相当于该实际速率峰值下的需求，超出 1001 倍。线路速率的鲁棒性属于工程方面的规格要求，而非现实中的需求，因此报告应如此表述。

**Result 2 — event-mix calibration.** Real composition: submissions 47.7%, full deletions 42.7%, visible executions 5.9%, hidden executions 2.8%, partial cancels 0.8%. The synthetic driver's mix table (3.4.3.2) now cites these measured ratios; the earlier working figures (55/25/20) were materially wrong about modify frequency — real flow is add/delete-dominated, and modifies are rare.  
结果 2——事件混合校准。实际构成如下：提交占 47.7%，完全删除占 42.7%，可见执行占 5.9%，隐藏执行占 2.8%，部分取消占 0.8%。合成驱动程序的混合表（3.4.3.2）现在引用了这些测量到的比例；之前使用的数据（55/25/20）在修改频率方面存在严重错误——实际情况下，修改行为以添加和删除为主，而修改本身非常罕见。

**Result 3 — field-width confirmation.** Max real `order_id` = 287,150,931 (u32: fits, 15× headroom); max size 15,000 shares (u32: trivial). Table 3.1.4's field widths survive contact with real data.  
结果 3——字段宽度的确认。最大实际数值为 287,150,931（32 位整数：适合使用，15 倍于头部空间）；最大尺寸为 15,000 个份额（32 位整数：简单情况）。表 3.1.4 中的字段宽度在与实际数据交互后仍然有效。

**Result 4 — translation throughput and invariants.** The Python translation layer (order-pool tracking + encode) processed the full day at **1.10 M msg/s** — the entire real session translates offline in 0.37 s, so replay preparation is never a cost. I2 and I3 passed with zero violations across the full dataset (table in 3.4.4.4).  
结果 4——翻译吞吐量和不变式。Python 翻译层（订单池跟踪+编码处理）在全天内以每秒 100 万条消息的速度运行——整个实时会话的离线翻译过程仅需 0.37 秒，因此重放准备从来不会造成任何成本。在完整的数据集上，I2 和 I3 在没有任何错误的情况下通过了测试（表项在 3.4.4.4 中进行了验证）。

**Finding 1 — sub-penny prices break the integer-cents assumption (protocol change required or policy needed).** 372 of 400,391 real events (0.09%) carry prices that are _not_ whole cents (LOBSTER prices are dollars ×10⁴; these events have a nonzero residue mod 100 — sub-penny executions/price-improvement prints). The Table 3.1.4 `price` field is specified in integer cents, so these events cannot be represented exactly. Options: (a) round-to-cent with a documented policy and a `price_rounded` counter (zero protocol change; 0.09% of events carry ≤ $0.005 error), or (b) redefine the price field unit as 10⁻⁴ dollars (exact; costs nothing in width — u32 spans $429,496 at 10⁻⁴ — but touches the PL parser, PS strategy arithmetic, and 3.3's kernel-parity chain). `[TEAM: decide; recommendation (a) for the prototype — the affected events are executions rather than restizng book liquidity, and the parity chain's integer-cents commitment (3.2.3.2, 3.3 Decision 4) is otherwise disturbed end-to-end.]`  
发现 1——低于一分钱的价格打破了整数分价的假设（需要修改协议或制定相关政策）。在 400,391 个实际事件中，有 372 个事件的定价不是整数分钱（例如，龙虾期权的价格为美元×10⁴；这些事件的余数模 100 不为 0——因此会出现低于一分钱的执行价格/价格调整情况）。表 3.1.4 中字段以整数分钱为单位进行表示，因此这些事件无法被精确表示。解决方案如下：(a)采用四舍五入的方法，并制定相关政策，同时使用计数器 `price_rounded` 进行记录（无需修改协议；0.09%的事件会出现≤0.005 美元的误差）；或者(b)将价格字段的单位重新定义为 10⁻⁴美元（精确表示；在数值上不会造成任何影响——u32 字段以 10⁻⁴单位表示 429,496 美元——但这会涉及到 PL 解析器、PS 策略计算以及 3.3 的核心奇偶校验链）。 `[TEAM: decide; recommendation (a) for the prototype — the affected events are executions rather than restizng book liquidity, and the parity chain's integer-cents commitment (3.2.3.2, 3.3 Decision 4) is otherwise disturbed end-to-end.]`

**Finding 2 — the Modify-semantics ambiguity (the FS13 oracle mechanism fired at design time).** Writing the translation forced a question Table 3.1.4 does not answer: does a Modify's `qty` field carry the _new absolute_ quantity or a _delta_? LOBSTER's partial-cancel and execution events carry deltas; the translation had to pick a convention (absolute remaining quantity was chosen) and the PL book-update stage must agree or the books diverge silently. This is precisely Decision 2's claim — that an independent second implementation is the strongest test of the protocol document — vindicated before any hardware exists: the ambiguity is now a required amendment to Table 3.1.4's field description rather than a future integration bug. `[TEAM: amend Table 3.1.4 — specify "qty = new absolute aggregate for this order" (recommended, stateless for the PL) and mirror the wording in the 3.1.3.1 stage-5 description.]`  
发现 2——修改语义的模糊性（在设计阶段，FS13 的预言机制被触发）。在翻译过程中，需要解决一个问题：表 3.1.4 并没有给出答案。修改的 `qty` 字段表示的是新的绝对数值，还是差值呢？LOBSTER 的部分取消和执行操作会涉及到差值；因此，翻译必须确定一个约定（选择使用绝对剩余数值），而 PL 的更新阶段则必须达成一致，否则两个版本就会各自独立发展。这正是决策 2 所主张的——独立的第二种实现方式才是验证协议文档的最有力手段——这种有效性可以在硬件存在之前就得到验证：这种模糊性现在已经成为表 3.1.4 字段描述中的必要修正内容，而不是未来需要解决的集成问题。 `[TEAM: amend Table 3.1.4 — specify "qty = new absolute aggregate for this order" (recommended, stateless for the PL) and mirror the wording in the 3.1.3.1 stage-5 description.]`

**Honest scope statement.** This validation exercises the translation layer and encoder on the development sandbox; it does not exercise the physical link, the PL parser, or timing (those are the Section 2 procedures, which remain pending). One symbol-day is a semantic ground-truth check, not a statistical study; the mix and rate figures above are one liquid large-cap's behavior on one 2012 day and are used as _calibration anchors_, not as claims about markets in general.  
诚实的范围声明：此验证过程是在开发沙盒环境中对翻译层和编码器进行的测试；它并不涉及物理链接、PL 解析器或时间处理（这些都属于第 2 阶段的程序，目前仍处于待定状态）。一个符号日只是对语义层面的实际验证，并非统计研究；上述混合率和比率数据仅反映了一只 2012 年度大型股基金在某一特定日的表现，它们被用作校准基准，而非对市场的普遍描述。

---

## 3.4.5 Specification Compliance / Instrumentation Summary  
3.4.5 规范符合性/仪表汇总

|Spec  规格/参数|What the simulator provides  <br>模拟器提供了什么功能？|Evidence status  证据状态|
|---|---|---|
|FS1/FS2 (instrument)  FS1/FS2（仪器）|Seeded reference sequences (`scenario_fs2_reference_1000.json`); TX-side ground-truth timestamps  <br>已排序的参考序列 ( `scenario_fs2_reference_1000.json` )；TX 端的实际时间戳|Design complete; pending scenario-file authoring  <br>设计已完成；目前处于等待场景文件编写的阶段。|
|FS13 (oracle)  FS13（Oracle）|Independent parse of every order packet; disagreements surface spec ambiguities  <br>每个订单数据包都进行了独立的解析；由于表述不清的地方，会导致分歧出现。|Mechanism validated at design time (Finding 2, RX-side analog); pending live cross-parse  <br>该机制在设计阶段已经经过验证（第 2 项发现，RX 端模拟版本）；正在等待实际运行中的跨解析测试。|
|NFS2 (peer)  NFS2（对等节点）|Direct-cabled link peer; TX frame counts as expected-delivery denominator  <br>直接连接的链路对端；传输帧数量符合预期交付标准|Pending 10-min counted run  <br>等待 10 分钟后的累计跑步距离|
|NFS4 (provider)  NFS4（提供者）|6.5 h seeded session; soak-mode logging (0.94 GB)  <br>6.5 小时的种子会话时间；日志模式记录（0.94GB）|Pending soak run  等待浸泡过程结束|
|NFS8 (injector)  NFS8（注入器）|Scenario directives: `corrupt_fcs`, `burst`, `malformed_field`  <br>情景指令： `corrupt_fcs` 、 `burst` 、 `malformed_field`|Pending scenario-file authoring + injection runs  <br>在等待场景文件创建和插入运行完成之后……|
|NFS9 (injector)  NFS9（注入器）|Offline-generated PCAP (90 MB looped / 7.5 GB unique) + line-rate replayer  <br>离线生成的 PCAP 文件（90 MB 大小，包含循环数据；7.5 GB 的独特数据）+ 按行速率播放的播放器|Pending replayer line-rate validation `[EVIDENCE]`  <br>在回放器的帧率验证完成之前 `[EVIDENCE]`|
|FS6/FS7 (bootstrap)  FS6/FS7（启动模式）|Regime-labeled, seed-reproducible session corpus; plus one real-data session (LOBSTER replay)  <br>带有标签的、可复现的会话数据集；此外还有一例真实数据会话（LOBSTER 重放）|Synthetic corpus pending; real-data translation validated (3.4.4.6)  <br>合成语料库正在待处理阶段；真实数据的转换已得到验证（3.4.4.6）|
|Own correctness  正确的自我认知|Invariants I1–I3; determinism (measured); rate margins (measured); real-data validation (measured, full dataset)  <br>不变量 I1–I3；确定性（已测量）；速率边际（已测量）；真实数据验证（已测量，完整数据集）|Sandbox-measured; target-host re-runs pending  <br>沙盒测量结果显示：目标主机上的重放操作仍待处理。|

---

## References  参考文献

[1] C. Leber, B. Geib and H. Litz, "High Frequency Trading Acceleration Using FPGAs," _2011 21st International Conference on Field Programmable Logic and Applications_, Chania, Greece, 2011, pp. 317-322, doi: 10.1109/FPL.2011.64.  
[1] C. Leber, B. Geib 和 H. Litz，“利用 FPGA 实现高频交易加速”，2011 年第 21 届可编程逻辑与应用国际会议，希腊哈尼亚，2011 年，页码 317-322，doi: 10.1109/FPL.2011.64。

[2] Y.-C. Kao, H.-A. Chen and H.-P. Ma, "An FPGA-Based High-Frequency Trading System for 10 Gigabit Ethernet with a Latency of 433 ns," _2022 International Symposium on VLSI Design, Automation and Test (VLSI-DAT)_, Hsinchu, Taiwan, 2022, pp. 1-4, doi: 10.1109/VLSI-DAT54769.2022.9768065.  
[2] 杨永成、陈海安和马海鹏，《一种基于 FPGA 的 10 吉比特以太网高频交易系统，延迟为 433 纳秒》，2022 年 VLSI 设计、自动化与测试国际研讨会，台湾新竹，2022 年，页码 1-4，doi: 10.1109/VLSI-DAT54769.2022.9768065。

[3] C. He, H. Fu, W. Luk, W. Li and G. Yang, "Exploring the potential of reconfigurable platforms for order book update," _2017 27th International Conference on Field Programmable Logic and Applications (FPL)_, Ghent, Belgium, 2017, pp. 1-8, doi: 10.23919/FPL.2017.8056862.  
[3] C. He, H. Fu, W. Luk, W. Li 和 G. Yang，“探索可重构平台在订单更新中的潜力”，2017 年第 27 届现场可编程逻辑与应用会议（FPL），比利时根特，2017 年，页码 1-8，doi: 10.23919/FPL.2017.8056862。

[4] G. W. Morris, D. B. Thomas and W. Luk, "FPGA Accelerated Low-Latency Market Data Feed Processing," _2009 17th IEEE Symposium on High Performance Interconnects_, New York, NY, USA, 2009, pp. 83-89, doi: 10.1109/HOTI.2009.17.  
[4] G. W. Morris、D. B. Thomas 和 W. Luk，“基于 FPGA 的低延迟市场数据处理技术”，2009 年第 17 届高性能互连技术研讨会论文集，美国纽约，2009 年，页码 83-89，doi: 10.1109/HOTI.2009.17。

[5] M. Mohamed Asan Basiri, "Hardware based Order Book Design in High Frequency Algo Trading," _2021 IEEE International Symposium on Smart Electronic Systems (iSES)_, Jaipur, India, 2021, pp. 285-288, doi: 10.1109/iSES52644.2021.00073.  
[5] M. Mohamed Asan Basiri，“基于硬件的订单簿设计在高频算法交易中的应用”，2021 年 IEEE 智能电子系统国际研讨会（iSES），印度斋浦尔，2021 年，第 285-288 页，doi: 10.1109/iSES52644.2021.00073。

[6] A. Boutros, B. Grady, M. Abbas and P. Chow, "Build fast, trade fast: FPGA-based high-frequency trading using high-level synthesis," _2017 International Conference on ReConFigurable Computing and FPGAs (ReConFig)_, Cancun, Mexico, 2017, pp. 1-6, doi: 10.1109/RECONFIG.2017.8279781.  
[6] A. Boutros, B. Grady, M. Abbas 和 P. Chow，“快速构建、快速交易：基于 FPGA 的高频交易系统”，2017 年可重构计算与 FPGA 国际会议（ReConFig），墨西哥坎昆，2017 年，页码 1-6，doi: 10.1109/RECONFIG.2017.8279781。

[7] R. Osuna, B. Reponte, and L. G. Ramirez, "Low-latency Ethernet communications on FPGA SoC for high frequency trading," Kastner Research Group, University of California, San Diego, San Diego, CA, USA, Tech. Rep., Jun. 2025. [Online]. Available: [https://kastner.ucsd.edu/wp-content/uploads/2025/06/admin/highfrequencytrading.pdf](https://kastner.ucsd.edu/wp-content/uploads/2025/06/admin/highfrequencytrading.pdf)  
[7] R. Osuna, B. Reponte, 和 L. G. Ramirez，“在 FPGA 系统上实现低延迟的以太网通信，以用于高频交易”，Kastner 研究组，加利福尼亚大学圣地亚哥分校，美国加利福尼亚州圣地亚哥，技术报告，2025 年 6 月。[在线发布]。可访问链接：https://kastner.ucsd.edu/wp-content/uploads/2025/06/admin/highfrequencytrading.pdf

[8] K. Tatsumura, R. Hidaka, J. Nakayama, T. Kashimata, and M. Yamasaki, "Real-time Trading System based on Selections of Potentially Profitable, Uncorrelated, and Balanced Stocks by NP-hard Combinatorial Optimization," Corporate Research and Development Center, Toshiba Corporation, Japan, 2023.  
[8] K. Tatsumura, R. Hidaka, J. Nakayama, T. Kashimata, 和 M. Yamasaki，“基于潜在盈利性、不相关性和均衡性的股票选择的实时交易系统——通过 NP 难组合优化实现”，日本东芝公司企业研发中心，2023 年。

[9] K. Tatsumura, R. Hidaka, J. Nakayama, T. Kashimata, and M. Yamasaki, "Pairs-trading System using Quantum-inspired Combinatorial Optimization Accelerator for Optimal Path Search in Market Graphs," Corporate Research and Development Center, Toshiba Corporation, Japan, 2023.  
[9] 田村克、平田良、中山良、加岛智、山崎明，“基于量子启发式组合优化加速器的配对交易系统——用于在市场图中寻找最优路径”，日本东芝公司企业研发中心，2023 年。

[10] Interactive Brokers, "Market Depth (Level II)," TWS API v9.72+ Documentation. [Online]. Available: [https://interactivebrokers.github.io/tws-api/market_depth.html](https://interactivebrokers.github.io/tws-api/market_depth.html) [Accessed: Jul. 9, 2026].  
[10] Interactive Brokers 公司提供的《市场深度信息（二级级别）》文档，基于 TWS API v9.72 及以上版本。在线获取地址：https://interactivebrokers.github.io/tws-api/market_depth.html 访问日期：2026 年 7 月 9 日。

[11] R. Huang and T. Polak, "LOBSTER: Limit Order Book Reconstruction System," SSRN Working Paper 1977207, Humboldt-Universität zu Berlin, Dec. 2011, doi: 10.2139/ssrn.1977207.  
[11] R. Huang 和 T. Polak，“LOBSTER：限价订单池重建系统”，SSRN 工作论文 1977207，柏林洪堡大学，2011 年 12 月，doi: 10.2139/ssrn.1977207。

[12] LOBSTER, "Price List — Academic Users," LOBSTER academic data. [Online]. Available: [https://data.lobsterdata.com/info/docs/legal/LOBSTER_priceList.pdf](https://data.lobsterdata.com/info/docs/legal/LOBSTER_priceList.pdf) [Accessed: Jul. 9, 2026].  
[12] LOBSTER 网站上的“价格列表——学术用户”，属于 LOBSTER 的学术数据平台。在线访问地址：https://data.lobsterdata.com/info/docs/legal/LOBSTER_priceList.pdf 访问时间：2026 年 7 月 9 日。

[13] LOBSTER, "Sample Files" and "Data Structure," LOBSTER academic data, Humboldt-Universität zu Berlin. [Online]. Available: [https://lobsterdata.com/info/DataSamples.php](https://lobsterdata.com/info/DataSamples.php) ; [https://lobsterdata.com/info/DataStructure.php](https://lobsterdata.com/info/DataStructure.php) (dataset: AAPL 2012-06-21, levels 1–50; official NASDAQ Historical TotalView-ITCH sample day). [Accessed: Jul. 9, 2026].  
[13] LOBSTER 网站上的“样本文件”和“数据结构”栏目，包含 LOBSTER 学术数据，由柏林洪堡大学提供。在线访问地址：https://lobsterdata.com/info/DataSamples.php；https://lobsterdata.com/info/DataStructure.php（数据集：AAPL 2012-06-21，数据级别为 1–50；官方 NASDAQ 历史数据示例日）。访问日期：2026 年 7 月 9 日。

[14] Y. Zheng, "FPGA-based Acceleration for High Frequency Trading," M.Phil. thesis, Dept. Electron. Comput. Eng., Hong Kong Univ. Sci. Technol., Hong Kong, Jan. 2023.  
[14] Y. Zheng，《基于 FPGA 的高频交易加速技术》，M.Phil 论文，香港理工大学电子计算机工程系，香港，2023 年 1 月。

[15] J. D. Hamilton, "A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle," _Econometrica_, vol. 57, no. 2, pp. 357–384, Mar. 1989, doi: 10.2307/1912559.  
[15] J. D. Hamilton，《非平稳时间序列与经济周期的经济分析新方法》，《计量经济学杂志》，第 57 卷，第 2 期，第 357-384 页，1989 年 3 月，doi: 10.2307/1912559。

[16] J. Bergstra and Y. Bengio, "Random Search for Hyper-Parameter Optimization," _Journal of Machine Learning Research_, vol. 13, pp. 281–305, Feb. 2012.  
[16] J. Bergstra 和 Y. Bengio，《通过随机搜索优化超参数》，机器学习研究杂志，第 13 卷，第 281-305 页，2012 年 2 月。

[17] D. Araci, "FinBERT: Financial Sentiment Analysis with Pre-trained Language Models," arXiv preprint arXiv:1908.10063, Aug. 2019.  
[17] D. Araci，“FinBERT：利用预训练语言模型进行金融情绪分析”，arXiv 预印本，arXiv:1908.10063，2019 年 8 月。

### Further reading (uncited in this document)  
推荐阅读资料（本文档中未提及具体来源）

- FIX Trading Community, "FIX Adapted for STreaming (FAST) Specification." [Online]. Available: [https://www.fixtrading.org/standards/fast-online/](https://www.fixtrading.org/standards/fast-online/) [Accessed: Jul. 9, 2026].  
    FIX 交易社区发布了一篇关于“适用于流媒体的 FIX 规范”的报道。[在线版]。链接：https://www.fixtrading.org/standards/fast-online/ [访问日期：2026 年 7 月 9 日]
- J. Zang, "quant-engine: a C++ quantitative backtest and research engine," independent project documentation. [Online]. Available: [https://qe.jiucheng-zang.ca](https://qe.jiucheng-zang.ca/) [Accessed: Jul. 2026].  
    J. Zang，《Quant-engine：一个用于定量回测和研究的 C++引擎》。独立项目文档。[在线版]。访问地址：https://qe.jiucheng-zang.ca　访问日期：2026 年 7 月。

`[TEAM: bibliography housekeeping — (i) confirm the Toshiba entries' actual venues (both appear to be published papers; locate DOI/venue before submission); (ii) confirm the citation style guide for online resources; (iii) Hamilton 1989, Bergstra & Bengio 2012, and FinBERT/Araci 2019 are now in the list as [15]–[17]; 3.3's remaining pending citations (Loughran-McDonald 2011, TradingAgents 2024/2412.20138) should be appended if and when actually cited.]`

---

## Document Index (titles + line numbers)  
文档索引（标题+行号）

Line numbers refer to this file as currently written (they will shift as edits are made).  
这些行号是按照当前文件的书写顺序来标记的（随着编辑的进行，行号可能会发生变化）。

- L1 1. Introduction  L1 1. 引言
- L3 1.1 Motivation  L3 1.1 动机
- L9 1.2 Project Objective  
    L9 1.2 项目目标
- L19 1.3 Block Diagram (Deprecated, only for reference)  
    L19 1.3 框图（已不再使用，仅用于参考）
- L93 2. System Specifications  
    L93 2. 系统规格说明
- L95 2.1 Functional Specifications  
    L95 2.1 功能规格
- L114 2.2 Non-Functional Specifications  
    L114 2.2 非功能规格要求
- L128 3.1 PL (FPGA) Market Data Path Subsystem  
    L128 3.1 PL（FPGA）市场数据路径子系统
- L138 3.1.1 Overview and Specification Mapping  
    L138 3.1.1 概述与规格说明映射
- L160 3.1.2 Engineering Design Process  
    L160 3.1.2 工程设计流程
- L164 Decision 1 — Network path placement: PS socket, PS-DMA-then-parse, or full PL path  
    L164 决策 1 — 网络路径选择：使用 PS 接口、PS-DMA 方式处理后再解析，或者采用完整的 PL 路径。
- L174 Decision 2 — MAC layer implementation: vendor IP, open-source stack, or minimal custom MAC  
    L174 决策 2——MAC 层实现方式：采用厂商提供的 IP 地址、开源解决方案，还是采用最基础的自定义 MAC 地址？
- L186 Decision 3 — Parse architecture: store-and-forward vs. cut-through streaming parse  
    L186 决策 3——解析架构：存储转发与直通流解析
- L194 Decision 4 — Order book storage: BRAM-indexed structure vs. fixed register array  
    L194 决策 4——订单簿存储方式：使用 BRAM 索引结构还是固定寄存器数组
- L207 3.1.3 Final Design Details  
    L207 3.1.3 最终设计细节
- L209 3.1.3.1 Receive pipeline  
    L209 3.1.3.1 接收管道
- L219 3.1.3.2 Packet formats (FS13 interface contract)  
    L219 3.1.3.2 数据包格式（FS13 接口规范）
- L240 3.1.3.3 Order book register layout  
    L240 3.1.3.3 订单簿登记页面布局
- L249 3.1.3.4 Clocking and PS interface  
    L249 3.1.3.4 时钟设置和 PS 接口
- L259 3.1.4 Quantitative Technical Analysis  
    L259 3.1.4 定量技术分析
- L261 3.1.4.1 Line-rate throughput (NFS9)  
    L261 3.1.4.1 线速吞吐量（NFS9）
- L276 3.1.4.2 FS1 latency budget decomposition  
    L276 3.1.4.2 FS1 延迟预算分解
- L290 3.1.4.3 Resource envelope (NFS6)  
    L290 3.1.4.3 资源限制范围（NFS6）
- L306 3.1.5 Specification Compliance Summary  
    L306 3.1.5 规范符合性总结
- L320 3.2 PS (ARM OS Layer) Strategy & Risk Subsystem  
    L320 3.2 马力（ARM 操作系统层）策略与风险子系统
- L328 3.2.1 Overview and Specification Mapping  
    L328 3.2.1 概述与规格说明映射
- L350 3.2.2 Engineering Design Process  
    L350 3.2.2 工程设计流程
- L352 Decision 1 — Hardware/software boundary: why the strategy engine is not in the PL  
    L352 决策 1——硬件与软件的边界：为什么策略引擎并不包含在 PL 中？
- L361 Decision 2 — Operating environment: bare-metal, FreeRTOS, AMP, or Linux with core isolation  
    L361 决策 2——运行环境：裸机环境、FreeRTOS、AMP，或者带有核心隔离功能的 Linux 系统
- L373 Decision 3 — Hot-path interface and event delivery: a three-iteration, spec-driven design history  
    L373 决策 3——热路径接口与事件传递：一个基于规范驱动的设计历程，包含三次迭代
- L393 Decision 4 — Execution Logger architecture: the memory arithmetic forces the record policy  
    L393 决策 4——执行日志器架构：内存运算机制决定了记录策略的实施方式
- L405 Decision 5 — Runtime Risk Guard placement: PS software vs. PL hardware  
    L405 决策 5——运行时安全保护的放置：PS 软件与 PL 硬件之间的对比
- L409 Decision 6 — Order-terminal semantics for FS14: execution report vs. modeled fills (selected)  
    L409 决策 6——适用于 FS14 的序贯终端语义：执行报告与建模后的填充情况（选中的结果）
- L415 3.2.3 Final Design Details  
    L415 3.2.3 最终设计细节
- L417 3.2.3.1 The PL/PS register bank and access protocol (interface contract)  
    L417 3.2.3.1 PL/PS 寄存器组及访问协议（接口规范）
- L435 3.2.3.2 Strategy Engine (Plug-In Execution)  
    L435 3.2.3.2 策略引擎（插件执行）
- L447 3.2.3.3 Runtime Risk Guard (FS3)  
    L447 3.2.3.3 运行时安全保护（FS3）
- L460 3.2.3.3.1 Open-order table (FS14)  
    L460 3.2.3.3.1 开单表格（FS14）
- L464 3.2.3.4 Config Loader (FS4) and fault handling (NFS8)  
    L464 3.2.3.4 配置加载器（FS4）与故障处理（NFS8）
- L468 3.2.3.5 Execution Logger and Console (FS5, FS11)  
    L468 3.2.3.5 执行日志器和控制台（FS5、FS11）
- L472 3.2.3.6 HOLD Mode  
    L472 3.2.3.6 保持模式
- L478 3.2.4 Quantitative Technical Analysis  
    L478 3.2.4 定量技术分析
- L480 3.2.4.1 FS2 latency budget decomposition (26 μs at 766 MHz)  
    L480 3.2.4.1 FS2 延迟预算分解（在 766 MHz 频率下为 26 微秒）
- L496 3.2.4.2 Interface capacity, conflation, and the DMA comparison  
    L496 3.2.4.2 接口容量、合并机制以及 DMA 比较
- L518 3.2.4.3 FS5 memory budget arithmetic  
    L518 3.2.4.3 FS5 内存预算计算
- L531 3.2.4.4 Runtime Risk Guard cost bound  
    L531 3.2.4.4 运行时风险防护的成本限制
- L537 3.2.5 Specification Compliance Summary  
    L537 3.2.5 规范合规性总结
- L551 3.3 EOD Server Pipeline Subsystem  
    L551 3.3 爆炸物处理服务器子系统
- L560 3.3.1 Overview and Specification Mapping  
    L560 3.3.1 概述与规格说明 映射
- L585 3.3.2 Engineering Design Process  
    L585 3.3.2 工程设计流程
- L589 Decision 1 — Execution environment: on-SoC overnight job, compiled host pipeline, or Python host pipeline  
    L589 决策 1——执行环境：可以在片上系统上快速完成任务，可以使用编译后的主机管道，或者采用 Python 编写的主机管道来实现。
- L599 Decision 2 — Regime classifier (FS6): rule-based thresholds, k-means clustering, or Hidden Markov Model  
    L599 决策 2——机制分类器（FS6）：基于规则的阈值设置、K 均值聚类或隐马尔可夫模型
- L615 Decision 3 — Parameter search (FS7): exhaustive grid, random search, or Bayesian optimization  
    L615 决策 3——参数搜索（FS7）：穷举法、随机搜索还是贝叶斯优化
- L625 Decision 4 — Backtest kernel: vectorized library, event-driven framework, or parity-ported custom loop  
    L625 决策 4——回测内核：采用向量化库、事件驱动框架，或平行移植的自定义循环
- L639 Decision 5 — Text & Sentiment Path architecture (FS9/FS10): where the LLM belongs, and the determinism boundary  
    L639 决策 5——文本与情感路径架构（FS9/FS10）：这就是大型语言模型发挥作用的地方，也是决定论边界所在。
- L659 Decision 6 — Approval gate and configuration chain of custody (FS8)  
    L659 决议 6——批准关口与保管链的设置（FS8）
- L671 3.3.3 Final Design Details  
    L671 3.3.3 最终设计细节
- L675 3.3.3a Market Data Path (essential — FS6, FS7)  
    L675 3.3.3a 市场数据路径（至关重要——适用于 FS6 和 FS7 版本）
- L677 3.3.3a.1 Data import and Parameter Engineering  
    L677 3.3.3a.1 数据导入与参数设计
- L690 3.3.3a.2 Regime Detection (FS6)  
    L690 3.3.3a.2 状态检测（FS6）
- L705 3.3.3a.3 Strategy Reoptimize — Backtest & Parameter Sweep (FS7)  
    L705 3.3.3a.3 策略重新优化——回测与参数扫描（FS7）
- L734 3.3.3a.3.1 Preliminary validation run (real data)  
    L734 3.3.3a.3.1 初步验证运行（真实数据）
- L764 3.3.3a.4 Risk Analysis and config generation  
    L764 3.3.3a.4 风险分析与配置生成
- L768 3.3.3b Text & Sentiment Path (non-essential — FS9, FS10)  
    L768 3.3.3b 文本与情绪路径（非必需功能——适用于 FS9 和 FS10 版本）
- L770 3.3.3b.1 LLM Agent — ingestion and extraction (FS9)  
    L770 3.3.3b.1 大型语言模型代理——数据摄取与提取功能（FS9）
- L784 3.3.3b.2 Sentiment Analysis (FS10)  
    L784 3.3.3b.2 情感分析（FS10）
- L788 3.3.3b.3 Coupling into Risk Analysis  
    L788 3.3.3b.3 整合到风险分析中
- L798 3.3.3.5 JSON configuration schema (interface 8 contract, jointly owned with 3.2.3.4)  
    L798 3.3.3.5 JSON 配置模式（接口 8 合约，与 3.2.3.4 共同使用）
- L809 3.3.3.6 FS12 status reporting and server-side fault handling (NFS8)  
    L809 3.3.3.6 FS12 状态报告与服务器端故障处理（NFS8）
- L815 3.3.4 Quantitative Technical Analysis  
    L815 3.3.4 定量技术分析
- L817 3.3.4.1 NFS5 runtime budget decomposition  
    L817 3.3.4.1 NFS5 运行时的预算分配
- L843 3.3.4.2 FS7 determinism argument — enumeration of nondeterminism sources  
    L843 3.3.4.2 FS7 确定性论证——非确定性来源的列举
- L859 3.3.4.3 Regime classifier non-degeneracy (FS6 verifiability by construction)  
    L859 3.3.4.3 体制分类器非退化性（通过构造验证可行性，基于 FS6 标准）
- L879 3.3.4.4 Sentiment risk-coupling safety bound (FS10 cannot violate FS3)  
    L879 3.3.4.4 情绪风险与安全性界限的耦合（FS10 不得违反 FS3）
- L893 3.3.4.5 Grid scale sensitivity (why exhaustive search is the right size, and when it stops being)  
    L893 3.3.4.5 网格尺度敏感性（为什么穷举搜索是正确的选择，以及何时它不再适用）
- L906 3.3.5 Specification Compliance Summary  
    L906 3.3.5 规格符合性总结
- L921 3.4 Exchange Simulator Subsystem  
    L921 3.4 交换器模拟系统
- L930 3.4.1 Overview and Specification Mapping  
    L930 3.4.1 概述与规格说明 映射
- L955 3.4.2 Engineering Design Process  
    L955 3.4.2 工程设计流程
- L957 Decision 1 — Market-data source: a four-iteration design history  
    L957 决策 1——市场数据来源：一个包含四次迭代的设计历史记录
- L976 Decision 2 — Execution model: full matching engine vs. validate-and-log executor under a no-impact assumption  
    L976 决策 2——执行模型：完全匹配引擎与在无影响假设下的验证与记录执行器
- L985 Decision 3 — Rate architecture: one online generator for everything, or an offline-generate / online-replay split  
    L985 决议 3——速率架构：要么采用全在线生成方式来处理所有情况，要么采用离线生成与在线回放相结合的方案。
- L999 Decision 4 — Test controllability: hardcoded test modes, interactive control, or declarative scenario files  
    L999 决策 4——可控制性测试：采用硬编码的测试模式、交互式控制方式，或声明式场景文件配置。
- L1009 3.4.3 Final Design Details  
    L1009 3.4.3 最终设计细节
- L1011 3.4.3.1 Component structure and data flow  
    L1011 3.4.3.1 组件结构与数据流
- L1022 3.4.3.2 Order-flow model (synthetic driver)  
    L1022 3.4.3.2 流量模型（人工驱动）
- L1033 3.4.3.3 Session configuration and ground-truth log  
    L1033 3.4.3.3 会话配置及实际日志记录
- L1039 3.4.3.4 Link and host configuration  
    L1039 3.4.3.4 链接与主机配置
- L1045 3.4.4 Quantitative Technical Analysis  
    L1045 3.4.4 定量技术分析
- L1047 3.4.4.1 Session-mode rate capability — measured  
    L1047 3.4.4.1 会话模式速率能力——已测量完毕
- L1059 3.4.4.2 Stress-mode PCAP sizing (NFS9)  
    L1059 3.4.4.2 应力模式 PCAP 尺寸确定（NFS9）
- L1071 3.4.4.3 Determinism — measured  
    L1071 3.4.4.3 决定论——已测量完毕
- L1075 3.4.4.4 Generator correctness invariants (the simulator's own test plan)  
    L1075 3.4.4.4 发电机的正确性不变量（模拟器自身的测试计划）
- L1085 3.4.4.5 Session data-volume arithmetic (NFS4 soak, log sizing)  
    L1085 3.4.4.5 会话数据量计算算法（NFS4 测试、日志大小调整）
- L1097 3.4.4.6 Real-data validation: LOBSTER replay through the protocol layer — measured  
    L1097 3.4.4.6 真实数据验证：通过协议层对 LOBSTER 重放过程进行监测——已测量完成
- L1117 3.4.5 Specification Compliance / Instrumentation Summary  
    L1117 3.4.5 规范合规性/仪表汇总
- L1132 References  L1132 参考文献
- L1162 Further reading (uncited in this document)  
    L1162 更多阅读资料（本文档中未提及来源）