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


LIGHT_SWORD_OBSERVATION = '''
若当前产品是光剑或剑形指旋灯玩具，优先核对以下两项，动作、灯效和运镜排在其后：
1. 包装盒是否实际入画。盒面印刷图案不计入实物数量。
2. 同一时刻可见的实物数量及连接关系。区分单把、四把实际连接成一组、多把独立同框；
四把被同一只手握住或摆在一起，仍属于多把独立。被遮住或出画的数量、看不清的连接留为未知。
素材识别把下列对象写进 visual_details.light_sword，参考分段则写进每段的 light_sword：
{"packaging":"visible/absent/unknown","visible_count":整数或null,
 "arrangement":"single/connected_four/separate_multiple/other/unknown","evidence":"一句可见依据"}。
同时在画面事实中用中文写清包装、数量及连接关系。若这两项改变，分开记录，勿把不同时刻出现的实物相加。
'''

LIGHT_SWORD_MATCH = '''
光剑参考选片先匹配包装、同时可见数量和连接关系，再比较动作、灯效、运镜、背景。
开头若明确是四把同框，单把不算近似，优先用观众从开场即可数清四把的镜头；
四把相连和四把独立应分别说明，避免把拿在一起当成已连接。先核对参考实际可见状态。
旧素材可以依据当前选区的事实识别；证据不明不能写成精确匹配。非关键的展示段可以用用途相近的镜头，
允许调整动作顺序，理由中注明可见差异。若用户明确要求具体动作，则按该要求核对。
'''


LIGHT_SWORD_CUT = '''
若当前产品为 LED Finger Spinner Sword Toy（手持式短剑／指旋玩具），可主动设计同款主体接不同场景或角度的切镜。
这种接法适用于单把、四把连接成一组和多把独立同框。先用短剑轮廓、十字护手、中央指孔和手柄确认同款，再比较相邻选区的首尾画面。
同一展示重点可以主动选两段或多段有可见依据的素材，让不同场景或角度相互印证。
例如四把组合正面接另一场景的侧面组合，或多把独立陈列接手持同框。每段应让观众看清同一重点。
普通展示可在单把、组合和多把独立之间切换；若正在说明数量或连接关系，接续镜头应保持该事实，或让变化清楚可辨。
优先让同款实物在切点前后都清楚可辨，并以相近灯色、主体位置或大小作为衔接依据；
场景、景别、持剑方向可以变化，例如红灯正面手持接另一场景的红灯倒握近景。
灯色会变化，只有对应选区有证据时才声称切点灯色一致；单凭灯色不能认定同款。
可在普通展示段灵活排列、复用合适素材，给两边足够时间看清产品，避免为了换角度连续切碎。
若参考开头指定包装、数量或连接形态，优先保留这些可见事实。
'''
