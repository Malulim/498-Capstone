# Formatting Checklist（跨文档汇总）

## 字体 / 行距 / 页边距
- [ ] 正文字体 11 或 12pt（专业字体均可，如 Arial）
- [ ] 行距 1.15–1.50
- [ ] 页边距四边至少 1 inch (2.54cm)
- [ ] 图内文字至少 9pt
- [ ] TOC 和 References 可用单倍行距

## 页数限制
- [ ] Specs + Risk Assessment 文档 ≤ 10 页（含 title page/TOC/references）
- [ ] Detailed Design and Project Timeline 文档 ≤ 30 页（含 title page/TOC/references/appendices）
- [ ] 页数矛盾表述已向老师澄清 ✅

## Heading / 标题
- [ ] Heading 颜色改成 Word 真正的 Automatic token（不是 hex #000000），全文一次性生效
- [ ] 连字符标题：连字符后词首字母大写（Non-Functional、High-Level）
- [ ] Section title 后不能直接接 table/figure/下一个 section title，需加过渡文字
- [ ] 过长标题精简为单行（如 "Order Book存储对比" → `Parse Architecture`），对比内容放正文

## 数值 / 单位
- [ ] 数值与单位之间加 non-breaking space（Alt+0160 / Unicode 00A0）
- [ ] 区间用 "to" 而非短横线："50 microseconds to 100 microseconds"
- [ ] 每个数值都完整跟单位

## 表格 (Tables)
- [ ] Caption 放在表格**上方**，编号，正文先引用再出现
- [ ] 表格数字右对齐（位宽表、latency 表）
- [ ] 表格字号可用 10pt 省空间
- [ ] 跨页表格：缩列宽/减字距/Ctrl+Enter 推页，尽量压到同一页
- [ ] 检查列宽过窄导致内容被挤多行的问题，精简措辞或加宽
- [ ] 每条 spec 标注 Essential / Non-essential

## 图 (Figures / Block Diagram)
- [ ] Caption 放在图**下方**，编号，正文先引用再出现
- [ ] 靠近首次提及位置放置，避免跨页截断
- [ ] Block diagram 字体太小 → 回源文件（Draw.io/Visio/PPT）重做，100%缩放下可读
- [ ] 长标题拆两行换取更大字号
- [ ] 箭头不压在文字上
- [ ] Legend 改成色块+标注图例框（非纯文字）
- [ ] 图中标出 inputs / subsystems / outputs，4–6 个 subsystem 为宜

## 甘特图 (Gantt Chart)
- [ ] 增强因果/时间逻辑展示，任务起止清晰、耗时比例可比较
- [ ] 用颜色编码区分组员
- [ ] 缩小左侧描述列（移到图表下方），加宽时间轴，加垂直分隔线
- [ ] 若与某表格内容重合，考虑直接用图表替代表格

## 引用 / References
- [ ] IEEE 格式，[1][2][3] 按正文首次出现顺序编号
- [ ] 每条 reference 至少被正文引用一次
- [ ] 确认是否真的不能引用自己之前的 ECE498A 提交（待与老师确认）
- [ ] 图/表取自其他来源需在 caption 中注明

## 其他结构类
- [ ] 空章节（如 Section 1 和 1.1 之间无内容）补过渡段或合并
- [ ] 删除临时占位的伪代码/流程图
- [ ] Title page 和 TOC 留到最后统一制作
- [ ] Title page 包含：组号、姓名/学号/邮箱、consultant 姓名、University/Faculty/Department 全称、项目标题、提交日期
- [ ] TOC 单独占一页，页码从 title page 之后开始编号
