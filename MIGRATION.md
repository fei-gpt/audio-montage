# 在另一台电脑运行

本地完整 UI 暂缓。目前通过命令运行，输出 MP4、SRT 和可选剪映草稿；无需操作剪映即可渲染视频。

## 下载和安装

克隆此仓库后进入仓库根目录。使用 Python 3.12（当前已验证版本为 3.12.7），并安装 FFmpeg，确保以下两个命令在终端可用：

```sh
ffmpeg -version
ffprobe -version
```

macOS / Linux：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
chmod +x run.sh
./run.sh --help
```

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe montage.py --help
```

后面的命令以 macOS / Linux 为例。Windows 将 `./run.sh` 替换为 `.\.venv\Scripts\python.exe montage.py`。requirements.txt 用于新环境安装；requirements-lock.txt 是原 Mac 测试环境快照，不保证适用于其他系统。Tkinter 仅用于已有的声音勾选窗口，命令行设置不依赖它。

## 新建项目

```sh
./run.sh init ./projects/demo --audio /本机绝对路径/voice.wav --language en
./run.sh preflight ./projects/demo
```

西语使用 `--language es`。导入已有时间轴，或显式下载模型再本地转写，二选一：

```sh
./run.sh import-timing ./projects/demo /本机绝对路径/voice.srt
```

```sh
./run.sh download-model tiny --output ./models/tiny
./run.sh transcribe ./projects/demo --model ./models/tiny --language en
```

下载模型需要网络；tiny 用于验证流程，真实配音精度需要另行评估。核对 audio/timing.json 的文字和边界之后才设 reviewed=true。

```sh
./run.sh build-plan ./projects/demo
./run.sh index-library --library /本机绝对路径/素材库 --database ./library/index.sqlite
```

查看 label_queue，按 LABELING.md 标注，再导入。补充 plans/edit.json 中的画面需求后：

```sh
./run.sh import-labels --database ./library/index.sqlite ./library/index.label-queue.json
./run.sh auto-plan ./projects/demo --database ./library/index.sqlite
./run.sh apply-plan ./projects/demo ./projects/demo/plans/proposal.json
./run.sh render ./projects/demo
./run.sh review ./projects/demo
```

核对画面、文案和裁切后，再将分镜 reviewed=true，正式输出：

```sh
./run.sh render ./projects/demo --final
./run.sh export-draft ./projects/demo
```

已有输出不覆盖。完整参数、方案结构和复核要求见 README.md。

## 声音和素材限制

只接纳实际显示比例严格为 9:16 的视频；其他比例直接排除。原视频声音默认关闭，可在命令行统一开启：

```sh
./run.sh set-audio ./projects/demo --keep-original-audio
# 关闭：
./run.sh set-audio ./projects/demo --no-keep-original-audio
```

## 仓库包含什么

包含程序、测试、合成测试音频、标注规范和验证记录。不包含 Python 虚拟环境、转写模型、用户配音、素材库、SQLite 索引或生成的视频。

换电脑后应在新电脑重新建立项目和索引。已有 edit.json、索引、草稿中的素材路径是绝对路径，直接复制不能自动迁移；需要更新路径并重新核对素材，旧草稿可重新导出。第一次镜头标注可以保留为 JSON，但导入时仍需匹配相同片段 ID 和时间范围。

本机完成过 Mac 集成测试；Windows/Linux 与实际剪映打开草稿尚未实测。

## 验证安装

macOS / Linux：

```sh
.venv/bin/python -m unittest discover -s . -p 'test_*.py' -v
# 包含本地转写实测：
MONTAGE_TEST_MODEL="$PWD/models/tiny" .venv/bin/python -m unittest discover -s . -p 'test_*.py' -v
```

不提供 MONTAGE_TEST_MODEL 时，需要实际模型的测试会跳过，不代表已经验证转写。fixtures/ 中均为合成音频，不是用户素材。
