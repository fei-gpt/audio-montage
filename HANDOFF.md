# 新电脑安装与交接

GitHub包含程序，不包含账号登录、素材、审核、任务数据库和本机运行时。

## 独立给别人使用

1. 下载或克隆仓库，安装Python 3.10+，在仓库运行 `python -m pip install --target .workbench-deps -r requirements-workbench.txt`。
2. 准备FFmpeg/ffprobe；已有工具可通过 `powershell -ExecutionPolicy Bypass -File scripts/install-media.ps1 -SourceDirectory "工具bin目录"` 接入。
3. 安装Codex CLI并用使用者自己的ChatGPT账号登录。在识别服务设置保存Codex / gpt-6-luna。安装CLI不代表该账号已有此模型权限，实际权限需单独验证。
4. 需要配音断句时运行 `powershell -ExecutionPolicy Bypass -File scripts/install-asr.ps1`。整条配音时长的MP4＋MP3配对路径无需ASR。Hypit、即梦和ElevenLabs仅在使用对应功能时另外配置。
5. 双击 `check-workbench.cmd`，解决缺项后双击 `start-workbench.cmd`，打开 http://127.0.0.1:8768 。不要让两个服务使用同一数据目录。
6. 新建产品、账号，接入使用者自己的素材。仅接受实际9:16输入。

自检只检查本地可用条件；不会调用模型、下载依赖或验证外部服务。可运行 `python -m workbench.preflight --json` 获取结构化报告，或 `--data "数据目录"` 检查另一个数据副本。核心Python/FFmpeg/ffprobe缺失返回非零；可选功能缺项单独列出。

## 迁移自己的旧数据

先请求暂停，并等当前请求完成；核实所有素材、剪辑及生成任务空闲后，关闭旧工作台再复制。不要在活动推理中强行停止。保留旧电脑备份。

- 复制完整 `.workbench-data`，以及源素材、原视频旁的 `.analysis.json` 和需要保留的输出。仅复制GitHub仓库不会带走业务数据。
- 尽量保持原素材盘符和目录，以及仓库的绝对位置；任务、证据、上传和输出记录含绝对路径。换盘符后不可直接假定旧断点可继续。
- `.workbench-data` 可能包含 `credentials.json`、`generation-config.json` 等凭据。自己的迁移副本应私密保存；给其他使用者交付程序时不附带该目录、`.env.workbench`、Codex登录目录或任何密钥。需要共享素材/产品资料时单独交付必要文件，不共享整套账号数据。
- 新电脑重新安装依赖及运行时，不直接复用旧电脑的Python虚拟环境；重新登录Codex，保存识别设置以更新CLI路径。
- 运行自检核对素材路径。当前没有全业务路径自动重绑向导；若绝对位置改变，先在副本中核对迁移方案，不能直接重启旧任务或重新识别整库来代替迁移。
- 保留已有完整分析、原始缓存和不明请求隔离记录；切换电脑不代表允许重发历史不明请求。

## 实机验收

在新电脑用自己的小批次验证：两组同名MP4＋MP3 → 检查配对 → 时长匹配 → 预览 → 核对 → 输出1080×1920/30fps；确认源文件未改变。再按需要验证本地断句及语义匹配。真实外部生成和配音服务必须另行明确授权调用，离线测试不代表付费端到端验收。
