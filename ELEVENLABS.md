# ElevenLabs 接入

已编写 TTS + 字符时间戳、Scribe 转写、Forced Alignment 三条 HTTP 路径，
直接转成现有 audio/timing.json 和 out/captions.srt。未进行联网调用或执行验证。
需要现有 FFmpeg/ffprobe，无新增 Python 包。

## 配置

在运行程序的终端设置 ELEVENLABS_API_KEY。不要将真实值写进 Git、命令示例或聊天。
可选环境变量 ELEVENLABS_VOICE_ID、ELEVENLABS_TTS_MODEL、ELEVENLABS_STT_MODEL。
本程序读取进程环境变量，不自动加载 .env；仅创建 .env 文件不会生效。
默认模型为 eleven_multilingual_v2 与 scribe_v2，账户需要具备相应 API 权限和额度。

## 使用

```bash
# 新项目：文字生成配音，同时取时间戳
./run.sh elevenlabs ./new-project --mode tts --script ./script.txt --voice VOICE_ID --language es --allow-paid
# 已 init 的项目：已有音频但没有文稿
./run.sh elevenlabs ./my-project --mode transcribe --language es --allow-paid
# 已 init 的项目：音频和准确文稿已有
./run.sh elevenlabs ./my-project --mode align --script ./script.txt --language es --allow-paid
# 接续原有流程
./run.sh build-plan ./new-project
```

--allow-paid 明确允许此次请求传输文稿/音频到 ElevenLabs 并按账户计费，
不是费用上限。未提供时仅允许复用已有缓存，不会新发请求。
本项目不自动查询余额或估算价格，不自动挑选声音，也不克隆声音。
已有时间轴拒绝覆盖，换配音使用新项目。

缓存按端点、参数及输入音频指纹命名，位于项目 audio/elevenlabs-cache/。
原始响应可能包含文稿、音频和时间戳，不应公开提交。
超时、错误响应或中断后无自动重试；若已有尝试记录但无结果，先核查服务端
是否计费，再手动归档对应 request.json。请求和生成结果不会因重新渲染而重发。
TTS 采用默认 MP3 输出。字符时间戳聚合为词/短语，不按字数估算时间。
对齐与转写结果始终 reviewed=false，必须实际核对后继续正式输出。

官方接口：
- https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps
- https://elevenlabs.io/docs/api-reference/speech-to-text/convert
- https://elevenlabs.io/docs/api-reference/forced-alignment/create
