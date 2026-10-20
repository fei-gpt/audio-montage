# 中文转写测试音频

chinese.wav 是使用 macOS 本地 Tingting 声音合成的测试音频，非用户录音。

原始文案：

> 把插排放进收纳盒。整理好电线，然后盖上盖子。现在，桌面变得整洁了。

测试模型：Systran/faster-whisper-tiny，CPU int8。该样例能验证转写、词级时间戳和短语分组确实运行，不能证明真实录音的精度。

本次识别中“整洁”被识别为“整结”，标点也有差别；程序保留原始识别结果，reviewed=false，要求人工核对。没有偷偷用原稿替换识别结果。

## 英文和西班牙语

english.wav：macOS Samantha 本地合成。

> Open the storage box. Put the cables inside, then close the lid. Your desk is clean and tidy.

spanish.wav：macOS Mónica 本地合成。

> Abre la caja. Coloca los cables dentro y cierra la tapa. Ahora la mesa está limpia y ordenada.

两者均使用已下载的多语言 tiny 模型实测，分别指定 en/es。检测关键词、原语言保留、词级时间戳与短语分组；程序不将西语翻译成英文。合成音频较干净，这不代表口音、噪声、背景音乐或真实素材的识别效果。
