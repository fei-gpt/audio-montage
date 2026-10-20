# 镜头标注规则

这是首次建库时可由 Codex 或人工执行的标注规范，不是自动调用视觉模型的程序。

1. 读取索引报告中的 label_queue，按片段查看 frames 的三张本地图片。目录名 hint_only 只作线索，不当作已验证事实。
2. 在 labels.description 中写具体可见主体、场景和动作；subject/action/scene 填短描述，tags 保存产品型号、颜色、景别等可见特征。
3. 只有首尾图片不足以确认完整动作时，进一步查看原片段或补抽帧。不把“手在盒子旁边”臆测为“手已经把插排放进去”。
4. 看不清的型号、材质、功能或不在画面中的结果不要填写。颜色相似不能证明是同款产品。
5. 标注内容与抽帧一致，才将 reviewed 设为 true；不确定的保留 false。labels.source 写 manual 或 codex-reviewed，便于追溯。
6. 只修改 labels 和 reviewed，不修改 id/start/end/frames。需要更准确动作区间时，在 labels.usable_ranges 中记录；不修改索引切分边界。固定窗口索引不会自动学习动作起止。
7. 保存独立的标注 JSON，再执行 import-labels。标签入库之后复用；后续剪辑只查看候选，不重新分析全部素材。

## 英文、西班牙语配音

首次看图标注时，一起保存对应的英文和西语描述，复用同一组抽帧，不要为每种语言重复分析全库。

```json
{
  "description": "双手把线缆放进白色收纳盒",
  "descriptions": {
    "en": "Hands put cables inside a white storage box",
    "es": "Las manos colocan cables dentro de una caja blanca"
  },
  "aliases": ["cable organizer", "organizador de cables"],
  "subject": "white storage box / caja blanca",
  "action": "put cables inside / colocar cables dentro",
  "tags": ["white", "blanca", "close-up", "primer plano"],
  "source": "codex-reviewed"
}
```

双语描述必须表达相同的可见事实。产品型号和品牌保留准确原名，不自行翻译型号。query、required、forbidden 使用其中已有的词或短语；脚本只做本地词项检索，不会把任意西语自动翻译成中文。

## 可用区间和完整动作

以下 labels 字段可与双语描述一起入库，所有时间为原视频绝对秒数，必须位于该索引片段 start/end 内：

```json
{
  "scene": "tabletop",
  "shot_size": "close-up",
  "screen_direction": "left-to-right",
  "usable_ranges": [
    {
      "start": 0.3, "end": 4.5,
      "kind": "action",
      "action_start": 1.0, "action_end": 3.0,
      "priority": 1.0,
      "reason": "1—3 秒包含从开始放入到完成的动作"
    }
  ]
}
```

start/end 是可裁切范围，action_start/action_end 是必须完整保留的动作。action 未单独给动作边界时，整个可用区间都会受到保护；静态展示使用 kind=static，不填写动作边界。priority 在 0—1 之间，只影响排序。多个区间可分别标记；看不清或不能使用的片段标为空列表。缺少 usable_ranges 时仅给居中待审候选。

完整动作边界需要播放核实，仅靠三张抽帧往往无法确定。主体、场景、景别和运动方向使用一致词汇，缺少证据就留空。这些标签只辅助衔接排序，不能代替整条视频审片。首次建库可先精标一小批命中素材，再按需要补充；无需每次重新分析全库。
