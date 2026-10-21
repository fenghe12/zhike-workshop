from __future__ import annotations

from copy import deepcopy
from typing import Any


LESSON_LIBRARY: dict[str, dict[str, Any]] = {
    "linear-function": {
        "subject": "初中数学",
        "topic": "一次函数的斜率与图像变化",
        "grade": "八年级",
        "objective": "理解一次函数 y=kx+b 中斜率与截距的几何意义，并能由两点求斜率。",
        "prerequisites": ["平面直角坐标系", "正比例关系", "有理数运算"],
        "scenes": [
            {
                "title": "从路程变化认识斜率",
                "visual": "line_intro",
                "key_points": ["横轴：时间；纵轴：路程", "每分钟增加 200 米", "k=Δy/Δx 表示变化率"],
                "focus_regions": ["A3:D5", "B3:D5", "B5:E6"],
                "highlight_sentence_indices": [1, 2, 4],
                "script_text": "先观察一辆匀速行驶的自行车。横轴表示时间，纵轴表示路程。每经过一分钟，路程增加两百米，因此图像是一条向右上方延伸的直线。直线越陡，相同时间内增加的路程越多。我们把纵向变化量除以横向变化量所得的比值称为斜率。",
            },
            {
                "title": "斜率 k 决定直线倾斜程度",
                "visual": "slope_compare",
                "key_points": ["蓝线 k=2；绿线 k=1；橙线 k=-1.5", "k>0 上升；k<0 下降", "|k| 越大，直线越陡"],
                "focus_regions": ["A2:D5", "A2:D5", "A2:E5"],
                "highlight_sentence_indices": [1, 2, 3],
                "script_text": "把三条一次函数画在同一坐标系中。蓝线的斜率为二，绿线的斜率为一，橙线的斜率为负一点五。正斜率对应从左下向右上的直线，负斜率对应从左上向右下的直线。斜率绝对值越大，直线越陡；绝对值越小，直线越平缓。",
            },
            {
                "title": "截距 b 控制上下平移",
                "visual": "intercept_shift",
                "key_points": ["斜率相同，三条直线互相平行", "b 表示 y 轴交点纵坐标", "b 增大，直线向上平移"],
                "focus_regions": ["A2:D5", "B2:C5", "A2:D5"],
                "highlight_sentence_indices": [1, 2, 3],
                "script_text": "保持斜率 k 等于一，只改变常数 b。函数 y=x、y=x+2 和 y=x-2 的图像互相平行，因为它们的倾斜程度相同。b 表示直线与 y 轴相交位置的纵坐标。b 增大，整条直线向上平移；b 减小，整条直线向下平移。",
            },
            {
                "title": "由两点计算斜率",
                "visual": "two_point_slope",
                "key_points": ["先求纵向变化量", "再求横向变化量", "k=(y₂-y₁)/(x₂-x₁)"],
                "focus_regions": ["B3:D5", "B3:D5", "D3:F5"],
                "highlight_sentence_indices": [1, 2, 3],
                "script_text": "已知直线经过 A 点一二和 B 点三六。纵向变化量是六减二，得到四；横向变化量是三减一，得到二。斜率等于四除以二，结果为二。计算时要保持两个差的点序一致，先用 B 点减 A 点，分子和分母都按相同顺序书写。",
            },
            {
                "title": "斜率在实际问题中的含义",
                "visual": "rate_application",
                "key_points": ["水量变化率：3 L/min", "温度变化率：-2 ℃/h", "路程—时间图像的斜率表示速度"],
                "focus_regions": ["A3:B5", "C3:D5", "E3:F5"],
                "highlight_sentence_indices": [1, 2, 3],
                "script_text": "斜率描述变化速度。水箱每分钟增加三升水，水量随时间图像的斜率就是三；气温每小时下降两摄氏度，温度图像的斜率就是负二；匀速运动中，路程时间图像的斜率就是速度。判断单位能够帮助我们解释斜率的实际意义。",
            },
            {
                "title": "总结与自测",
                "visual": "line_quiz",
                "key_points": ["k 判断方向和陡缓", "b 判断 y 轴交点", "两点式用于计算斜率"],
                "focus_regions": ["A2:D4", "A3:D5", "D3:F5"],
                "highlight_sentence_indices": [1, 2, 3],
                "script_text": "本节课形成三个结论。第一，k 的正负决定直线是上升还是下降，绝对值决定陡缓。第二，b 决定直线与 y 轴的交点。第三，已知两点时可以用纵向变化量除以横向变化量求斜率。请判断 y 等于负三 x 加一的方向、陡缓和 y 轴交点。",
            },
        ],
    },
    "light-reflection": {
        "subject": "初中物理",
        "topic": "光的反射定律",
        "grade": "八年级",
        "objective": "认识入射光线、反射光线、法线和反射角，并能利用反射定律解释现象。",
        "prerequisites": ["直线与角", "光沿直线传播", "平面镜"],
        "scenes": [
            {
                "title": "光遇到镜面会发生什么",
                "visual": "reflection_intro",
                "key_points": ["光遇镜面改变传播方向", "入射光线、反射光线与入射点", "建立法线描述光线方向"],
                "focus_regions": ["A2:D5", "B2:E5", "C2:D5"],
                "highlight_sentence_indices": [0, 1, 2],
                "script_text": "一束光射到平面镜表面后改变传播方向，这种现象称为光的反射。射向镜面的光线叫入射光线，离开镜面的光线叫反射光线，两条光线与镜面的交点叫入射点。接下来需要建立一条辅助线，才能准确描述两条光线的方向。",
            },
            {
                "title": "法线、入射角与反射角",
                "visual": "reflection_terms",
                "key_points": ["法线经过入射点并垂直镜面", "入射角与反射角均以法线为基准", "不能将光线与镜面的夹角直接代入"],
                "focus_regions": ["C2:D5", "B2:E5", "B2:E5"],
                "highlight_sentence_indices": [0, 1, 2],
                "script_text": "过入射点作一条与镜面垂直的虚线，这条线叫法线。入射光线与法线之间的夹角叫入射角，反射光线与法线之间的夹角叫反射角。两个角都相对于法线测量，不能把光线与镜面的夹角直接当作入射角或反射角。",
            },
            {
                "title": "反射角等于入射角",
                "visual": "reflection_angles",
                "key_points": ["入射角 20°，反射角 20°", "反射角等于入射角：r=i", "光路具有可逆性"],
                "focus_regions": ["A2:C5", "A2:E5", "B2:E5"],
                "highlight_sentence_indices": [1, 3, 4],
                "script_text": "逐渐改变入射光线方向，可以看到反射光线始终关于法线对称。入射角为二十度时，反射角也是二十度；入射角增大到四十度，反射角同步增大到四十度。这说明反射角等于入射角。沿反射光线反向照射，光会沿原入射路径返回。",
            },
            {
                "title": "用实验验证反射定律",
                "visual": "reflection_experiment",
                "key_points": ["纸板显示入射与反射光路", "量角器分别测量两个角", "改变入射角并记录多组数据"],
                "focus_regions": ["A2:D5", "B2:D5", "D2:F5"],
                "highlight_sentence_indices": [0, 1, 2],
                "script_text": "实验时把平面镜竖直放在白色纸板上，用激光笔沿纸板射向镜面。画出入射光线、法线和反射光线，再用量角器分别测量两个角。改变入射角重复测量，记录多组数据。多次实验能够减小偶然误差，并验证两个角始终相等。",
            },
            {
                "title": "镜面反射与漫反射",
                "visual": "reflection_surface",
                "key_points": ["光滑表面形成规则反射", "粗糙表面形成漫反射", "每一条光线都遵守反射定律"],
                "focus_regions": ["A2:C5", "D2:F5", "A2:F5"],
                "highlight_sentence_indices": [0, 1, 2],
                "script_text": "平整镜面上的平行光反射后仍然平行，形成镜面反射。粗糙纸面由许多朝向不同的微小平面组成，反射光向不同方向传播，形成漫反射。漫反射看起来方向分散，但每一条光线在对应的微小表面上仍然满足反射角等于入射角。",
            },
            {
                "title": "总结与光路判断",
                "visual": "reflection_quiz",
                "key_points": ["反射光路图分为三步", "入射点→法线→等角反射光线", "所有角度均以法线为基准"],
                "focus_regions": ["A2:D5", "B2:E5", "C2:D5"],
                "highlight_sentence_indices": [0, 1, 2],
                "script_text": "完成反射光路图可以分为三步。先找到入射点，再过入射点作镜面的法线，最后在法线另一侧按照等角关系画出反射光线。判断角度时始终以法线为基准。请观察给出的入射光线，确定反射光线应位于哪个方向，并说明依据。",
            },
        ],
    },
    "ph-indicator": {
        "subject": "初中化学",
        "topic": "溶液酸碱度与指示剂",
        "grade": "九年级",
        "objective": "理解 pH 与溶液酸碱性的关系，掌握常见指示剂和 pH 试纸的规范使用方法。",
        "prerequisites": ["溶液", "酸和碱的初步性质", "实验安全"],
        "scenes": [
            {
                "title": "用 pH 表示酸碱度",
                "visual": "ph_scale",
                "key_points": ["pH 小于 7 为酸性", "pH 等于 7 为中性", "pH 大于 7 为碱性"],
                "focus_regions": ["A3:C5", "C3:D5", "D3:F5"],
                "highlight_sentence_indices": [1, 2, 3],
                "script_text": "溶液的酸碱性可以用 pH 表示，常见范围是零到十四。pH 小于七时溶液呈酸性，数值越小酸性越强；pH 等于七时呈中性；pH 大于七时呈碱性，数值越大碱性越强。pH 是连续变化的量，不能只按酸、碱两个类别理解。",
            },
            {
                "title": "酸性和碱性的微观来源",
                "visual": "ion_balance",
                "key_points": ["酸性：H⁺较多；碱性：OH⁻较多", "中性：H⁺与OH⁻相对平衡", "粒子数量表示相对关系"],
                "focus_regions": ["A2:F5", "C2:D5", "A2:F5"],
                "highlight_sentence_indices": [0, 1, 2],
                "script_text": "从微观角度观察，酸性溶液中氢离子的相对含量较高，碱性溶液中氢氧根离子的相对含量较高。中性溶液中两者处于相对平衡状态。图中的粒子数量用于表示相对关系，实际溶液中还含有水分子和其他离子。",
            },
            {
                "title": "常见酸碱指示剂",
                "visual": "indicator_cards",
                "key_points": ["石蕊遇酸变红、遇碱变蓝", "酚酞遇碱变红", "指示剂只能判断范围"],
                "focus_regions": ["A2:F5", "D2:F5", "A2:F5"],
                "highlight_sentence_indices": [1, 2, 3],
                "script_text": "石蕊和酚酞是常见酸碱指示剂。紫色石蕊在酸性溶液中变红，在碱性溶液中变蓝；无色酚酞在酸性和中性溶液中保持无色，在碱性溶液中变红。指示剂通过颜色变化判断酸碱性，通常不能直接给出准确 pH 数值。",
            },
            {
                "title": "规范使用 pH 试纸",
                "visual": "ph_paper",
                "key_points": ["洁净取样、滴在试纸上并立即比色", "禁止浸入待测液或预先湿润试纸"],
                "focus_regions": ["A2:D5", "A2:F5"],
                "highlight_sentence_indices": [0, 1],
                "script_text": "测量 pH 时，把一小片试纸放在洁净玻璃片上，用洁净干燥的玻璃棒蘸取待测溶液，滴在试纸上，立即与标准比色卡比较。不能把试纸直接浸入待测液，也不能先用水湿润试纸，否则会污染溶液或改变浓度，使测量结果产生偏差。",
            },
            {
                "title": "生活样品的酸碱度",
                "visual": "ph_samples",
                "key_points": ["柠檬汁呈酸性", "纯水接近中性", "肥皂水呈碱性"],
                "focus_regions": ["A2:B5", "C2:D5", "E2:F5"],
                "highlight_sentence_indices": [1, 2, 3],
                "script_text": "比较三种常见样品。柠檬汁的 pH 约为二，呈酸性；纯水在适宜条件下接近七，呈中性；肥皂水的 pH 常在九到十之间，呈碱性。具体数值会受到浓度、温度和样品配方影响，因此实验记录应写明样品条件和测量方法。",
            },
            {
                "title": "总结与实验判断",
                "visual": "ph_quiz",
                "key_points": ["pH 数值区分酸性、中性和碱性", "指示剂颜色判断溶液性质", "洁净取样并及时比色"],
                "focus_regions": ["D2:F4", "A2:C4", "A2:F5"],
                "highlight_sentence_indices": [1, 2, 3],
                "script_text": "本节课需要建立三层联系。第一，用 pH 数值区分酸性、中性和碱性。第二，根据石蕊、酚酞的颜色变化判断溶液性质。第三，使用 pH 试纸时保持取样工具洁净并及时比色。请根据给出的颜色和 pH 信息，判断未知溶液的性质并说明实验依据。",
            },
        ],
    },
}


def get_lesson_spec(lesson_id: str) -> dict[str, Any]:
    try:
        value = deepcopy(LESSON_LIBRARY[lesson_id])
    except KeyError as exc:
        raise ValueError(f"不支持的代码动画课件：{lesson_id}") from exc
    value["lesson_id"] = lesson_id
    for index, scene in enumerate(value["scenes"], start=1):
        scene["scene_id"] = index
        scene["class_name"] = f"Scene{index:02d}"
        scene["avatar_position"] = "right_bottom"
    return value


def list_lesson_specs() -> list[dict[str, str]]:
    return [
        {
            "lessonId": lesson_id,
            "subject": value["subject"],
            "topic": value["topic"],
            "grade": value["grade"],
        }
        for lesson_id, value in LESSON_LIBRARY.items()
    ]
