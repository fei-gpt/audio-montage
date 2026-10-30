# audio-montage 接续说明

先阅读 AGENTS.md、CAPABILITIES.md，再按任务读对应功能文档。
这是本地 Python CLI 项目，不需要部署网站或数据库服务。

在项目根目录创建 .venv，优先 Python 3.12，安装 requirements.txt，确保 ffmpeg、
ffprobe 在当前终端 PATH 中。Windows 使用 .venv\Scripts\python.exe montage.py；
Mac/Linux 使用 ./run.sh。不要沿用其他电脑的虚拟环境或绝对素材路径。

素材理解由当前助手实际查看证据完成，程序只准备抽帧和管理记录；不要把
pending_analysis 模板或抽帧成功当作理解完成。没有视觉能力时明确报告。

ElevenLabs 读取进程环境变量，不自动加载 .env。不要在聊天或日志输出密钥。
未经明确接受本次传输与计费，不添加 --allow-paid；缓存命中无需重复收费调用。

剪映逐片导出使用项目技能 jianying-segment-export，与 export-draft 完全不同。
默认不要调用可选的剪映或 ElevenLabs。根据用户输入选择最短路径。

验证：python -m unittest discover -s . -p 'test_*.py' -v。
真实引擎、服务和媒体质量需分别验收，不把模拟通过当作实际成片质量保证。

## 内容识别优先

从完整视频识别有效镜头并提取多个片段时，使用 content-recognition 项目技能。
先读 CONTENT_STANDARD.md，明确通用、用途与用户补充标准，不能靠单一分数筛选。
模型/API 由用户后续配置，不假定 Flash 免费活动持续。
