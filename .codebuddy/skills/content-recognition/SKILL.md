---
name: content-recognition
description: 理解完整视频的展示意图，核实真实切镜，在单镜头内选材并导出独立片段；支持有证据的一镜到底完整展示时长例外。
---

## 必先读取

读取仓库 CONTENT_STANDARD.md 与 CONTENT_REVIEW.md，以最新用户明确要求为准。
标准分 A 通用基础、B 可选用途、C 用户补充。默认 general，带货任务再启用 commerce，
其他类型可用 tutorial/lifestyle/documentary/comparison；不能以单一广告总分判有效。
本技能使用仓库工具，不依赖安装 Hypit 或其付费 Runtime；没有视觉能力就说明限制，不编造观察。

## 执行顺序

1. 用 recognize-content 准备任务和概览。通览全片，先填写 analysis.product_intent：
   展示对象、功能/用途意图、演示方式、可见结果、未知项及原片时间证据。未知产品用中性名称；
   功能展示价值与性能已获证明分别记录，工具接触屏幕等演示动作不能据此判废。
2. 核实物理镜头表 analysis.shot_boundaries（time/type/evidence/reason）。仅填确认的真实切点，
   疑似点另记；实际观察后才置 shot_boundary_reviewed。同场景跳剪也要拆分；
   摇推拉移、跟拍、变焦等连续运镜不算切镜。scene 分数、模糊、遮挡和构图变化都不能单独证明切镜。
   疑似切点检查相邻原始帧/连续画面，不能仅凭稀疏联系表宣称一镜到底。
3. 在各物理镜头内按展示价值和需求选材，填写 facts、editorial_value、content_roles、
   assessment.base/profile/user、reason、evidence 及原片秒数；保留 alternatives/tradeoffs。
   requirements 分 hard/preferences/exclusions，硬条件按 ID 逐项核对；未知用 uncertain。
   不将静止、自然手持、无 CTA 或未包含整套操作一律判废；说明本段表达什么、效果何时出现。
4. 普通候选默认1–4秒。明显切镜必须拆分，不允许自动片段内部含切点；
   拆分后只能在所属镜头内向前/向后补充相关画面，不跨切点凑时长。
   明确一镜到底且需完整展示效果的候选不受默认范围限制，按标准填写 duration_policy、
   display_intent、duration_reason、shot_review（范围/连续性/实际核查方法/证据）。
   不按4秒机械切碎，不截断必要效果，也不借一镜到底保留无关空等。
5. 覆盖与边界实际核实后才置 reviewed/boundary_reviewed。observe-media 支持
   --start/--end/--every 加密观察；固定窗口不是剪辑边界，不能靠外推补齐未观察动作。
   权限依据来自用户资料，未知不自行声明 allowed。
6. extract-segments 导出；默认保持原速、原画面和原声。检查实际文件的内部切镜、
   首末边界、描述及展示效果，并按 CONTENT_REVIEW.md 写明方法、覆盖、版本与未检查项。
   技术验证与语义复核分别报告；抽帧初审不能称为最终验收。

## 待审、纠错与续接

- 未核实一镜到底例外的越界完整候选放 manual-review.json/csv 和 manual-review-clips/；
  内容/用户条件/边界不确定项放 uncertain-review.json。两类均保持 needs_manual_review。
- reviewed 记录不能证明模型真的看过。产品身份、意图或连续性判断推翻时，按影响范围撤销旧结论，
  归档版本并重审所有依赖项，不能只改文件名。用户取消重做时仅记录影响，不重新处理。
- review-segments --task 任务 --decisions 结论.json 回填结论；keep 需显式 boundary_reviewed:true
  且硬条件 pass。reselect-segments --task 任务 --selections 选区.json 调整区间，须写理由且在观察覆盖内。
  两条命令都保留 history/、review-log.json；默认重新导出，--no-extract 仅记录。
- 交付 clips、clips.csv、extraction.json，分别报告默认时长片段、一镜到底例外、待审及实际输出复核数量。
  续接读 task.json、progress.json、resume.md，不重发全库历史，不覆盖未经核对的新版本。
