"""Small, evidence-first vocabulary for ordinary product display footage."""
DISPLAY_PROMPT = '''
普通产品展示标准（只观察当前区间，不推测拍摄者心理）：
在visual_details中增加product_display对象：
{"light_state":"on/off/mixed/not_applicable/unknown",
 "light_change":"none/turn_on/turn_off/color_change/multiple/unknown",
 "product_motion":"fixed/rotate/change_angle/enter/exit/multiple/unknown",
 "camera_motion":"fixed/push/pull/pan/track/multiple/unknown",
 "framing":"whole/detail/partial/mixed/unknown",
 "uses":["appearance","lighting","activation","deactivation","detail","intro","outro"],
 "limitations":[],"evidence":"一句当前区间可见依据"}。
枚举使用英文值；uses只选有证据支持的用途，不能判断则空数组。
常亮不是亮起，常灭不是熄灭；曝光变化不能直接当开关灯。产品旋转与运镜分开，进出画与切镜分开。
进入画面后需留出清楚展示的区间；离开画面可作收尾，不天然判无效。
产品不动但镜头推拉摇移仍有展示价值；普通展示不必强求功能演示或完整操作。
没有看到具体开关动作，不声称触摸/按压/遥控等开启方式。采样不足以确认变化时标unknown。
同一镜头的局部细节不能直接代替整机全貌，主体模糊或遮挡作为使用限制。
不要把整片中的状态变化继承给没有发生变化的局部片段。
'''

MATCH_PROMPT = '''
产品镜头匹配：普通介绍或非可视化宣传允许使用同产品的通用外观/灯效展示，理由写“通用展示”，不捏造动作对应。
文案明确讲亮起、熄灭、进出画、操作或细节时，必须核对对应可见事实；常亮不能替代亮起过程。
先核对产品身份、动作方向、灯光变化和用途，再考虑景别、构图与时长；镜头相似不等于可替换。
无product_display的旧记录不是无效素材，可依据facts，证据不足报告缺口，不猜标签、不自动重跑全库。
入库观察事实长期复用，本次配音决定用途；进入适合引入、离开适合收尾，但要按实际文案和前后镜头判断。
'''
