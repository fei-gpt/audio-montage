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
无需用户预先指定裁切时间，不依赖配音或剪映。当前视觉判断由助手完成，尚未接视觉 API。
content-v2 分开记录通用、用途与用户标准，提取前检查硬条件和证据状态。

本次回归 26 项：22 项通过、4 项因模型/依赖缺失跳过。
新增实测覆盖合成视频画面区间正确性、时长、原声/静音、模拟中断续跑及硬条件拦截。
这不代表真实镜头语义或剪映原生引擎已通过验收。
