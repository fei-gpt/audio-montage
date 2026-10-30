---
name: content-recognition
description: 理解整段原视频，按用户剪辑目的识别有效与无效镜头，自动确定多个区间并导出独立素材。用于从长视频选材，不要求用户先提供裁切时间。
---

读取仓库 CONTENT_STANDARD.md，按其初版标准观察。使用 recognize-content 创建任务和概览证据。
先理解整片结构，在 task.json 的 analysis 中记录整体内容、观察覆盖区间及未解问题。
检查全部概览，场景变化附近和候选动作加密观察，使用 observe-media 对 assets 中的记录
指定 --start/--end/--every。只有实际看过证据才能写观察事实。
不能仅用三帧认定完整动作；候选边界要检查连续变化，必要时播放或更密集抽帧。
没有视觉能力就停止并说明，不能凭文件名/模型猜测生成标注。

根据本次 request 写 requirements，将片段分为 keep/reject/uncertain，记录事实、
剪辑价值、质量问题、决定理由、原视频秒数及证据。一个长镜头可取多段；语义边界
不受固定窗口约束。未知产品信息留空。失败动作也可能适合反例，以用户目的为准。
覆盖和边界核实后才置 reviewed/boundary_reviewed。权限来自用户提供资料，不能自行猜测。
执行 extract-segments --task 任务路径；独立片段默认原速、原画面和原声。
交付 clips、clips.csv、extraction.json，说明无效及待确认内容。进度保存在 progress.json，
续接读取 resume.md 和 task.json，不重新发送全库历史。
本技能依赖完整仓库，不依赖 Hypit 安装或其付费 Runtime。

按标准的带货维度记录镜头用途、可见事实与不能支持的商业主张；允许一镜多用。
不强套广告时长/脚本，不把自然手持、静止画面或失败操作一律判废。
判断应依次经过：Hypit 式整体与连续观察→带货角色分析→本次需求匹配→技术与边界审核。

明确区分标准层级：A 通用基础、B 可选用途、C 用户补充。
默认 general，识别为带货任务再启用 commerce；不要将带货标准泛化到所有素材。
按 content-v2 模板填写 assessment.base/profile/user；用户硬条件按 id 逐项检查，
偏好作为权衡，保留 alternatives/tradeoffs。不存在“总分高即有效”的决策捷径。

自动导出单镜头硬区间1–3秒（含端点）。短于1秒或超过3秒时保留完整候选，交 manual-review
清单，不强行补长、截断或机械分段。交付时明确自动导出数量与时长越界待审数量。
