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

LIGHT_SWORD_CATEGORIES = (
    '单把光剑旋转', '四把合体光剑旋转', '从旋转到停下', '从静止到开始旋转',
    '展示不同灯效', '拆分光剑', '安装光剑', '多人合作旋转',
    '点亮光剑', '关闭灯光', '拿起光剑', '产品揭示', '静态外观展示',
)


def uses_light_sword_categories(product):
    identity=' '.join(str(x or '') for x in (product.get('name'),product.get('knowledge_product_name'),
                       (product.get('profile') or {}).get('suggested_name'))).lower()
    return any(term in identity for term in ('lightplay','光剑','finger spinner sword'))


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
统一展示逻辑“产品揭示”：短铺垫 → 产品从不可见或未清楚展示变为清楚可辨 → 亮相。手从画外拿入、移开手或布、移开前景露出后方陈列、先见包装再展示实物，都归同类；包装有无仍独立记录。换颜色、持续旋转或产品一直清楚可见，不构成揭示。
在 light_sword.reveal 中记录 {"status":"present/absent/unknown","method":"enter_frame/uncover/foreground_moves/packaging_first/other/unknown","evidence":"简述变化前、变化动作、变化后","start":原片铺垫秒数或null,"end":原片亮相清楚后的结束秒数或null}。同时在 facts 中标明“产品揭示”。手法只描述实际看见的动作；有包装不能推断开箱。时间只用证据支持的区间，采样不足填 unknown 或 null。候选裁切保留短铺垫、显现和清楚亮相。
同时在画面事实中用中文写清包装、数量及连接关系。若这两项改变，分开记录，勿把不同时刻出现的实物相加。
'''

LIGHT_SWORD_MATCH = '''
光剑参考选片先匹配包装、同时可见数量和连接关系，再比较动作、灯效、运镜、背景。
开头若明确是四把同框，单把不算近似，优先用观众从开场即可数清四把的镜头；
四把相连和四把独立应分别说明，避免把拿在一起当成已连接。先核对参考实际可见状态。
旧素材可以依据当前选区的事实识别；证据不明不能写成精确匹配。非关键的展示段可以用用途相近的镜头，
允许调整动作顺序，理由中注明可见差异。若用户明确要求具体动作，则按该要求核对。
'''


LIGHT_SWORD_ROTATIONS = {
    'single': {'单把光剑旋转', '单个光剑旋转'},
    'four': {'四把合体光剑旋转', '四把光剑旋转', '四个光剑旋转', '四个合体光剑旋转'},
}
LIGHT_SWORD_ROTATION_START = {'静止到旋转', '从静止到旋转', '从静止到开始旋转', '从停下到转'}

LIGHT_SWORD_CUT = '''
每条光剑成片必须分别安排单把光剑旋转和四把光剑旋转，各至少一个镜头，以用户确认的素材类别为依据。
单条成片中，「拆分光剑」与「安装光剑」合计最多出现一次。可以两种都省略，也可以任选其中一种用一个镜头；同一镜头若同时含拆分与安装，也不得选用。以实际选区的动作和已确认类别核对。
单条成片中，「产品揭示」和「带货指引」各最多出现一次，两类可在同一条成片中各出现一次。拆分、安装、产品揭示和带货指引均为可选镜头，单条成片可以全部省略。次数限制是上限；只在镜头适合本条内容和节奏时使用。
若当前产品为 LED Finger Spinner Sword Toy（手持式短剑／指旋玩具），可主动设计同款主体接不同场景或角度的切镜。
这种接法适用于单把、四把连接成一组和多把独立同框。先用短剑轮廓、十字护手、中央指孔和手柄确认同款，再比较相邻选区的首尾画面。
同一展示重点可以主动选两段或多段有可见依据的素材，让不同场景或角度相互印证。
例如四把组合正面接另一场景的侧面组合，或多把独立陈列接手持同框。每段应让观众看清同一重点。
普通展示可在单把、组合和多把独立之间切换；若正在说明数量或连接关系，接续镜头应保持该事实，或让变化清楚可辨。
优先让同款实物在切点前后都清楚可辨，并以相近灯色、主体位置或大小作为衔接依据；
场景、景别、持剑方向可以变化，例如红灯正面手持接另一场景的红灯倒握近景。
灯色会变化，只有对应选区有证据时才声称切点灯色一致；单凭灯色不能认定同款。
相同角度换颜色、同类旋转灯效、同构图反复手持等同类展示最多连续两镜。第三镜必须改变展示方式或构图（如手持变旋转、近景变全景、静物变入画揭示），仅换颜色不算变化。
先见背景、再从画外拿入有盒或无盒光剑并亮相，是有效的揭示镜头。适合作开头或由平稳展示转入新阶段，裁切时保留短铺垫与产品亮相。
可在普通展示段灵活排列、复用合适素材，给两边足够时间看清产品，避免为了换角度连续切碎。
若参考开头指定包装、数量或连接形态，优先保留这些可见事实。
全片只在最后一个镜头优先静态展示、带货指引或旋转到停下。
'''
