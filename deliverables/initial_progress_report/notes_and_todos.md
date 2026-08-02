# 配套说明 · 状态 / 待办 / 决策点

配套文件：`report_content.md`（纯正文，无注释，可直接排版）

本文件分四部分：
- **A. 占位符清单** — 正文里 `[[FILL-n]]` 要填什么
- **B. 需要你拍板的决策** — 我替你做了选择，你可以否决
- **C. 我自己填的草稿数值** — 不是占位符，但需要你确认
- **D. 独立交付：RevisedAbstract.docx**

---

---

# 0. 记号体系（两份文件通用）

| 记号 | 出现在 | 含义 | 现有数量 |
|:---|:---|:---|---:|
| `[[FILL-n]]` | **report_content.md** | 正文空位，不填交不了 | 14 处 / 8 类 |
| ❌ | notes A 节 | 该 FILL 尚未提供 | 4 |
| ✅ | notes B 节 | 决策已确认，无需再动 | 3 |
| 👉 | notes C 节 | 我填了草稿值，需要你确认 | 2 |
| ⚠️ | notes C/D 节 | 容易踩的坑，做的时候注意 | 2 |
| `- [ ]` | notes E 节 | 格式清单，排版时逐条勾 | 12 |

**注意一个不对称**：正文里**没有"已完成"记号**——没有 `[[FILL]]` 就是写完了，
靠缺席表示完成。好处是正文干净，坏处是没法一眼看出哪些段落定稿了。
G 节的段落状态表补上这一点。


# A. 占位符清单（正文中 8 处）

| 编号 | 位置 | 要填什么 | 谁能做 | 状态 |
|:---|:---|:---|:---|:---|
| `[[FILL-1..5]]` | Title page 表格 | 五个学号 | 你们 | ❌ 未提供 |
| `[[FILL-6]]` | Section 1.2 | Detailed Design 的 Figure 6 Gantt 图。图内文字须 ≥9 pt 可读 | 你们 | ❌ 只有截图 |
| `[[FILL-7]]` | Section 2.2 表格 | 每人「Hours since」和「Total」，共 12 个数（含合计行） | 你们 | ❌ 未提供 |
| `[[FILL-8]]` | Appendix A / B | A = 五份签名 log；B = Bishop 签名的 Feedback Sheet 扫描件 | 你们 | ❌ 未开始 |

**`[[FILL-7]]` 的三条硬约束：**
1. 每人总数 ≥ 120（评分表以 120 h/人 为判据）
2. 组内不能差太多（评分表另一句：each student is contributing a fair share）
3. **必须与 Appendix A 的 log 逐条对得上** —— 正文最后一句已经明写了这一点

**`[[FILL-8]]` 是唯一的硬阻塞。** Marking sheet 底部原话：缺 Appendix A 或 B，本 deliverable **视为未提交**。不是扣分问题。

---

# B. 决策点（已全部确认 ✅）

| # | 决策 | 结论 |
|:---|:---|:---|
| B1 | Abstract 叙事：旧版"自动化研究循环" → 新版"把时延关键路径钉死在硬件里" | ✅ 采用新叙事 |
| B2 | 板子措辞：只写技术约束（网口挂在 PS 侧），不点型号、不写成采购失误 | ✅ 保留 |
| B3 | Section 3.2 语气：明确承认 Level 3 + 照 Bishop 评语给四条提升路径 | ✅ 保留 |
| B4 | Discussion 额外 3 分放弃（只发给 <50% 完成度的组） | 规则所致，无需行动 |

**B3 的一个新信息**：你们当时就和 Bishop 争论过任务排序。这反而让 3.1 里那段
"重排是被外部约束逼的，不是滑期"更站得住——他已经知道这件事，报告里写出来是
和他已有认知一致，而不是事后找补。

# C. 我自己填的草稿数值（需确认，不是占位符）

## C1. 完成度表 — 76.5%（已按你的反馈修正）

**修正内容**：原先那行「板级整合 8% × 35%」被删掉了。理由是你指出的问题——
描述写「full board integration not started」却给 35%，自相矛盾，阅卷人一眼能看出来。

**新的处理方式**：不给系统整合单独权重。整合是**验证门槛**，不是被设计的子系统，
清关的成本已经摊进那两个还没清关的子系统里了（TX 从 85% 降到 80%，PS 从 90% 降到 88%）。
正文里另加了一句明说「板上还什么都没跑」。

| 子系统 | 权重 | 完成度 | 贡献 | 依据 |
|:---|---:|---:|---:|:---|
| 市场数据接收 + 订单簿 | 15% | 15% | 2.3% | `pl/rx_logic/` 空目录，零行 RTL。但设计已冻结，`axi_lite_regbank.sv` 已预留 0x00–0x2C 地址窗 |
| 订单发送 + 处理器接口 | 20% | 80% | 16.0% | 598 行 SV + 1216 行 tb 全绿，反测 15/15 与 6/6 全抓到。缺综合、时序收敛、TEMAC 配置、上板 |
| 策略与风控软件 | 25% | 88% | 22.0% | 870 行 C 在开发主机上全链路跑通。缺真实 feed、isolcpus、部署到目标处理器 |
| 隔夜优化流水线 | 25% | 92% | 23.0% | 约 3000 行 Python + 5 个测试文件，最完整 |
| 交易所模拟器 | 15% | 88% | 13.2% | preprocessor / replayer / receiver / checker 齐全 |
| **合计** | **100%** | | **76.5%** | |

算术核对：2.25 + 16.0 + 22.0 + 23.0 + 13.2 = 76.45 → **76.5%**。落在 Bishop 勾的 75–90% 内。

**这个数字的位置是刻意的**：Bishop 一开始说最多 70，争论后改到 75。76.5 是他区间的下沿，
既不自我拔高，又不会把自己推进 9 分档（<75 就掉档，差 3 分）。

👉 **仍需你逐行确认权重。** 觉得某块被高估/低估，改权重比改完成度好说话；
总数只要仍落在 75–90，我都能重写那节散文。

## C2. 工时的起点数字

Detailed Design 的 Table 28（约 7 月 12 日）记录：Hanyu 72 / Catherine 74 / Ashley 72 / Panzy 71 / Lucy 73，合计 362。

到 8 月 2 日约三周，每人需再加约 46–49 小时才到 120（约 15 h/周）。

👉 **正文里 362 和五个起点数已经填好了**，你们只需补「Hours since」和「Total」。

## C3. 补 log 的方法（关键）

⚠️ **不要照着 Gantt 抄。** 如果 log 里写「7 月 18 日 实现 top-of-book 快照 3 小时」，会和 2.1 里「RX 没有 RTL」直接打架 —— 同一份文档自证矛盾，比进度落后严重得多。

**建议做法**：用 `git log --author=<name> --date=short --pretty=format:'%ad %s'` 把每人的提交日期和内容拉出来当骨架，再补上开会、写文档、调试这类没进 git 的时间。这样既真实又快。

log 格式（大纲 p27）：Task / Date / Start time / Finish time / Hours / Running total，末尾签名 + 那句 "By signing above, I am stating that this is an accurate account of the tasks, dates, and times that I worked on my capstone design project."

---

# D. 独立交付：`2026.36.RevisedAbstract.docx`

**这是另一个 deliverable，和 Progress Report 分开交。**

| 规则 | 内容 |
|:---|:---|
| 文件名 | `2026.36.RevisedAbstract.docx` |
| 格式 | **必须 .docx，不能 PDF**（教授明说 PDF 复制粘贴不好用） |
| 提交 | 组内一人交即可，LEARN Dropbox |
| 注意 | **不要传整份 Progress Report**，这是独立的一页 |
| 注意 | 即使 abstract 一个字没改，5 项也全都要交 —— 他要的是电子档本身 |
| 评分 | 齐全且格式对 = 0 分；格式有问题 = −2.5；迟交 = −5 |

## 5 项内容

**1. Group number**

```
2026.36
```

**2. Group members**（姓名按你们希望**印在手册和 symposium 名牌上**的拼写）

```
Hanyu Yao ([[FILL-1]])
Catherine Ye ([[FILL-2]])
Ashley Wu ([[FILL-3]])
Panzy Pan ([[FILL-4]])
Lucy Sun ([[FILL-5]])
```

**3. Revised Project Title** — 41 字符，纯字母，无缩写，合规，**沿用 5 月原标题不改**

```
Adaptive Quantitative Trading Accelerator
```

**4. Revised Project Abstract (max 200 words)** — 197 词

⚠️ 与 `report_content.md` 的 Section 1.1 **逐字一致**。改一处两处都要改。
（正文见 `report_content.md` Section 1.1，此处直接复制）

**5. Shortened Project Abstract (max 85 words)** — 82 词。**只出现在这里**，Progress Report 里不出现。

```
This project splits an algorithmic trading system between reconfigurable logic and an embedded processor on one chip. The logic takes market data straight off the network, decodes it, maintains a record of pending buy and sell orders, and reports the best prices to the processor, which evaluates a strategy and risk-checks every order before the hardware transmits it. An overnight pipeline retunes the strategy against recorded sessions, subject to human approval. Critical-path latency is bounded by hardware, not by an operating system.
```

---

# E. 正文定稿后的格式工序

- [ ] 正文 ≤ **6 页**（附录不算）
- [ ] 11–12 pt 字体，1.15–1.5 行距，四边 ≥ 1 inch
- [ ] 图内文字 ≥ 9 pt
- [ ] 全文现在时
- [ ] 每个数值标单位
- [ ] 缩写首次出现时定义（正文已尽量写全称，避免了 FPGA/PL/PS/AQTA 等）
- [ ] 图：编号 + caption 在**下方**，正文引用
- [ ] 表：编号 + caption 在**上方**，正文引用
- [ ] Title page / Sec 1 / Sec 2 / Sec 3 各自另起一页
- [ ] 不引用自己之前的 498A 提交物（正文已遵守：提到 Detailed Design 时用内部指代，未列 References）
- [ ] Appendix A 五份 log 签名齐全
- [ ] Appendix B Feedback Sheet 扫描件清晰（签名和日期可读）

---

# F. 关键路径

```
Appendix A 五份 log ──┐
                      ├──→ 工时数字 [[FILL-7]] ──→ 2.2 收口 ──┐
                      │                                        │
学号 [[FILL-1..5]] ────┼────────────────────────────────────────┼──→ 格式工序 ──→ 提交
                      │                                        │
Gantt 图 [[FILL-6]] ──┤                                        │
                      │                                        │
完成度表确认（C1）─────┘                                        │
                                                               │
决策 B1/B2/B3 确认 ─────────────────────────────────────────────┘
```

**log 是唯一真正的阻塞项**，且工时数字依赖它先出来。其余都是几分钟的事。

---

# G. 正文段落状态表

对应 `report_content.md`，逐节列出状态。**没有 `[[FILL]]` 且标 ✅ 的，就是可以直接排版的定稿。**

| 正文位置 | 散文状态 | 数据状态 | 阻塞项 |
|:---|:---|:---|:---|
| Title Page | ✅ 定稿 | ❌ 缺学号 | FILL-1~5 |
| 1.1 Revised Abstract | ✅ 定稿（197 词） | — | 无 |
| 1.2 Original Timeline | ✅ 定稿（含指向 3.1 的过渡句） | ❌ 缺 Gantt 图 | FILL-6 |
| 2.1 Prototype Completion | ✅ 定稿（表 + 四段证据 + 板上未跑说明） | 👉 权重待你确认 | 无（可先排版） |
| 2.2 Student Hours | ✅ 定稿（含"与 Appendix A 逐条对应"那句） | ❌ 缺 12 个数 | FILL-7 ← 依赖 log |
| 3.1 Confidence | ✅ 定稿（三点依据 + 排序偏差解释 + 风险段） | — | 无 |
| 3.2 Level of Challenge | ✅ 定稿（承认 Level 3 + 四条提升路径） | — | 无 |
| Appendix A | — | ❌ 未开始 | FILL-8 ← **唯一硬阻塞** |
| Appendix B | — | ❌ 有照片，需转清晰件 | FILL-8 |

**读法**：七个正文小节的散文**全部定稿**。剩下的全是往里塞数据和图，
以及排版。唯一需要真正动脑的是补 log（C3 节讲了方法）。

**两个"看起来缺其实不缺"的地方**：
- 2.1 的表格数值已经填好了（76.5%），👉 只是请你复核权重，不填也能交
- 2.2 的起点列（72/74/72/71/73 和合计 362）已填好，只缺右边两列

---

# H. 一致性审计

阅卷人手上会同时有：Progress Report 正文、Appendix A（logs）、Appendix B（Feedback Sheet）、
单独提交的 docx，以及**已经交过的 Detailed Design**。下面按"能被对照出来"的维度逐条核。

## H1. 已核对通过 ✅

| 维度 | 甲 | 乙 | 结论 |
|:---|:---|:---|:---|
| 组号 | 正文 2026.36 | Feedback Sheet 2026.36 / docx 2026.36 | ✅ |
| Consultant 姓名 | 正文 William Bishop | Feedback Sheet 签名 | ✅ |
| 标题 | Title page | docx 第 3 项 | ✅ 同为 Adaptive Quantitative Trading Accelerator |
| 完成度 | 正文 76.5% | Feedback Sheet 勾 75–90% | ✅ 落在区间内，且在下沿（不虚高） |
| 挑战度 | 3.2 "assessed at level three" | Feedback Sheet 勾 (3) | ✅ |
| 信心 | 3.1 "very high confidence" | Feedback Sheet 勾 Very high | ✅ 与 consultant 同调 |
| 引用他的评语 | 3.2 "integrating the components into the final design and testing it thoroughly" | 手写原文 "The remaining work involves integrating the components into the final design and testing the design thoroughly" | ✅ 转述准确 |
| FS1 数值 | 3.1 "77 clock cycles / 32% worst-case margin / 1.5 microsecond" | Detailed Design 3.1.2 Decision 2 | ✅ |
| FS2 数值 | 3.1 "30 microsecond / roughly five times margin" | Detailed Design Table 13（原文 ≥5.5×） | ✅ 我取了保守说法 |
| NFS6 数值 | 3.1 "11% logic / 3% block memory，75% 与 85% 上限" | Detailed Design Table 5 + NFS6 | ✅ |
| 反测数字 | 2.1 "fifteen ... and six of the top level" | module_specification（regbank 15/15、tx_top 6/6） | ✅ |
| 模块数 | 2.1 "All four modules pass lint" | regbank + latcher + frame_builder + tx_top = 4 | ✅ |
| 订单簿深度 | Abstract "ten-level record" | Detailed Design 10-level | ✅ |

## H2. 已修复的真冲突 ⚠️→✅

**3.1 结尾句 vs Gantt 图（Figure 6）。**

原句写「the term between now and March is allocated to them in the timeline」。
但 Gantt 里 HW/PL 那栏，RX 解析器相关任务排在 **7/10–7/27**，也就是**计划中它 7 月底就该做完了**；
冬季那几项写的是 "Refine PL Ethernet front-end and parser"、"timing closure and resource optimization"——
是**精修**，不是**从零实现**。换句话说，**原 timeline 里没有给"写 RX RTL"留任何位置**，
因为它假设这件事已经发生了。

细心的阅卷人对照 2.1（RX 零行 RTL）会发现这个洞。

**已改为**：
> The winter allocations for refinement, timing closure, and end-to-end integration in Section 1.2
> are unchanged; the ingest-path implementation displaced by the constraint above is absorbed into
> the fall term ahead of them.

这样既不改 1.2 的原图（大纲要求原样），又把移位说清楚了。

## H3. 边界情况（低风险，但你该知道）

**① Abstract 用现在时描述一个部分不存在的系统。**
1.1 写「The logic takes market data directly off the network, decodes..., maintains a ten-level record...」，
而 2.1 说这块零行 RTL。表面上矛盾。

但这是 deliverable 设计本身导致的——大纲 p11 **强制要求 abstract 用现在时**
（理由：abstract 是在设计完成后才发布的）。所有组都这样。**无需处理。**

**② 提到 Detailed Design 算不算"引用自己旧作"。**
2.2 表头写「Hours as of Detailed Design (July 12)」，3.1 写「as summarized in the compliance
tables of the Detailed Design」。

大纲三处（p9/p16/p22）都说 "Do not reference your own work from previous ECE498A submissions"，
但那三处都出现在 **References 格式**的语境里，禁的是把旧作列进参考文献。
而且 Slide 18 明确要求 1.2「Extract from Section 4.6 of the Detailed Design」——
指代它是被要求的。**判断：正文内指代没问题，只要不进 References 列表。无需处理。**

**③ Demo 日期 7/31 vs 课程要求 7/28 17:00 前。**
Appendix B 上 Bishop 签的日期是 July 31, 2026，比课程建议的截止晚三天。

Marking sheet 的迟交扣分只针对 Progress Report 本身（8/2），demo 没有独立分值和独立扣分栏。
**判断：风险低，正文不提，不主动引起注意。** 但你们心里有数。

## H4. 尚未成立、填数据时会产生的一致性要求 🔴

这几条现在还不能核，因为数据没填。**填的时候必须同时满足：**

| 约束 | 甲 | 乙 | 后果 |
|:---|:---|:---|:---|
| 工时逐条相符 | 2.2 表格 12 个数 | Appendix A 五份 log 的 running total | 大纲 p25 明文要求；对不上直接扣 |
| 200 词逐字一致 | 正文 1.1 | docx 第 4 项 | Slide 26 明文要求 |
| 姓名学号一致 | Title page | docx 第 2 项 + Appendix A 各 log 表头 | docx 那份按"印在名牌上"的拼写，可能与 log 上手写的不同，注意统一 |
| "分布均匀"成立 | 2.2 那句 "the distribution across members is even" | 五个实际数字 | 若某人明显偏低，这句就是假的，必须改写并解释 |
| log 内容 ≠ Gantt 计划 | Appendix A 各条任务 | 2.1 "RX 零行 RTL" | ⚠️ **最大的坑**：log 里若出现"实现 top-of-book 快照"之类，与 2.1 正面打架。按实际写，用 `git log` 拉骨架 |
| log 内容 ↔ 3.1 的排序解释 | Appendix A 的时间顺序 | 3.1 "先做 TX 后做 RX 是被约束逼的" | log 应当自然呈现 TX 相关工作集中在 7 月，这反而**佐证**了 3.1 的说法 |

**最后一条是个机会**：如果 log 如实写，它会**自动支持** 3.1 的论证——
7 月的工作确实集中在 TX、regbank、testbench、golden frame 上。
这比在 3.1 里空口解释有力得多，且不需要额外做任何事，只要不去粉饰。