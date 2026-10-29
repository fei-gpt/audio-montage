# 长期素材理解：基础框架

当前已接入观察抽帧、已复核语义片段入库和现有检索/规划。由 Codex 查看证据完成理解，不调用 Hypit Runtime 或独立视觉 API。
本模块借鉴 Hypit 的整体观察、细看动作、保留时间证据的方法；不声明已理解任何视频。

## 创建记录

先使用原有 index-library 建立合格的 9:16 素材索引，再执行：

```bash
./run.sh prepare-understanding --database ./library/index.sqlite --output ./library/understanding
./run.sh understanding-status --output ./library/understanding
```

每个原视频按完整 SHA256 保存一份 assets/<hash>.json。重复执行保留已有记录，
不会重置审核状态。当前模板中的 paths 是创建时的位置快照，不自动追踪搬移。
输出放在 library/ 下时不会提交入 Git。

## 数据约定

- asset 保存原视频身份、产品信息、来源权限和整体理解。
- segments 保存语义片段；segment_template 只是填写参考，不是有效片段。
- 片段 start/end、usable_ranges 和 evidence 中的时间都使用原视频绝对秒数。
- 语义片段允许跨越固定索引窗口，仍必须位于原视频有效时长内。
- facts 只写可见事实；interpretation 单独记录用途和不能证明的内容。
- evidence 建议使用 {"time": 4.2, "path": "证据图片路径", "note": "可见事实"}。
- usable_ranges 沿用 LABELING.md 的完整动作约定。
- product.reuse_scope 为 unknown、product_specific 或 generic_context。
  未确认身份不等于通用素材；跨产品使用仍需核对。
- review 各字段只有实际查看相应证据后才能设为 true。
- status 初始为 pending_analysis；后续可由操作者使用 needs_review、reviewed。
  status 仅为进度记录，目前程序不检查其与 review 字段是否一致。

## 完整接入流程

```bash
./run.sh observe-media ./library/understanding/assets/<hash>.json --every 2
# Codex 查看输出清单中的图片；对动作进一步加密观察：
./run.sh observe-media ./library/understanding/assets/<hash>.json --start 4 --end 9 --every 0.2
# Codex 填写 segments、证据、产品身份和实际审核结果后：
./run.sh import-understanding ./library/understanding/assets/<hash>.json --database ./library/index.sqlite
./run.sh search --database ./library/index.sqlite --query '放入线缆' --product-model MODEL-A
```

导入允许语义片段跨固定窗口，使用原视频时间；写入现有 clips 表，自动供
search/candidates/auto-plan 使用，后续 choose/apply-plan/render 沿用原校验。
重复导入替换此原视频的语义片段，不修改传统窗口片段。

分镜可添加 product_model；candidates 和 auto-plan 会按型号过滤，接受确认的
同型号和 generic_context，排除未知身份及旧标签中没有产品身份的片段。
未填写 product_model 时保留原检索行为，不提供跨产品隔离保证。
restrictions 和 rights 目前供 Codex 审核，不是自动授权判定器。

新增或改变语义片段后，旧候选需重新生成。历史理解版本与可视化联系表尚未实现。
原素材保持只读，不上传媒体、不下载模型、不产生付费调用。

## 联系表、反馈、相似提示与权限

```bash
./run.sh contact-sheet --database ./library/index.sqlite --output ./library/contact
./run.sh similar-media --database ./library/index.sqlite
./run.sh selection-feedback --database ./library/index.sqlite --project ./my-project --clip CLIP-ID --decision rejected --reason '该项目产品型号不适合'
```

contact/contact.html 是本地只读、可搜索联系表，展示区间与缓存图片，不运行服务器。
相似提示使用原视频 10%、50%、90% 三处画面的 64 位差异哈希，仅提示全部采样
接近的文件；重新剪辑、错位、局部重复可能漏检。计算量随素材数量平方增长，
不适合直接对超大库全量执行。不会自动合并产品身份、权限或审核结果。

反馈记录项目、原因和标签版本。选中次数仅参与词项分数相同的排序；淘汰不作
全库惩罚，也不会自动证明语义正确。标签改变后旧反馈不再参与排序。

rights.usage 使用 unknown/allowed/prohibited；allowed 必须来自用户或可信授权信息，
不能由画面推断。禁止使用阻止输出；未知状态给出复核警告，阻止正式输出。
产品 restrictions 为自由文本；有内容时，需要明确 restrictions_reviewed=true，
并以 approved_models 列出核对后允许的型号。程序不把自由文本自动解释成授权。
候选返回 policy_warnings，选片保存产品与权限快照，输出再次检查。
已有选片的权限快照不会自动同步数据库，修改权限后必须重新选片；当前不提供
跨项目自动撤回能力。
