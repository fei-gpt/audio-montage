# 配音驱动混剪：基础工作流

本工具实现配音驱动的混剪流程。素材处理和检索在本地执行，不发送视频、不调用付费 API。显式执行 download-model 时会联网下载模型。建议使用已验证的 Python 3.12，以及 FFmpeg 和 ffprobe；完整依赖见 requirements.txt。

**换电脑操作先看 [MIGRATION.md](MIGRATION.md)**：包含 macOS/Linux 与 Windows 的安装和启动方式。本地完整 UI 暂缓，目前通过命令行执行。

**固定规则：只使用 9:16 视频，输出也只允许 9:16。** 横屏、方形、近似但非精确 9:16 等素材直接排除，原因写入索引报告 excluded；不会通过裁剪、补边或拉伸接纳。判定使用实际显示比例，计算像素比例（SAR）和旋转信息。分辨率可以不同，例如 1080×1920、720×1280；内容严格按原显示比例缩放。无法明确判定的视频排除。

索引入口、旧数据库检索、候选回填、手工选片校验、渲染和剪映草稿导出均执行该约束。旧索引保留的数据也不能绕过当前规则。带正常 90° 旋转元数据且实际显示为 9:16 的素材可使用。

## 已实现和待接入

| 部分 | 状态 |
|---|---|
| 导入已有 SRT / 时间轴 JSON | 可用，检查重叠、越界和空文案 |
| 本地自动转写 | 英文 en、西班牙语 es、自动检测 auto；保留原语言，词级时间戳和术语提示；兼容 zh |
| 时间轴转待编排清单 | 可用，保留停顿，拒绝覆盖已有选片 |
| 理解文案、设计镜头 | 由 Codex 或人工填写；脚本不会猜测语义 |
| 镜头索引 | 按切镜点和时间窗口切分、三帧抽取、SHA256 缓存、重复内容复用 |
| 片段检索 | 中/英/西语多语言描述与别名，重音兼容，过滤时长和完整词项条件 |
| 候选回填 | 生成候选列表，choose 选择后回填剪辑清单并备份，保持待复核状态 |
| 区间裁切与短素材组合 | 按已标注完整动作选区间；单段优先，不够时规划多段，避免重复画面 |
| 素材剪切、缩放、拼接、配音合成 | 可用，保持原速；素材原声默认关闭，可统一勾选保留 |
| 字幕 | 输出外挂 SRT，未烧录；停顿不强行显示字幕 |
| 自动检查 | 时间轴连续、媒体有效、素材时长、输出解码和总时长 |
| 审片辅助 | 每镜头提取前、中、后三帧，生成附图审片表 |
| 剪映草稿包 | 导出视频、配音、字幕三轨，打包原素材并更新绝对路径；当前 Mac 剪映打开兼容性未验证 |
| 视觉自动标注、向量语义检索、BGM、转场、响度标准化 | 尚未接入；已有标签检索不依赖模型 |

本项目参考 xilo 的分步工作流，代码为本次独立实现，未声称复现其内部算法。

- 混剪原帖：https://x.com/xilo2991/status/2073752063591473242
- 知识视频原帖：https://x.com/xilo2991/status/2091071218963411453
- 可读取混剪正文：https://www.jxxy.net/ai/articles/xilo2991-2073752063591473242/

## 使用

当前工作区已经有独立环境时，使用 `./run.sh` 代替 `python3 montage.py`。脚本会先选择本目录 .venv，再选择本工作区 work/montage-venv；也可用 MONTAGE_PYTHON 指定 Python。

### 保留原视频声音（默认不勾选）

创建项目后打开原生设置窗口：

```sh
./run.sh settings ./my-project
```

窗口提供一个勾选项：**保留原视频声音**。默认不勾选；勾选并保存后，所选视频片段的原声与主配音一起输出，统一应用于整条预览、正式成片和剪映草稿。无需给每条素材或片段分类。未带音轨的素材保持无原声，不会用其他素材的声音替补，主配音保持连续。原声按所选区间截取，保留其起始延迟；缺失或较短的原声以静音补齐对应时间。合成混音在需要时限制峰值，防止叠加超幅。

也可以用命令切换同一个设置：

```sh
./run.sh set-audio ./my-project --keep-original-audio
./run.sh set-audio ./my-project --no-keep-original-audio
```

配置保存为 project.json 的 `keep_original_audio: false/true`。旧项目没有该字段也默认关闭。新建项目仅在明确传 `--keep-original-audio` 时开启。取消窗口不更改设置。改变选项后需要重新渲染；旧审片记录会失效，已有 MP4 和草稿仍不覆盖。

settings 使用 Python 自带的 Tkinter；当前环境已确认可导入 Tk 8.6。其他环境若缺少 Tkinter，可用上面的命令设置。实际混音和草稿音量已测试，原生窗口未做自动点击测试。

迁移到其他电脑时，在本目录建立独立环境：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
chmod +x run.sh
```

在本文件所在目录打开终端，命令中的素材路径均替换为你的真实绝对路径。项目目录可自行指定。

```sh
python3 montage.py init ./my-project --audio /绝对路径/配音.wav
python3 montage.py import-timing ./my-project /绝对路径/配音字幕.srt
python3 montage.py build-plan ./my-project
```

也可将第二条换成本地转写（需事先安装 faster-whisper 并准备兼容的本地模型）：

```sh
./run.sh download-model tiny --output /绝对路径/模型目录/tiny
./run.sh transcribe ./my-project --model /绝对路径/模型目录/tiny --language en --prompt 'storage box, cable organizer'
# 西班牙语：
./run.sh transcribe ./另一个项目 --model /绝对路径/模型目录/tiny --language es --prompt 'caja organizadora, cables'
```

自动语音识别的时间戳是估计结果，不是经过验证的强制对齐。核对 audio/timing.json 中的文字与边界，确认后把 reviewed 改为 true；不以原稿直接替换识别文本来假装完成了时间对齐。

初始化时可用 `--language en` 或 `--language es` 保存语言，transcribe 未指定时继承项目设置；均未指定时默认 auto，检测整条音频的主要语言。已知语言建议明确指定。转写固定使用 transcribe 任务，西语字幕保留西语，不翻译为英语；同一条音频频繁切换语言需额外复核。

tiny 适合验证能否运行，不保证真实录音精度；真实配音可另行下载 small 等模型再评估。transcribe 不联网、不自动下载、不覆盖已有时间轴；同时输出 out/captions.srt。模型下载与推理没有付费 API token 费用，但需要磁盘、网络和计算时间。

当前工作区测试模型位于 `../../work/models/faster-whisper-tiny/`，可直接复用。官方模型端点若超时，可显式给 download-model 增加 `--endpoint https://hf-mirror.com` 使用公开镜像。转写保留 audio/raw-transcript.json 原始识别，再根据实际词级时间戳与标点生成短语时间轴；长度阈值仅用于分组，时间始终来自音频识别。FFmpeg 将输入解码为单声道 16 kHz，避免依赖 PyAV 不同版本的文件接口差异。

英文、西语按实际词边界和标点分组，初始每组最多约 78 字符、12 词或 5 秒；常见称谓缩写和小数不作为句末。输出字幕优先两行平衡排版，每行约 40 字符，不拆单词或连字符词。中文兼容 15 字符/4 秒的旧设置。检查报告 advisories 提示超过两行或阅读速度过快的字幕，人工决定如何调整。

### 接入检查与原稿核对

```sh
./run.sh preflight ./my-project
./run.sh compare-script ./my-project --script /绝对路径/原始配音稿.txt
```

preflight 输出配音指纹、音轨信息、语言、工具依赖、输出规格和可用磁盘。compare-script 比较识别文字和已有原稿，标出漏词、替换、数字和重音差异；不改写时间戳，不把原稿机械贴到识别时间轴上。静音音频会停止转写；所有识别结果仍然需要复核。

### 编排与选择素材

打开 plans/edit.json。默认每个转写段生成一个待编排镜头，这只是占位清单；应按语义合并或细分，而不是机械按句切镜头。初始、句间、结尾停顿也必须有画面，可合并到相邻镜头。镜头 start/end 必须首尾相接，覆盖完整配音。

为每个镜头补充 purpose（观众应理解什么）、query（找什么画面）、required/forbidden（硬性条件），再填 selection：

```json
{
  "id": "S001",
  "start": 0.0,
  "end": 3.0,
  "text": "把插排放进收纳盒",
  "purpose": "展示收纳操作，而不是静态外观",
  "query": "手把插排放进白色收纳盒，近景",
  "required": ["白色款", "放入动作"],
  "forbidden": ["其他产品型号"],
  "selection": {
    "path": "/绝对路径/演示.mp4",
    "source_start": 4.2,
    "reason": "该区间包含完整的放入动作"
  },
  "reviewed": true
}
```

单段 selection 的 source_start 是原素材开始秒数，使用时长取镜头 end-start，保持 1 倍速。无需重复填写 source_end。也可通过下文 choose 命令回填 selection。多段格式见下文。

合成脚本只校验字段和时间，不验证 reason 的真实性。检索模块使用 query 和 required/forbidden 对已标注文本排序、过滤，不能证明画面实际满足条件。确认语义、关键动作完整、裁切正确后，才把镜头 reviewed 改为 true。

### 合成

```sh
python3 montage.py validate ./my-project
python3 montage.py render ./my-project
python3 montage.py review ./my-project
python3 montage.py render ./my-project --final
```

预览允许未复核警告，但不允许缺素材或无效区间；正式输出要求清除所有复核警告。已存在的 MP4 不覆盖，请自行重命名保存旧版本。输出 out/preview.mp4、out/final.mp4、out/captions.srt 和 qa/ 检查记录。

review 生成 qa/review.md 和 qa/frames/ 图片，辅助人工或 Codex 逐镜头看画面。修改选片后必须重渲再生成审片表，避免查看旧片。抽帧不能取代完整播放，也不会自动勾选审核项。正式片的审片命令增加 --final。

渲染记录保存剪辑清单和视频指纹；清单或输出视频变化后，review 会拒绝用旧片生成审片表。

完整输入指纹也包含项目配置、配音、字幕内容、实际选片区间及源视频内容；这些变化会使旧审片失效。仅修改 reviewed、画面目的等不影响像素的审核字段不触发重渲。JSON 写入使用原子替换，降低中断时清单损坏的风险。

project.json 默认 1080×1920、30fps、fit=contain。仅接受精确 9:16 源素材，保持完整画面等比例缩放；不支持 cover 裁剪。自定义宽高也必须为 9:16 且为偶数。预览最长边 640 像素。边界按统一帧网格量化，精度受帧率约束；音频保持为主时间轴。最后不足一帧的视觉尾部可能定格补足。

## 项目结构

```text
my-project/
  project.json         配音绝对路径、规格、总时长
  audio/timing.json    转写文字和真实时间戳
  plans/edit.json      画面需求、素材选择、人工复核
  out/                 MP4 与 SRT
  qa/                  校验和渲染报告
```

原素材仅只读引用。移动原素材后必须更新路径。工作目录里只创建自己的中间文件。

## 镜头索引与检索

```sh
./run.sh index-library --library /绝对路径/素材库 --database ./library/index.sqlite --window 6
```

首次扫描自动检测镜头变化，并把长镜头继续按最多 6 秒窗口划分，提取每片段前、中、后三帧。只保存时间范围，不改动原视频。再次扫描读取内容指纹，相同内容即使改名也复用已有片段。已变更的原视频不会继续使用旧标注。

输出 library/index.label-queue.json：填写各片段 labels.description、subject、action、scene、tags，看过画面后将 reviewed 设为 true，再导入：

```sh
./run.sh import-labels --database ./library/index.sqlite ./library/index.label-queue.json
./run.sh search --database ./library/index.sqlite --query '手把插排放进白色收纳盒' --min-duration 2 --required 白色
./run.sh candidates ./my-project --database ./library/index.sqlite
./run.sh choose ./my-project --database ./library/index.sqlite --shot S001 --clip 片段ID
```

标注可由人工或 Codex 查看抽帧后填写一次，具体规则见 LABELING.md。未标注或未复核的片段不进入内容检索；目录和文件名不用于内容评分。检索采用 Unicode 词项和中文二字片段重合，兼容 sofá/sofa 等重音输入，但保留 ñ 与 n 区别；忽略常见英西功能词。必须/排除条件按完整词项或短语判断，不把 red 当成 covered 的一部分。

跨语言必须先保存双语描述或同义别名：labels.descriptions.en/es 和 labels.aliases。例如配音为西语、标签只有中文时，需要先一次性补英西描述，或在画面编排时把 query 写成标签语言；脚本不会自动翻译。rank_score 是文本排序值，不是语义置信度，不等于向量检索。切分是候选区间，动作起止仍需核对。search/candidates/choose 的单段选择会过滤不足时长的候选；auto-plan 可以组合多个短片段。

选择候选后会备份原清单并将该镜头改为待审。重复索引不会覆盖已编辑的标注队列，而是生成递增编号的新队列；以 index-report.json 中的 label_queue 路径为准。片段标签写入 SQLite 后复用，不会在每次剪辑时重新消耗视觉模型 token。

候选与镜头文案、时间、检索条件和标签版本绑定；任一变化后 choose 要求重新检索。相同素材在同一批候选检索中只校验一次内容指纹；丢失的缓存抽帧会自动补建，不重复生成语义标签。索引与越界检查优先使用实际视频轨道时长，避免源文件音轨较长时误选无画面区间。

## 精确裁切、短素材组合与去重

首次标注可额外保存 `labels.usable_ranges`，记录可以使用的区间和必须保留的完整动作边界，全部使用**原视频绝对秒数**，具体格式见 LABELING.md。这项工作在建库时做一次，之后复用。choose 和自动规划都会遵守边界；例如动作从 1 秒到 3 秒，目标只有 1.5 秒时不会截断动作，而是换候选。

没有精确区间时，使用索引片段的居中位置作为待复核候选。这只是起点，不代表程序已经看懂并找到最佳画面。显式填写 `usable_ranges: []` 表示该片段不能使用。

完成画面需求 query/required/forbidden 后，可以本地生成整条方案：

```sh
./run.sh auto-plan ./my-project --database ./library/index.sqlite
# 查看 plans/proposal.json 的 edit 和 report，再应用：
./run.sh apply-plan ./my-project ./my-project/plans/proposal.json
```

生成方案不会修改 edit.json；应用前重新核对清单、标签版本、素材指纹、9:16 和可用区间，再备份并写入。新选片保持 reviewed=false。已有选片保留并预留其区间；方案文件不覆盖，需要重新生成时先备份移走。

规划优先使用一段足够长的素材，需要时再组合，默认每个分镜最多 4 段、每段至少 0.8 秒，避免为补尾部产生闪切。可用 `--max-parts` 和 `--min-part` 调整。完整动作必须保留，保持原速，不自动循环或慢放。未找到满足标签、时长、去重和数量限制的完整方案时，报告 missing_material 并留空；这是有限候选搜索，留空也可能需要调整查询或分镜。少于一帧的分镜会提示合并时间轴。

多段选择格式示例：配音分镜为 0—6 秒，可选择两条原素材各用 3 秒。

```json
"selection": {
  "parts": [
    {"path": "/绝对路径/A.mp4", "source_start": 0.5, "duration": 3.0},
    {"path": "/绝对路径/B.mp4", "source_start": 1.0, "duration": 3.0}
  ]
}
```

parts 按顺序播放，总时长必须等于该分镜 end-start。子片段不能同时使用旧的顶层 path 格式。渲染、审片抽帧及剪映草稿都按子片段展开，配音和字幕时间轴保持连续。原声依然由项目级勾选项统一决定。

自动规划避免整条视频重复使用相同内容指纹的重叠区间；手工选片的重叠超过 0.05 秒会产生警告并阻止正式输出。确实需要重复时，在对应分镜显式添加 `allow_reuse: true`。这个检查不能识别重新编码过的相似画面。可选 subject/scene/shot_size/screen_direction 标签帮助排序衔接，方向变化写入复核提示；程序没有光流或完整视觉连续性判断，仍需播放复核。

## 剪映草稿包

```sh
./run.sh export-draft ./my-project
# 如果你明确需要先导出待审版本：
./run.sh export-draft ./my-project --name 待审版本 --allow-unreviewed
```

输出 out/jianying_draft/：draft_content.json、draft_info.json、draft_meta_info.json、media/、media_manifest.json、export_report.json。视频每镜头独立可编辑，原声按“保留原视频声音”设置为关闭或保留，配音独立轨道，字幕为文本轨道；复制媒体后重写包内绝对路径，防止依赖原素材目录。移动整个包后需要重链接或重新导出。

实现使用 [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft)，未修改剪映自己的草稿列表或安装目录。该库上游明确提示跨平台和剪映版本限制；本机未检测到剪映应用，因此只能验证草稿结构、轨道时间、唯一 ID、素材路径和库内回读，不能承诺当前 Mac 版剪映打开成功。预览 MP4 始终使用 FFmpeg 独立生成。

## 检查与后续

```sh
./run.sh --help
./run.sh validate ./my-project
# 可复跑的真实媒体集成测试：
# 在仓库根目录使用本机虚拟环境执行全部测试
.venv/bin/python -m unittest discover -s . -p 'test_*.py' -v
# 连同已下载的多语言模型一起验证：
MONTAGE_TEST_MODEL="$PWD/models/tiny" .venv/bin/python -m unittest discover -s . -p 'test_*.py' -v
```

真实素材接入后优先验证配音术语、动作边界、画面裁切与检索命中率，再决定是否需要视觉自动标注或向量检索。当前不需要搭建网站或部署数据库服务。

本次完整测试包括英文、西语及中文实际模型推理、跨语言标签和重音检索、字幕分词、原稿对比、素材缓存修复、候选回填与版本拦截、MP4 编解码、草稿三轨导出及库内回读。详情见 verification.json。测试音频位于 fixtures/；它们是本地合成的语音，非用户录音。

提供真实素材的方法见 INTAKE.md。真实素材的音画匹配精度仍需接入后实测，不能由这些程序测试替代。

## 长期素材理解（框架）

新增按原视频保存的理解记录模板，包含产品身份、跨产品复用限制、语义片段、
动作区间、观察事实、用途解释、证据和分项审核状态。命令与范围见
[UNDERSTANDING.md](UNDERSTANDING.md)。已接入观察抽帧、Codex 复核结果入库和现有选片检索；视觉理解由 Codex 查看证据完成。

## 项目产品规则与统一入口

```bash
./run.sh set-product ./my-project --model MODEL-A
./run.sh workflow ./my-project
./run.sh workflow ./my-project --stage plan --database ./library/index.sqlite
./run.sh workflow ./my-project --stage apply
./run.sh workflow ./my-project --stage preview
# 实际审核后再正式输出：
./run.sh workflow ./my-project --stage final
```

项目型号由未设置型号的分镜继承。启用后，缺少产品身份的旧选片也会被渲染及
草稿校验拦截，需重新选片。分镜可显式指定另一个型号。
方案绑定项目配置，配置变化后需重新规划。
候选、方案和视频自动复制旧版本到同目录 history/，再生成新版本；
生成失败保留旧文件。理解结果导入也保存记录和旧语义片段快照。
统一入口保留方案应用和实际审核阶段，不会自动把 reviewed 改为 true。

本次改动按用户要求未运行测试或媒体验证。当前仍使用原来的两轮视频编码，
尚未改变补尾帧与时长处理；来源权限和自由文本限制仍需实际审核。

## 新增素材管理能力

联系表、选片反馈、近似素材提示与使用范围约束见
[UNDERSTANDING.md](UNDERSTANDING.md#联系表反馈相似提示与权限)。

渲染改为每段编码一次，末段补足统一帧网格，最终合配音时复制视频流；
保留原声的混音逻辑继续使用原流程。最终视频仍执行原有解码与时长检查。
本次未实际运行新路径，帧边界、编码拼接和音画同步尚未经媒体验证。

以上实现取代前文“仍使用两轮编码”的旧说明。来源与自由文本限制现在参与候选
提示和正式输出审核；具体授权事实仍需有依据的录入。

## 可选 ElevenLabs

可通过 `elevenlabs --mode tts/transcribe/align` 生成配音及时间戳、转写已有配音、
或将原稿与配音强制对齐，结果接入现有时间轴与字幕流程。
配置、费用开关、缓存和恢复方式见 [ELEVENLABS.md](ELEVENLABS.md)。
默认流程仍不调用外部服务；此适配代码尚未经真实 API 或本地执行验证。
