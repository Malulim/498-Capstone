# 交叉引用修正清单 — 498 finalizing.md

目标文件:`498 finalizing.md`
核对依据:Section 2 spec表格、Section 3 标题结构(3.1–3.4)、Table 1–29 标题、Figure 1–6 标题、References [1]–[16]。

**已核对无问题(不需要动):** 全部16条引用[1]–[16]在正文引用和参考文献列表之间完全一一对应;全部29张Table编号连续,没有跳号或重号;全部6张Figure编号连续,跟各subsystem对应一致;所有"Decision N"跨节引用(包括3.1到3.4之间互相引用的)都指向正确的决策;除下面列出的几处外,其余所有FS/NFS编号引用都能在Section 2里对上号。

---

## 1. 结构性问题:"五个subsystem"的说法跟实际标题结构对不上

**位置:** 第65行,Section 3 开篇第一段。

**现在的原文:**
> "This detailed design is organized as **five** open-ended subsystem designs rather than as a single monolithic trading appliance. The **PL RX Market-Data Ingest and Book Builder subsystem** owns deterministic packet reception... The **PL TX Order Egress and PS Interface subsystem** owns the reverse path..."

**问题在哪:** 这段话把 PL RX 和 PL TX 描述成两个独立的顶层subsystem(这样加起来正好是5个:PL RX、PL TX、PS、EOD、Exchange Simulator)。但实际的标题结构里只有**4个顶层subsystem**:`## 3.1 PL (FPGA) Market Data Path Subsystem`、`## 3.2 PS...`、`## 3.3 EOD...`、`## 3.4 Exchange Simulator...`。RX和TX只是3.1内部的两个子小节(`#### 3.1.3.1 RX Ingress and Book-Builder Subsystem` 和 `#### 3.1.3.2 TX Order-Egress and PS Interface Subsystem`),各自都没有独立的Overview / Engineering Design Process / Final Design Details / Compliance Summary——它们共用3.1这一整套。

**为什么重要:** 如果rubric要求5个open-ended subsystem(官方评分rubric里5/6人组那条脚注),按标题数的人会数出4个,不是5个。正文里说的和文档骨架对不上。

**修改方向(二选一——这是架构决定,不是简单改字):**
- **方案A:** 把 PL RX 和 PL TX 真正提升成独立的顶层section:把现在的`## 3.1`拆成`## 3.1 PL RX Market-Data Ingest and Book Builder Subsystem`和`## 3.2 PL TX Order Egress and PS Interface Subsystem`,各自补齐自己的3.X.1/3.X.2/3.X.3/3.X.4结构,然后把现在的3.2/3.3/3.4(PS/EOD/Simulator)依次往后挪成3.3/3.4/3.5。这是个大改动——后面所有指向`3.2.x`、`3.3.x`、`3.4.x`的交叉引用也都要跟着重新编号。
- **方案B:** 把"five subsystems"这句话改回"four subsystems,PL subsystem内部围绕RX/TX两条跨lane设计组织"——改动小很多,但如果rubric真的要求5个,这样就拿不到5个subsystem的分。

**建议操作:** 先跟团队确认实际人数是不是5/6人、是不是真的需要5个,再决定走方案A还是B,不要直接动笔。

---

## 2. NFS8 被引用了3次,但Section 2里从来没定义过

Section 2.2(`## 2.2 Non-Functional Specifications`,第48–61行)的表格里只定义到NFS6。NFS8在Section 2里完全不存在,但Section 3.2里当作真实存在的spec引用了三次:

| 编号 | 行号 | 现在的原文 | 建议 |
|---|---|---|---|
| 2.1 | 292 | `\| NFS8 \| Owner of software fault handling: malformed-config rejection at load time, fault-coded logging, continue-without-restart. \|`(Table 10,PS spec mapping表里的一行) | 要么(a)在Section 2.2表格里补一行NFS8的正式定义(用这句描述,再定essential/non-essential),要么(b)如果NFS8是之前草稿里就故意砍掉的spec,就把这一行删掉,把"software fault handling"这个内容并到别的已有spec描述里去。 |
| 2.2 | 378 | `\| 0x20–0x2C \| DIAG_PARSE_ERR, DIAG_FCS_FAIL, DIAG_DROP_OOW, DIAG_TX_BACKPRESSURE \| R \| NFS8/NFS2 counters, read periodically by core 0 \|` | 跟上面2.1的决定保持一致——如果补了NFS8就保留"NFS8/NFS2",如果砍了NFS8就把"NFS8/"这个前缀去掉,只留"NFS2 counters..."。 |
| 2.3 | 482 | `Linux + isolated core, no hot-path allocation; fault paths per NFS8; HOLD Mode as safe state`(Table 18,NFS4合规表里的一行) | 同上的决定——保留"per NFS8"(如果补了定义),或者改成不带spec编号的纯文字描述。 |

**建议做法:** 把NFS8正式补进Section 2.2的表格(Table 2)里——它显然是有实际内容支撑的(被引用3次,而且跟3.2.3.1/3.2.3.4/3.2.4里的真实设计内容挂钩),只是缺了定义那一行。参考NFS1–NFS6的写法,建议措辞:

```
| NFS8 | Software fault handling | Malformed configuration is rejected at load time, all faults are fault-coded and logged, and the session continues without a restart. | [选一个跟其他行风格一致的验证方法] | Y |
```

---

## 3. FS13 在这份文档的编号体系里不存在——应该是FS11

这份文档在砍掉早期的text/LLM-sentiment相关spec之后重新编过号(Section 2.1的FS表格编到FS1–FS12,其中FS11 = "Order packet format")。FS13是重新编号之前的旧编号残留,在这里根本不存在。

| 编号 | 行号 | 现在的原文 | 改法 |
|---|---|---|---|
| 3.1 | 208 | `The latched fields are packed into the fixed-format FS13 order payload defined in *Table 7* below.` | 把`FS13`改成`FS11` |
| 3.2 | 224 | `...so FS13 verification can parse captured packets independently of PS-side formatting logic.` | 把`FS13`改成`FS11` |
| 3.3 | 239 | `*Table 7: TX Order-Egress and PS Interface Subsystem Output Packet Contract (FS13)*` | 把`(FS13)`改成`(FS11)` |

---

## 4. "input validation per 3.3.3.6" 应该是 3.3.3.1

**位置:** 第504行,Table 19(EOD spec mapping表),NFS5那一行。

**现在的原文:**
> `\| NFS5 (non-ess.) \| Sole owner: full pipeline (ingestion → classification → optimization → approval prompt) within 30 minutes; input validation per 3.3.3.6. \|`

**问题在哪:** `3.3.3.6`这一节的标题是"FS10 status reporting"(日志相关),不是input validation。真正做输入校验的内容("schema check, monotonic-timestamp check, minimum-history check...")在**3.3.3.1**("Data import and Parameter Engineering")里。

**改法:** 把这一行里的`3.3.3.6`改成`3.3.3.1`。

---

## 5. "canonical serialization (3.3.3.7)" 应该是 3.3.3.5

**位置:** 第630行,3.3.3.3节里的"FS7 determinism"那一段。

**现在的原文:**
> `...strictly sequential evaluation over ordered-list grids with canonical serialization (3.3.3.7), a single designated verification host...`

**问题在哪:** `3.3.3.7`是"Operator Approval and configuration transmission (FS8)",跟序列化格式没关系。真正管序列化的是**3.3.3.5**("JSON configuration schema")——它的`provenance`字段里有个`grid hash`,这才是"serialization is canonical"这句话的真实依据。

**改法:** 把这句话里的`(3.3.3.7)`改成`(3.3.3.5)`。

---

## 6. Table 18(PS Specification Compliance Summary)里引用了好几个根本不存在的子节编号

`3.2.4`这一节("Specification Compliance Summary")**没有任何子节**——就是一张表,没有3.2.4.1/3.2.4.2这种细分。`3.2.3.3`("Runtime Risk Guard")也没有3.2.3.3.1这个子节。以下几处全部是空引用:

| 编号 | 行号 | 现在的原文 | 应该指向 | 为什么 |
|---|---|---|---|---|
| 6.1 | 381 | `\| 0x54 \| TX_READY \| R \| Egress flow-control invariant (see 3.2.4.1) \|`(Table 15,寄存器映射表) | **3.2.2** | TX_READY作为"a correctness invariant rather than a performance mechanism"以及软件时序预算(Table 13)实际上是在3.2.2 Decision 3里讲的。 |
| 6.2 | 446 | `Busy-poll isolated core + register reads; ≤ ~5 μs software path vs. ~29 μs share (3.2.4.1)`(Table 18,FS2那行) | **3.2.2** | 同上——"~5 μs vs ~29 μs"这个数字就是3.2.2 Decision 3里的Table 13。 |
| 6.3 | 476–477 | `FS2 path is the PS contribution; margin table 3.2.4.1`(Table 18,NFS1那行——因为表格换行被拆成了"table 3."+"2.4.1"两截) | **3.2.2** | 同一张表(Table 13)才是"margin"这个说法的真实出处。 |
| 6.4 | 461 | `Static allocation, decision-complete + sampled-snapshot ring, async flush (3.2.4.2)`(Table 18,FS5那行) | **3.2.3.5** | 3.2.3.5"Execution Logger and Console"才是讲日志环形缓冲、内存分配、flush行为的地方。 |
| 6.5 | 466 | `Pre-allocated open-order table sized exactly to the FS3's in-flight ceiling; Risk Guard rejects at limit; modeled terminal transitions (3.2.3.3.1)`(Table 18,FS12那行) | **3.2.3.3** | 3.2.3.3"Runtime Risk Guard"才是讲open-order table和建模成交延迟T的地方;根本没有".1"这个子节,直接去掉后面的".1"就行。 |

**改法:** `3.2.4.1`全部改成`3.2.2`(共3处:6.1、6.2、6.3),`3.2.4.2`改成`3.2.3.5`(1处:6.4),`3.2.3.3.1`改成`3.2.3.3`(1处:6.5)。

---

## 7. "Table 3.1.3" 是旧式表格编号残留——应该是"Table 6"

**位置:** 第740行,3.4.3.1节("Components and artifacts")。

**现在的原文:**
> `- **Frame file** — the slice pre-encoded into Table 3.1.3 payloads, each frame keeping its original NASDAQ timestamp for pacing.`

**问题在哪:** 这份文档全篇用的是顺序表格编号(Table 1、2、3...一直到29),不是老式的`3.1.3`这种带小数点的编号。这句话说的RX数据格式表,其实就是**Table 6**("RX Ingress and Book-Builder Subsystem Input Payload Contract")——3.4.1节(第679行)对同一个概念就正确地写成了"Table 6",可以互相印证。

**改法:** 把`Table 3.1.3`改成`Table 6`。

---

## 快速执行汇总表

| 编号 | 行号 | 查找 | 替换成 |
|---|---|---|---|
| 3.1 | 208 | `FS13 order payload` | `FS11 order payload` |
| 3.2 | 224 | `so FS13 verification` | `so FS11 verification` |
| 3.3 | 239 | `Contract (FS13)` | `Contract (FS11)` |
| 4 | 504 | `input validation per 3.3.3.6` | `input validation per 3.3.3.1` |
| 5 | 630 | `canonical serialization (3.3.3.7)` | `canonical serialization (3.3.3.5)` |
| 6.1 | 381 | `invariant (see 3.2.4.1)` | `invariant (see 3.2.2)` |
| 6.2 | 446 | `~29 μs share (3.2.4.1)` | `~29 μs share (3.2.2)` |
| 6.3 | 476–477 | `margin table 3.2.4.1` | `margin table 3.2.2` |
| 6.4 | 461 | `async flush (3.2.4.2)` | `async flush (3.2.3.5)` |
| 6.5 | 466 | `transitions (3.2.3.3.1)` | `transitions (3.2.3.3)` |
| 7 | 740 | `Table 3.1.3 payloads` | `Table 6 payloads` |
| 2 | 292, 378, 482 | NFS8未定义 | **不是简单查找替换**——需要团队先决定:是把NFS8补进Section 2.2表格,还是把3处引用全删掉。具体建议措辞见上面第2条。 |
| 1 | 65 | "five subsystems"跟4个标题对不上 | **不是简单查找替换**——这是架构决定。见上面第1条,方案A(真的拆成5个顶层subsystem)或方案B(把prose里"five"改回"four")。 |

第3、4、5、6、7条是可以直接查找替换的机械性修改,没有歧义。第1、2条需要先由负责scope/spec的人拍板再动手改。
