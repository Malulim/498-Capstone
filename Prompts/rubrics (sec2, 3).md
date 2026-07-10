## 1. Section 2 评分标准 (共 26 分)

- **分类与组织 (4 分)**：规格需条理清晰，合理分类为“功能性/非功能性”以及“基本/非基本（Essential/Non-essential）” 。
    
- **可验证性与开放性 (12 分)**：每一项规格都必须是可验证的、开放式的且难度适当 。
    
- **完整性 (5 分)**：规格集必须是完整的 （即你所设计的每个子系统都必须至少对应一项规格 ）。
    
- **挑战性 (5 分)**：规格的设定对于四年级工程专业学生（毕业设计/Capstone Project）而言应当具有足够的挑战性 。
    

## 2. 什么是好的规格？(撰写要求)

- **可验证 (Verifiable)**：必须能够通过客观手段判断其是否被满足 。必须**避免模糊描述**（例如：不能写“系统需要轻量化” ），应当**尽可能量化**（例如：“控制系统质量必须在 300 克以下” ）。
    
- **开放式 (Open-ended)**：规格应针对你所设计的系统部分，且不能直接指定具体的产品型号 。
    
    - _错误示例_：“高度计必须使用 SuperBrand X Altimeter-Z99” 。
        
    - _正确示例_：“控制系统必须能够测量 0 至 5 米的高度，精度在 5 厘米以内” 。
        
- **合适性 (Appropriate)**：不要包含无关紧要的信息，或将详细的设计决策直接当作规格 。
    
- **完整性 (Complete)**：确保你所设计的每一个子系统都有至少一项相关的规格 ，并捕捉到系统行为的所有重要方面 。
    
- **挑战性 (Challenging)**：指标应富有挑战性但兼顾现实 。例如无人机悬停误差，设置 $5\text{ cm}$ 挑战性适中，设置 $100\text{ cm}$ 毫无挑战，而设置 $0.1\text{ cm}$ 则可能太脱离现实 。
    

## 3. 核心分类：功能性 vs 非功能性

### 2.1 功能性规格 (Functional Specifications)

- **本质**：定义系统“**必须做什么 (What it does)**”，直接关系到系统的运行和行为 。
    
- **撰写要求**：列出系统的核心行为（如无人机能引导降落、自动控制等）并严格量化 。
    
- **示例**：
    
    - “四轴飞行器必须能够自主飞行至少 30 分钟。”
        
    - “四轴飞行器必须能在离地 2 米处悬停，任何方向的偏差不超过 5 厘米，旋转不超过 10 度。”
        

### 2.2 非功能性规格 (Non-functional Specifications)

- **本质**：定义系统“**以何种约束条件运行 (How it works)**”，描述系统的特性 。
    
- **撰写要求**：通常包括物理尺寸、质量、外观、成本、可靠性、维护性及易用性等约束 。
    
- **示例/约束方向**：
    
    - **物理与环境约束**：“控制系统必须能装进一个 $3\text{ cm} \times 5\text{ cm} \times 5\text{ cm}$ 的盒子内” ；或者重量限制、防水防尘等级等 。
        
    - **性能与资源约束**：电池续航时间、峰值电流、系统响应延迟（如图像处理在 100 毫秒内） 。
        
    - **成本与耐用性**：开发成本限制（如不超过 $500）、耐用等级（如承受 2 米跌落） 。
        

## 4. 优先级分类 (Necessity)

无论是功能性还是非功能性规格，都必须严格区分为以下两类 ：

- **基本规格 (Essential)**：项目**必须满足**的核心指标。如果不满足，设计将被视为不合格 。
    
- **非基本规格 (Non-essential)**：对基础运行不那么关键的附加功能 。若能满足，会让项目更加优秀，但**不要包含毫无希望或完全不想去实现的规格** 。
    

## 5. 推荐的表格结构与撰写操作

报告应以**表格形式**呈现，必要时辅以文字段落解释 。标准表格应包含以下三列核心要素 ：

|**1. Specification (规格名称) PDF**|**2. Description (详细描述) PDF+ 1**|**3. Classification/Necessity (优先级分类) PDF+ 1**|
|---|---|---|
|定义具体的指标/规格名称|解释该规格的具体行为、高度量化的参数或物理限制|严格标注为 **Essential** 或 **Non-Essential**|

**操作建议**：在撰写时，将“核心功能”与“系统约束”严格分离 。同时，可根据每个指标的物理属性，提前规划好该指标后续是适用于“真实物理测试”还是“软件平台模拟” 。


# Section 3: Detailed Design — Full Requirements + Grading Rubric (Do / Don't)

## Structure

```
### Section Overview
- Section 3 is the most important section of the Detailed Design report.
- Include one subsection for each subsystem (or possibly group of subsystems) that you designed.
- Subsection names must match exactly with those on your Block Diagram.

### Structure Template
- 3.1 Subsystem X Design
- 3.2 Subsystem Y Design
- 3.3 …

### Content Requirements (per subsection)
- Give a detailed description of your final design for the subsystem.
- Include enough detail that, ideally, another group could use your documentation to construct a prototype.
- Explain clearly why/how your design satisfies the project specifications.
- Refer back to specs explicitly using their IDs (FS1, FS2, …, NFS1, NFS2, …), since specs are supposed to drive the whole design process.
- Explain clearly the design iterations and/or alternative designs that you considered.
- Demonstrate how you followed an engineering design process (creative, iterative, open-ended).
- Consider using decision matrices to support alternative-selection reasoning.
- Clearly justify all significant design decisions related to iterations and/or alternatives.
- Arguments must be logical, clear, complete, and substantial — minimize simplistic, superficial, or vague reasoning.
- Use references/citations to support arguments.
- Include quantitative technical analysis (QTA) — engineering theory and/or simulations — to justify decisions and/or evaluate the design.
- At least some of the design/analysis must be at an advanced level, requiring substantial upper-year (3rd/4th-year) ECE knowledge.

### Acceptable Supporting Material Types
- Circuit schematics, PCB layouts, pseudo-code (or code fragments)
- UML diagrams, flowcharts, state diagrams, ER diagrams, data flow diagrams, timing diagrams
- CAD drawings, part listings

### Citation Requirements
- Reference datasheets for all hardware components used.
- Reference any code taken from other sources.
```

---

## Grading Rubric — Detailed Do / Don't by Dimension

_(Rubric spans Unsatisfactory → Satisfactory → Good → Excellent → Outstanding. Below: what "Outstanding" looks like — DO this — vs. what "Unsatisfactory" looks like — DON'T let it happen.)_

```
### 1. Complexity of Design Task
DO:
- Aim to have 4 or more subsystems that involve open-ended design.
DON'T:
- Have the project involve only 1 subsystem with open-ended design, or no open-ended design at all — this is Unsatisfactory territory.
- Note the gradient: 2 subsystems = Satisfactory, 3 = Good, 4+ = Outstanding/Excellent.

### 2. Quality of Final Design
DO:
- Convincingly show the design meets the project objective and satisfies ALL specifications (essential + non-essential).
- Aim for a design that is highly novel, elegant, and creative — described as "a truly great accomplishment."
DON'T:
- Leave any essential spec unshown/unmet — even one missing essential spec drops you to Unsatisfactory.
- Submit a design that is incomprehensible or inadequately described — clarity of description is graded, not just the design itself.
- Settle for "relatively simple" designs with no novelty if aiming higher than Satisfactory.

### 3. Use of Engineering Design Process
DO:
- Propose a reasonable solution backed by thorough investigation of serious alternatives and/or iterations.
- Make the design process clearly systematic, comprehensive, and substantial.
DON'T:
- Make only a "minimal attempt" to explain alternatives or an iterative process.
- Write process descriptions that are trivial, superficial, irrelevant, poorly explained, or very vague — this is explicitly called out as Unsatisfactory.
- Just assert "we considered alternatives" without walking through the actual investigation.

### 4. Quality of Justifications
DO:
- Make arguments logical, clear, complete, substantial, and sophisticated.
- Support all major claims with complete, authoritative citations.
DON'T:
- Submit justifications that are missing, minimal, or incomprehensible.
- Use arguments that are illogical, faulty, simplistic, trivial, or vague.
- Leave citations missing or poorly used — "difficult to follow, unpersuasive, or have many gaps" is explicitly Satisfactory-level, not higher.

### 5. Level of Knowledge Used
DO:
- Clearly demonstrate substantial 4th-year ECE technical knowledge in your analysis or design.
DON'T:
- Rely on knowledge that amounts to "little beyond first-year engineering" — this is Unsatisfactory.
- Aim only for "second-year" or "third-year" level content if you want above Good/Excellent — Outstanding specifically requires 4th-year-level substance.

### 6. Breadth and Depth of Quantitative Technical Analysis (QTA)
DO:
- Apply detailed and substantial QTA convincingly to ALL aspects of the design.
- Make extensive use of engineering theory, simulation, and/or data analysis tools.
DON'T:
- Leave QTA missing, minimal, incomprehensible, trivial, superficial, or irrelevant.
- Submit QTA with major errors/gaps.
- Choose design decisions or a design that isn't even amenable to QTA (i.e., pick problems you can actually analyze quantitatively).
```

---

## QTA-Specific Rules (separate from rubric, but directly feeds "Quality of Justifications" + "QTA" rows)

```
### What Counts as QTA
- Data-driven: must reference specific datasets, measurements, or simulations that informed design decisions BEFORE the solution was built.
- Quantifiable metrics: numerical values, performance benchmarks, comparative analyses specific to your situation.
- Optimization: references to optimization algorithms, parameter tuning, sensitivity analysis.
- Mathematical models: equations, algorithms, or simulations of system behavior.
- Rigorous analysis: mathematical derivations, statistical analyses, or computational simulations.
- Evidence-based conclusions: backed by empirical evidence/quantitative analysis, not anecdote, intuition, or a decision matrix alone.
- Iterative: show multiple iterations, sensitivity analyses, or trade-off studies; document prior iteration results too.

### What Does NOT Count as QTA
- Copying a well-known formula and just saying "we used it" — you must show how/why you used it and what your calculations were.
- Trivial calculations (e.g., Ohm's Law to size a current-limiting resistor).
- Evaluating a tool you're using based on external/cited data rather than your own measurements (e.g., citing DB access speed benchmarks instead of measuring it yourself).
- Analysis must involve substantial 3rd/4th-year concepts — first/second-year-level math doesn't qualify.
```

***
## smaples总结
综合这15份高分项目设计文档，你会发现尽管项目内容千差万别（从无人机电池更换、智能垃圾桶到纯软件的播客推荐系统），但**每一个Subsystem（子系统）的编写逻辑都遵循着一个高度标准化的“叙事弧线”**。

这个通用的编写逻辑可以概括为：**“提出问题 -> 探索并对比方案 -> 做出科学决策 -> 呈现最终技术细节”**。

如果你们要在Section 3写具体的Subsystem，可以严格套用以下**四步走的典型逻辑（Typical Writing Logic）**：

### 第一步：子系统概述与需求映射 (Overview & Requirements Mapping)

在进入具体的技术细节前，每个子系统都会先“定调”，明确这个模块存在的意义以及它必须满足的硬性指标。

- **编写逻辑：** 简要说明该子系统的核心功能，并**明确指出它对应了Section 2中的哪些规格（Specifications）**。
- **来源印证：** 例如在分布式垃圾收集系统（2015.034）中，垃圾桶分配子系统的第一节就是“Problem Characterization（问题特征）”，直接列出了该子系统需要满足的响应时间和定位要求。在教育级RF接收器（2017.008）中，RF子系统的开头也明确解释了信号在经过该阶段时的目标（如将频率下变频到40MHz）。

### 第二步：工程设计过程 (Engineering Design Process) —— 【得分核心】

这是体现你们“Engineering Justification（工程合理性）”的最重要部分。不要直接甩出最终设计，而是要展示你们的思考过程。这一步通常有两种典型的写法（可任选其一或结合使用）：

**模式 A：备选方案对比与决策矩阵 (Alternatives & Decision Matrices)**

- **编写逻辑：** 提出2到3种可行的技术方案，设立评估标准（如：复杂度、成本、功耗、速度等）并赋予权重，通过打分表（Decision Matrix）计算总分，得分最高者胜出。
- **来源印证：**
    - **硬件/机械：** Geo-Doodle项目（2017.030）在设计升降执行器时，对比了液压缸、带丝杠的步进电机和齿轮杆，通过对复杂度（30%）、耐用性（20%）、成本（15%）等打分，最终科学地选择了步进电机。
    - **软件：** 播客应用（2017.001）在选择Web应用框架时，通过加权矩阵对比了Angular、React、Vue等框架的渲染速度和社区支持。Insightful项目（2017.012）详细对比了SQL与NoSQL、MySQL与PostgreSQL等数据库方案。

**模式 B：原型迭代记录 (Design Iterations)**

- **编写逻辑：** 按照“原型 (Prototype) -> 测试 (Test) -> 分析 (Analyze) -> 改进 (Refine)”的循环来写。描述第一版设计遇到了什么瓶颈，第二版又是如何解决的。
- **来源印证：** 自动冰球机器人（2015.031）在设计线性执行器时，详细描述了第一版使用螺纹杆（Threaded rods）导致速度太慢，最终迭代为同步带（Timing belt）以满足冰球的高速移动需求。垃圾收集系统（2015.034）的网络子系统也清晰列出了从本地测试到Ubuntu服务器部署的多次迭代循环。

### 第三步：最终设计细节 (Details of Final Design) —— 【技术实力展现】

在通过“第二步”证明了你们的选择是合理的之后，这一步需要提供详尽的工程交付物，让读者觉得“拿着这份文档就能复现这个子系统”。

**不同领域的典型输出套路（We shall do）：**

- **软件/算法子系统：**
    - 必须包含架构图或数据流图。
    - 如果是数据库，提供实体关系图（ER Diagram）和Schema规划。
    - 如果是控制逻辑，提供状态机图（State Machine）或流程图（Flowcharts）。
    - 关键算法可以附上伪代码（Pseudocode）或核心代码片段。
- **硬件/电路子系统：**
    - 提供电路原理图（Schematics）。
    - 展示元件清单（BOM / Parts List）。
    - 附上涉及的物理、电气或热力学计算公式。例如家庭酿酒机（2016.019）中列出了热量计算的偏微分方程和储罐厚度的受力计算公式。
- **机械/结构子系统：**
    - 提供3D CAD渲染图，强烈建议使用**爆炸图（Exploded View）**来展示内部层级关系。
    - 标明具体尺寸和材料选择。例如无人机电池更换站（2017.032）展示了电池仓内部磁铁和PCB板安装位置的详细CAD切面图。

### 第四步：分析与总结 (Analysis / Conclusion)

- **编写逻辑：** 在子系统的小节末尾，用简短的一两段话总结该最终设计是如何完美解决第一步中提出的需求规格的。
- **来源印证：** 在RF接收器项目（2017.008）中，子系统的末尾会有一张表或一段总结，明确解释“因为我们采用了X设计，所以成功实现了Y精度（如2cm的降落误差容限）”。

---

### 💡 你们在写 Section 3 时的 Checklist (We shall do):

在撰写每个Subsystem时，问自己以下几个问题：

1. **[ ] 开场白：** 我们有没有说清楚这个Subsystem的作用，以及它对应Section 2的哪条Requirement？
2. **[ ] 方案对比（最容易拿分的点）：** 我们有没有使用表格（Decision Matrix）来对比至少两种备选方案（如传感器A vs 传感器B，或者算法A vs 算法B）？有没有给出各个维度的权重？
3. **[ ] 可视化：** 这个子系统有没有至少一张图表？（软件的流程图/ER图、硬件的电路图、机械的CAD图）。
4. **[ ] 数据与公式：** 如果有关键参数（比如电机的扭矩、服务器的吞吐量、算法的复杂度），有没有写出计算过程或给出参数表？