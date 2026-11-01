# 视觉 API

统一使用 OpenAI 兼容 Chat Completions 图片协议，可配置 DeepSeek、GPT 和
CC Switch 暴露的兼容转接地址。不是读 CC Switch 私有数据库，不改其配置，
转接必须支持图片输入和 /chat/completions；仅支持 Responses 或 Anthropic 的端点暂不能用。

config/ 中提供三份示例。base_url 不包括 /chat/completions；密钥只读取 api_key_env
指定的进程环境变量，不写配置。GPT 和转接模型名由实际账户支持的视觉模型填写。

```bash
./run.sh recognize-content --video /path/video.mp4 --request '提取完整使用演示' --output ./work/task
./run.sh analyze-content-api --task ./work/task/task.json --config ./config/vision.deepseek.example.json --allow-paid
```

每20秒观察一批，相邻批次重叠4秒：0–20、16–36、32–52……。
候选按中点分配到唯一主责批次，近乎相同的区间在密集复核前先去重；候选随后密集抽帧，
再由视觉API按多维标准与同一套用户条件复核，通过后写回 task.json。
触及内部窗口边缘的候选可能未完整，标为 uncertain，不强行拼接不同动作。
超过重叠范围的长动作仍可能需要人工确认，不保证全部跨窗事件被自动合并。
短暂画面按用户要求不额外追求捕获。

## 复核可以修正边界，但只能在已观察范围内

密集复核除判断内容外，可返回修正后的 `start`/`end`。程序按以下顺序校验，任何一项不满足
都不采用修正，并保留原区间、把候选标为 uncertain 并写明原因：

1. 起点与终点必须同时给出且为有效数字，起点早于终点；
2. 修正后的区间必须仍落在**本批复核的已观察窗口**内，不靠外推补齐未看到的动作；
3. 修正后重新抽该区间的密集帧作为证据，不复用旧区间的帧。

采纳修正时保留痕迹：

- `original_start` / `original_end`：首次修正前的原区间；
- `boundary_history`：每项含 `source`（`api_dense_review` 或 `manual_reselect`）、
  `from`、`to`、`reason`、`at`；
- `boundary_corrected: true`。

## 标 keep 之前先过用户硬条件

候选只有同时满足以下条件才会写入 `decision: keep`：

- 复核自身判定 keep 且 `boundary_reviewed` 为 true；
- 未触及观察窗口边缘；
- 通用维度齐全，`evidence_sufficiency` 为 pass，其余维度无 fail/unknown，
  conditional 时必须有 `use_conditions`；
- `requirements.hard` 与 `requirements.exclusions` 的每个 id 都有 `result: pass`。

任一硬条件结果为 unknown 或缺失时写 `decision: uncertain` 并说明是哪个 id，
不再等到 `extract-segments` 才整批失败。`requirement_match` 同步写为
match/mismatch/unknown。

`extract-segments` 对单个片段的内容问题同样只把该片段放进 `uncertain-review.json`，
其余已核实片段照常导出；只有任务数据本身损坏（时间越界、ID 重复、缺证据等）才整体报错。

## 返回与后续

返回 task.json、api-analysis.json、api-progress.json 和请求缓存。
之后 extract-segments 默认1–3秒；核实的一镜到底完整展示可例外，其余越界单独待审。例外字段见 CONTENT_STANDARD.md。
分析阶段 reviewed 表示完成采样分析，不表示人工逐帧验收，method 保存 api_sampled_frames。
不自动推断素材授权。--allow-paid 允许图片/文稿发往配置服务并可能计费，不是费用上限。
不自动重试未知状态请求，不切换替代收费服务。

人工处理待审项：

```bash
# 回填人工结论（decision/facts/reason/user 结果/boundary_reviewed），归档旧 task.json 后重新导出
./run.sh review-segments --task ./work/task/task.json --decisions ./work/task/decisions.json --reviewer me
# 人工重新选区，校验仍在已观察范围，原区间写入 boundary_history 后重新导出
./run.sh reselect-segments --task ./work/task/task.json --selections ./work/task/selections.json
```

两条命令都会把上一版 task.json 复制到任务目录 `history/`，并追加 `review-log.json`
（含 before/after 快照、原因与审核人）。加 `--no-extract` 只记录结论、暂不导出。

## 离线测试范围

离线测试覆盖协议载荷、缓存、付费开关、窗口重叠与候选归属、边界修正与越界拒绝、
硬条件未确认时的 keep 拦截，以及模拟响应下从解析到分割导出的完整链路
（真实本机 FFmpeg 抽帧与编码，HTTP 边界用假服务替代）。真实服务和视觉判断质量未实测。

## 与最新识别流程的区别

标准与 WorkBuddy 执行流程以 CONTENT_STANDARD.md、CONTENT_REVIEW.md 为准。当前 API 入口仍为分批采样候选及密集复核，尚未保证完成整片产品意图的独立预审或完整切点表，不能把 API 成功等同于新流程的最终验收。
已记录真实切点不得位于自动片段内部；摇推拉移等连续运镜不属于切镜。同镜头内可调整补足默认时长；有证据的一镜到底展示例外优先保留必要效果。跨窗长展示若证据不足须续接观察或待审，不能为适应窗口而切碎。
