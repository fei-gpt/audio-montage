本地界面入口： [多产品、多账号工作台](WORKBENCH.md)。当前支持真实后台任务、资料及账号隔离；真实视觉服务仍需用户配置。

# 能做什么、如何使用

本项目是由助手操作的本地视频工具集。可以交给 WorkBuddy 接续，不需要网站部署。
助手负责看图理解、文案与画面的对应判断；Python 负责索引、记录、约束和媒体处理。

## 按目标选择入口

| 你的目标 | 入口 | 输入与输出 | 当前边界 |
| --- | --- | --- | --- |
| 配音驱动混剪 | init → import-timing/transcribe → build-plan → workflow | 配音、9:16 素材 → MP4、外挂 SRT | 分镜语义和动作需助手实际复核 |
| 生成配音 | elevenlabs --mode tts | 文稿、声音 ID → 音频、时间轴、字幕 | 需要 Key、额度与显式付费开关 |
| 已有配音取时间 | elevenlabs --mode transcribe/align | 音频；align 另需原稿 → 时间轴 | 外部 API 未真实验证；本地 transcribe 可替代 |
| 建长期素材库 | index-library → prepare-understanding → observe-media → import-understanding | 素材 → 带证据的语义片段 | 无独立视觉模型调用；助手要看图片并填写记录 |
| 检索及自动选片 | search/candidates/choose 或 auto-plan/apply-plan | 已复核标签、画面需求 → 选片方案 | 词项检索，不是向量语义检索；缺素材留空 |
| 从整片选材 | recognize-content → extract-segments（可选 analyze-content-api） | 完整视频、剪辑要求 → 多个独立 MP4（默认1–4秒，核实的一镜到底完整展示可例外） | 视觉判断需助手或视觉 API；越界与未确认候选交人工 |
| Hypit 参考分析 | hypit-analyze | 参考视频 → Hypit probe、机械边界候选、带时间码抽帧和时间网格 | 需要已安装 Hypit CLI；机械边界不是语义切镜结论 |
| 看素材、记录反馈 | contact-sheet / selection-feedback / similar-media | 索引 → 联系表、反馈、相似提示 | 相似检测只做三帧提示，不自动合并 |
| 剪映时间线各段导出 | export-timeline-segments | 已有剪映草稿 → 每段独立 MP4 | Windows + 匹配 jy-draftc/剪映；真实引擎未验证 |
| 交给剪映继续编辑 | export-draft | 本项目选片 → 可编辑草稿包 | 可选；不是“逐片段导出”，Mac 打开兼容性未验证 |

## 助手可以承担的工作

读取素材路径和已有产品资料，检查环境，建立索引，查看证据，提出并保存画面理解；
根据配音设计分镜、选片、暴露缺素材；执行预览、按反馈修改、输出视频；
读取剪映草稿并批量调用逐片段导出；排查失败、维护版本、交付日志。
这些工作需要所在助手有本地文件、终端和图片观察能力。命令本身不提供自主视觉理解。

用户提供素材位置、产品准确身份及已知使用范围。权限未知不能由助手看画面猜测。
当前产品/权限在选片中保存快照，更新素材库限制后必须重新选片，尚无跨项目撤回。

## WorkBuddy 开始方式

1. 下载完整仓库，在 WorkBuddy 中打开或授权该本地目录。
2. 按 MIGRATION.md 安装环境，读取 .codebuddy/CODEBUDDY.md。
3. 提供实际素材/配音/草稿路径。不要只把 GitHub 链接当作已安装环境。
4. 可以直接说：“读取项目说明，检查依赖，用这条配音和这些素材做混剪”；
   或“使用 jianying-segment-export，把这个草稿指定视频轨道每段分别导出”。
5. ElevenLabs 配置参考 ELEVENLABS.md，逐段导出参考 JIANYING_SEGMENTS.md。

## 验证状态

离线回归：已验证合成媒体混剪、原声混音、理解入库与检索、联系表、反馈及
相似检测入口；ElevenLabs 验证模拟响应转换、缓存和费用拦截；
逐片导出验证拆分不修改源数据和多轨选择约束。
未验收真实 ElevenLabs 调用、真实产品语义准确性、剪映解密与引擎输出、
WorkBuddy 实际运行、本地 Whisper 模型推理。

不包含 BGM/转场自动设计、独立向量数据库、无人审核的全自动视频理解、
跨电脑路径自动迁移。Hypit 是参考方法，未依赖其 Runtime。

## 文档导航

- README.md：基础流程与完整命令示例。
- UNDERSTANDING.md：长期素材理解、产品范围、权限、反馈。
- ELEVENLABS.md：外部语音服务配置、缓存及恢复。
- JIANYING_SEGMENTS.md：独立逐片段导出插件。
- MIGRATION.md：安装迁移；AGENTS.md：执行约束。

## 核心新增：整片识别与多片段提取

recognize-content 创建自然语言任务和概览证据；视觉助手按 CONTENT_STANDARD.md
理解整片、核实多个候选区间；extract-segments 输出独立 MP4、CSV、JSON 与进度。
无需用户预先指定裁切时间，不依赖配音或剪映。当前视觉判断由助手完成；
也可选用 analyze-content-api 走 OpenAI 兼容图片接口（需 --allow-paid）。
content-v2 分开记录通用、用途与用户标准，标 keep 前逐项检查硬条件与证据状态，
未知结果进待审而不是等到导出才整批失败。

时长越界候选单独进入 manual-review-clips 与 manual-review.json；内容或条件未确认的候选
进入 uncertain-review.json。人工核对后用 review-segments 回填结论、用 reselect-segments
重新选区，两条命令都保留历史（history/ 与 review-log.json）并自动重新导出。
视觉 API 的密集复核可在已观察窗口内修正边界，原区间写入 original_start/boundary_history。

本次离线回归 44 项：40 项通过、4 项跳过（3 项需本地 ASR 模型，1 项需 pyJianYingDraft）。
新增覆盖：模拟兼容 API 的完整链路（解析要求→批次候选→密集复核→边界修正与越界拒绝→
分割导出→人工回填→重新选区）、硬条件未确认时的 keep 拦截、时长越界转待审、
模拟中断续跑与旧输出归档。HTTP 边界用假服务替代，真实服务、真实镜头语义与
剪映原生引擎仍未验收。
