---
name: jianying-segment-export
description: 从用户已有剪映草稿按视频轨道逐片段导出独立视频，使用匹配版本的 jy-draftc 调用本机剪映引擎。用于批量导出所选片段，不用于创建混剪草稿或导出整条视频。
---

# 时间线片段导出

在仓库根目录工作，先读 JIANYING_SEGMENTS.md，使用 jianying_segments.py 模块，
通过 montage.py export-timeline-segments 调用。该技能依赖完整仓库，不能仅复制此目录运行。

确认用户草稿目录、独立输出目录和目标视频轨道。多轨不猜测，读取明文草稿
列出视频轨道 ID；加密内容需在适配的 Windows 环境解密后检查。

检查 Windows x64、jy-draftc 路径及剪映 videoeditor.dll 所在目录。
工具版本必须匹配安装的剪映版本；历史 11.6.0.14552 对应
11.6.0.14552-26101320，实际以工具校验为准。
本仓库不包含 jy-draftc 二进制及剪映安装包。

先为明文样本准备拆分草稿，不传 --export；实际导出时添加 --export：

```powershell
.\.venv\Scripts\python.exe montage.py export-timeline-segments --draft "D:\Drafts\demo" --output "D:\Exports\demo" --track TRACK_ID --tool "D:\Tools\jy-draftc.exe" --jy-dir "D:\Jianying\11.6.0.14552" --export
```

仅保留目标视频片段及自带声音，不带其他轨道字幕、配音和叠层。
遇到复合片段、转场、跨轨或时间线级关键帧，先用一个片段实测，不能保证
与剪映 GUI 的“导出所选片段”完全相同。
保留原草稿；不要对未知视频加覆盖参数。根据 segments-export.json 和日志恢复，
输出时长/比例检查失败时停止并报告，不把文件存在当作导出成功。
交付独立视频、对应原片段 ID/时间及失败清单。
