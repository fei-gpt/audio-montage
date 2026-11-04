# AI生成与实拍续接

进入“视频剪辑制作”，选择产品与账号。页面保留“上传已有文件”与“AI视频生成”两条入口，共用当前账号素材库和同一套合成模块。

## 顺序

1. 新建AI任务，填写目标、文案规则和语言，选择 DeepSeek API 或本机 Codex CLI。先保存，不自动调用。
2. 允许文案调用与即梦额度后，生成两层文字：AI开头口播及即梦画面提示词、实拍续接配音稿及画面要求。产品事实来自共用知识，不重新读取原始资料。
3. 调用官方 Dreamina CLI，严格9:16、自带口播音轨。保存 submit_id，后台低频查询同一任务并下载正式结果；查询失败不重新提交。不明提交记录阻止重复计费。
4. 视频返回工作台后，用户实际播放并确认当前视频指纹。未确认之前不会调用 ElevenLabs。
5. 确认后，ElevenLabs 将**已经保存的实拍续接配音稿**转为语音，而不是再次生成文案。使用带时间戳的接口，保存音频、字符对齐和真实字幕时间轴，后续无需重新转写。
6. 自动创建账号内剪辑任务，引用AI开头、续接配音及已确认素材库。按内容选片并生成预览；选择直接输出模式时生成完整成片并标注未人工审片。AI开头确认不可跳过。

## 配置

“生成服务设置”可直接填写 ElevenLabs 密钥，保存后获取声音列表并选择声音。密钥仅写入本机 credentials.json，不回显、不进Git。

DeepSeek复用工作台识别服务配置；Codex使用本机CLI已有登录，执行只读沙箱、结构化输出，结果缓存后不重复调用。没有自动切换文案服务。

即梦使用官方Windows二进制，放在仓库 `.dreamina-runtime/dreamina.exe`，可运行 `powershell -ExecutionPolicy Bypass -File scripts/install-dreamina.ps1` 安装或修复。安装来源为[即梦官方CLI入口](https://jimeng.jianying.com/ai-tool/install)中的官方分发地址。安装器只验证帮助，不生成。

首次使用须在本机完成 `dreamina login`。浏览器已登录不能等同CLI登录；需要同意模型协议时由用户在即梦官方网页完成，不自动代为同意。默认不指定模型以沿用CLI默认值，默认720p、5秒；提交前读取当前子命令帮助。最终合成仍为1080×1920。

## 接口与恢复

- `/api/generation/settings`：GET状态、POST本机配置，密钥仅写入、不返回。
- `/api/generation/voices`：GET声音元数据，不生成语音。
- 账号路由下 `generation` POST创建；`generation/<id>` GET；后缀 `start`、`poll`、`approve-intro`、`resume` 使用POST。
- `approve-intro` 必须包含当前 `intro_sha256`、`content_confirmed:true` 和 `allow_paid:true`。确认授权覆盖续接配音及后续选片API。
- 保存分阶段产物、费用尝试记录和外部任务ID。CLI只查询已接受的任务，未得到完整响应时不自动重提。任务ID、结果下载和音频缓存均按账号隔离。
- 生成后的素材通过上传记录接入剪辑，ElevenLabs时间轴通过音频指纹接入剪辑缓存，不再识别同一配音。

## 实际验证边界

`python -m unittest test_generation -v` 模拟文案、CLI和ElevenLabs响应，并使用本地合成媒体验证确认关口、恢复、防重提、账号隔离和自动交接至剪辑预览。官方CLI已安装并读取帮助；未执行真实登录、生成或付费验收。

接口依据：[ElevenLabs带时间戳配音](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps)、[Codex非交互结构化输出](https://learn.chatgpt.com/docs/non-interactive-mode)。
