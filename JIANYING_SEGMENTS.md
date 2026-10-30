# 按剪映时间线片段分别导出

与 export-draft（创建剪映草稿包）无关。本命令读取已有剪映草稿，
将指定视频轨道的各个片段隔离为独立草稿，通过 jy-draftc -ex 调用剪映引擎。
只保留目标视频片段及片段自带原声/关联素材，不包含其他轨道的配音、字幕或叠层。
这是单素材隔离导出，不是将整条合成视频按切点分割。

## Windows 配置与执行

安装与剪映运行时严格匹配的 jy-draftc。用户提供的历史版本为
剪映 11.6.0.14552，对应上游工具 11.6.0.14552-26101320。
不自动下载或安装剪映，也不修改原草稿或剪映安装目录。

```powershell
.\.venv\Scripts\python.exe montage.py export-timeline-segments --draft "D:\Drafts\demo" --output "D:\Exports\demo" --tool "D:\Tools\jy-draftc.exe" --jy-dir "D:\Jianying\11.6.0.14552" --export
```

多视频轨道必须添加 --track 原草稿轨道ID。不加 --export 时，仅为明文草稿
准备独立草稿，可在 Mac 上检查拆分结果；加密草稿需要匹配的 Windows 引擎解密。
也可通过 JY_DRAFTC、JY_INSTALL_DIR 配置路径。工具自身校验 DLL/ABI，版本不符即停止。

输出 0001.mp4 等独立视频、drafts/ 副本、segments-export.json 与逐片日志。
成功片段按指纹断点续跑；未知或改动的视频拒绝覆盖。原视频在原处保持可读。
草稿使用绝对媒体路径时应在原 Windows 电脑执行；相对路径、云素材、复合片段、
跨轨依赖、转场和时间线级关键帧尚需真实样本核对。片段结构原样保留，但不保证
所有高级效果在独立草稿中与剪映“导出所选片段”完全一致。

当前 Mac 没有发现剪映和 jy-draftc，仅验证拆分逻辑，未验证真实解密或引擎导出。
此前成功导出 123 段为用户提供的历史信息，本机未找到其脚本或记录，不能当作本实现的验收结果。

上游文档：https://github.com/wenshui330/jy-draftc
