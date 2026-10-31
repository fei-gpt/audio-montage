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
候选按中点分配到唯一主责批次，近乎相同的区间去重；候选随后密集抽帧，
再由视觉API按多维标准与同一套用户条件复核，通过后写回 task.json。
触及内部窗口边缘的候选可能未完整，标为 uncertain，不强行拼接不同动作。
超过重叠范围的长动作仍可能需要人工确认，不保证全部跨窗事件被自动合并。
短暂画面按用户要求不额外追求捕获。

返回 task.json、api-analysis.json、api-progress.json 和请求缓存。
之后 extract-segments 使用原有1–3秒规则；完整候选越界则单独导出供人工审核。
分析阶段 reviewed 表示完成采样分析，不表示人工逐帧验收，method 保存 api_sampled_frames。
不自动推断素材授权。--allow-paid 允许图片/文稿发往配置服务并可能计费，不是费用上限。
不自动重试未知状态请求，不切换替代收费服务。

离线测试覆盖协议载荷、缓存、付费开关、窗口重叠与候选归属；真实服务和视觉判断质量未实测。
