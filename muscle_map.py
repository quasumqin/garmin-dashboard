#!/usr/bin/env python3
"""动作 → 肌群 / 器械映射，以及周训练覆盖的判定规则。

Garmin 的活动接口只给到 category / subCategory，不返回肌肉信息，
所以这份映射是自己建的：大类打底，有子类时以子类为准（子类更准，
例如 SQUAT 底下既有腿举也有负重深蹲）。

术语说明：
- 肌群（muscle）：人体图上的着色单位，共 17 个。
- 覆盖部位（coverage）：周覆盖统计的单位，共 11 个，比肌群粗一档，
  因为「背」下面的斜方、背阔、竖脊肌没法分开统计有效组数。
"""

# ---------------------------------------------------------------- 肌群
# key: (中文名, 正面/背面)  —— 三角肌分三束，正面画前束与中束，背面画后束与中束
MUSCLES = {
    "chest":      ("胸大肌", "front"),
    "delt_front": ("三角肌前束", "front"),
    "delt_side":  ("三角肌中束", "both"),
    "delt_rear":  ("三角肌后束", "back"),
    "biceps":     ("肱二头肌", "front"),
    "triceps":    ("肱三头肌", "back"),
    "forearm":    ("前臂", "both"),
    "traps":      ("斜方肌", "both"),
    "lats":       ("背阔肌", "back"),
    "lower_back": ("竖脊肌（下背）", "back"),
    "abs":        ("腹直肌", "front"),
    "obliques":   ("腹斜肌", "front"),
    "glute_max":  ("臀大肌", "back"),
    "glute_med":  ("臀中肌", "back"),
    "quads":      ("股四头肌", "front"),
    "hamstrings": ("腘绳肌", "back"),
    "calves":     ("小腿", "both"),
}

# ---------------------------------------------------------------- 覆盖部位
COVERAGE_OF = {
    "chest": "胸",
    "delt_front": "肩", "delt_side": "肩", "delt_rear": "肩",
    "biceps": "二头",
    "triceps": "三头",
    "forearm": "前臂",
    "traps": "背", "lats": "背", "lower_back": "背",
    "abs": "核心", "obliques": "核心",
    "glute_max": "臀", "glute_med": "臀",
    "quads": "腿前",
    "hamstrings": "腿后",
    "calves": "小腿",
}

# 每周有效组数参考区间（常规增肌口径，见页面脚注）
WEEKLY_STD = {
    "胸":   (10, 20),
    "背":   (10, 20),
    "肩":   (8, 16),
    "二头": (6, 14),
    "三头": (6, 14),
    "前臂": (4, 10),
    "核心": (6, 16),
    "臀":   (6, 16),
    "腿前": (8, 18),
    "腿后": (6, 14),
    "小腿": (6, 12),
}

COVERAGE_ORDER = list(WEEKLY_STD.keys())

# 本项目的 17 个肌群 → MuscleMap 的 SVG slug。
# 肩的三束、臀大/臀中在图上共用整块路径，明细统计仍分开。
MUSCLE_TO_SLUGS = {
    "chest":      ["chest", "upper-chest", "lower-chest"],
    "delt_front": ["deltoids", "front-deltoid"],
    "delt_side":  ["deltoids"],
    "delt_rear":  ["deltoids", "rear-deltoid"],
    "biceps":     ["biceps"],
    "triceps":    ["triceps"],
    "forearm":    ["forearm"],
    "traps":      ["trapezius", "upper-trapezius", "lower-trapezius"],
    "lats":       ["upper-back"],
    "lower_back": ["lower-back"],
    "abs":        ["abs", "upper-abs", "lower-abs"],
    "obliques":   ["obliques"],
    "glute_max":  ["gluteal"],
    "glute_med":  ["gluteal"],
    "quads":      ["quadriceps", "inner-quad", "outer-quad"],
    "hamstrings": ["hamstring"],
    "calves":     ["calves"],
}

# ---------------------------------------------------------------- 器械
EQUIPMENT = {
    "barbell":     "杠铃",
    "dumbbell":    "哑铃",
    "bench":       "卧推架",
    "squat_rack":  "深蹲架",
    "cable":       "龙门架 / 绳索",
    "cable_row":   "坐姿划船机",
    "lat_pulldown": "高位下拉机",
    "leg_press":   "腿举机",
    "hip_thrust":  "臀推架",
    "abductor":    "髋外展机",
    "pullup_bar":  "单杠",
    "suspension":  "悬吊带",
    "bodyweight":  "自重",
    "leg_curl":    "腿弯举机",
    "calf_machine": "提踵机",
    "pec_deck":    "蝴蝶机",
    "hack_squat":  "哈克深蹲机",
}

# 单色简笔图标（64×64 线稿），由页面内联渲染
EQUIPMENT_ICONS = {
    "barbell": """<g><path d="M8 32h48"/><rect x="10" y="22" width="6" height="20" rx="1.5"/><rect x="18" y="25" width="5" height="14" rx="1.5"/><rect x="41" y="25" width="5" height="14" rx="1.5"/><rect x="48" y="22" width="6" height="20" rx="1.5"/></g>""",
    "dumbbell": """<g><path d="M18 32h28"/><rect x="8" y="21" width="9" height="22" rx="2"/><rect x="47" y="21" width="9" height="22" rx="2"/></g>""",
    "bench": """<g><path d="M10 46h44"/><path d="M14 46V28h34"/><path d="M18 28h26"/><path d="M42 28V14h10v14"/><circle cx="14" cy="50" r="3"/><circle cx="50" cy="50" r="3"/></g>""",
    "squat_rack": """<g><path d="M14 54V12M50 54V12M14 20h36M14 40h36"/><path d="M10 12h8M46 12h8"/><circle cx="20" cy="32" r="2"/><circle cx="44" cy="32" r="2"/></g>""",
    "cable": """<g><path d="M12 54V10h40v10"/><circle cx="52" cy="24" r="4"/><path d="M52 28v14"/><path d="M46 42h12"/><path d="M12 20h18"/></g>""",
    "cable_row": """<g><path d="M10 54V14h14v10"/><path d="M24 24h26"/><circle cx="52" cy="24" r="4"/><path d="M52 28v10"/><path d="M44 38h16v8H44z"/><path d="M30 54v-8h14"/></g>""",
    "lat_pulldown": """<g><path d="M12 54V10h40"/><path d="M32 10v8"/><path d="M20 30h24"/><path d="M20 30l-6 10M44 30l6 10"/><path d="M32 18v12"/></g>""",
    "leg_press": """<g><path d="M8 52l30-34 8 7L16 59z"/><path d="M38 18l10-8 8 7-8 8"/><path d="M20 56l6 6"/><path d="M10 30l12 10"/></g>""",
    "hip_thrust": """<g><path d="M8 46h24v-10"/><path d="M32 36h16"/><path d="M14 46v8M42 46v8"/><path d="M20 24h18"/><circle cx="14" cy="24" r="3"/></g>""",
    "abductor": """<g><path d="M16 54V30h32v24"/><path d="M22 30V18h20v12"/><path d="M22 36h-8v8h8M42 36h8v8h-8"/><path d="M16 54h32"/></g>""",
    "pullup_bar": """<g><path d="M10 14h44"/><path d="M16 14v40M48 14v40"/><path d="M16 54h8M40 54h8"/><path d="M24 24v10h16V24"/></g>""",
    "suspension": """<g><path d="M32 8v10"/><path d="M32 18l-12 30M32 18l12 30"/><path d="M12 52h12M40 52h12"/><circle cx="32" cy="10" r="3"/></g>""",
    "bodyweight": """<g><circle cx="32" cy="13" r="6"/><path d="M32 20v16M32 24l-12 8M32 24l12 8M32 36l-8 16M32 36l8 16"/></g>""",
    "leg_curl": """<g><path d="M10 40h28V22"/><path d="M38 22h16"/><path d="M38 30h14"/><path d="M14 40v14M54 22v22"/><circle cx="50" cy="36" r="6"/></g>""",
    "calf_machine": """<g><path d="M14 54h36"/><path d="M20 54V22h24v32"/><path d="M28 22V10h12v12"/><path d="M20 34h24"/></g>""",
    "pec_deck": """<g><path d="M26 56V18h12v38"/><path d="M26 28L10 20v10l16 8M38 28l16-8v10l-16 8"/><path d="M32 12v6"/></g>""",
    "hack_squat": """<g><path d="M8 54l28-32 14 12-26 30z"/><path d="M34 20l14-10 10 9-10 10"/><path d="M12 58h40"/></g>""",
}
DEFAULT_ICON = """<g><rect x="10" y="22" width="44" height="30" rx="4"/><path d="M10 32h44M24 22v30M40 22v30"/></g>"""

# ---------------------------------------------------------------- 动作映射
# primary / secondary 填肌群 key；equipment 填器械 key
# 说明：自重动作的器械记为 bodyweight，不代表不需要器械
EXERCISES = {
    # 胸
    "BENCH_PRESS":        dict(cn="卧推",       primary=["chest"], secondary=["delt_front", "triceps"], equipment="bench"),
    "PUSH_UP":            dict(cn="俯卧撑",     primary=["chest"], secondary=["delt_front", "triceps", "abs"], equipment="bodyweight"),
    "FLYE":               dict(cn="飞鸟",       primary=["chest"], secondary=["delt_front"], equipment="dumbbell"),
    "CABLE_CROSSOVER":    dict(cn="绳索夹胸",   primary=["chest"], secondary=["delt_front"], equipment="cable"),
    "CHEST_FLY":          dict(cn="夹胸",       primary=["chest"], secondary=["delt_front"], equipment="suspension"),
    "PEC_DECK":           dict(cn="蝴蝶机夹胸", primary=["chest"], secondary=["delt_front"], equipment="pec_deck"),
    # 肩
    "SHOULDER_PRESS":     dict(cn="肩推",       primary=["delt_front", "delt_side"], secondary=["triceps", "traps"], equipment="dumbbell"),
    "LATERAL_RAISE":      dict(cn="侧平举",     primary=["delt_side"], secondary=["traps"], equipment="dumbbell"),
    "REVERSE_FLYE":       dict(cn="反向飞鸟",   primary=["delt_rear"], secondary=["traps"], equipment="dumbbell"),
    "FACE_PULL":          dict(cn="面拉",       primary=["delt_rear"], secondary=["traps"], equipment="cable"),
    # 手臂
    "CURL":               dict(cn="弯举",       primary=["biceps"], secondary=["forearm"], equipment="dumbbell"),
    "HAMMER_CURL":        dict(cn="锤式弯举",   primary=["biceps"], secondary=["forearm"], equipment="dumbbell"),
    "TRICEPS_EXTENSION":  dict(cn="三头下压",   primary=["triceps"], secondary=["forearm"], equipment="cable"),
    "DUMBBELL_KICKBACK":  dict(cn="哑铃臂后伸", primary=["triceps"], secondary=[], equipment="dumbbell"),
    "OVERHEAD_TRICEPS":   dict(cn="过头臂屈伸", primary=["triceps"], secondary=[], equipment="dumbbell"),
    # 背
    "PULL_UP":            dict(cn="引体向上",   primary=["lats"], secondary=["biceps", "traps", "delt_rear"], equipment="pullup_bar"),
    "LAT_PULLDOWN":       dict(cn="高位下拉",   primary=["lats"], secondary=["biceps", "traps", "delt_rear"], equipment="lat_pulldown"),
    "ROW":                dict(cn="划船",       primary=["lats", "traps"], secondary=["biceps", "delt_rear", "lower_back"], equipment="cable"),
    "SEATED_CABLE_ROW":   dict(cn="坐姿绳索划船", primary=["lats", "traps"], secondary=["biceps", "delt_rear"], equipment="cable_row"),
    "SUSPENSION":         dict(cn="悬吊训练",   primary=["abs"], secondary=["chest", "lats"], equipment="suspension"),
    # 腿
    "SQUAT":              dict(cn="深蹲",       primary=["quads", "glute_max"], secondary=["hamstrings", "abs", "calves"], equipment="squat_rack"),
    "WEIGHTED_SQUAT":     dict(cn="负重深蹲",   primary=["quads", "glute_max"], secondary=["hamstrings", "abs", "calves"], equipment="squat_rack"),
    "LEG_PRESS":          dict(cn="腿举",       primary=["quads", "glute_max"], secondary=["hamstrings", "calves"], equipment="leg_press"),
    "HACK_SQUAT":         dict(cn="哈克深蹲",   primary=["quads", "glute_max"], secondary=["hamstrings", "calves"], equipment="hack_squat"),
    "LUNGE":              dict(cn="弓步",       primary=["quads", "glute_max"], secondary=["hamstrings", "calves", "abs"], equipment="dumbbell"),
    "DEADLIFT":           dict(cn="硬拉",       primary=["hamstrings", "glute_max", "lower_back"], secondary=["lats", "traps", "forearm", "abs"], equipment="barbell"),
    "BARBELL_DEADLIFT":   dict(cn="杠铃硬拉",   primary=["hamstrings", "glute_max", "lower_back"], secondary=["lats", "traps", "forearm", "abs"], equipment="barbell"),
    "ROMANIAN_DEADLIFT":  dict(cn="罗马尼亚硬拉", primary=["hamstrings", "glute_max"], secondary=["lower_back", "forearm"], equipment="barbell"),
    "LEG_CURL":           dict(cn="腿弯举",     primary=["hamstrings"], secondary=["calves"], equipment="leg_curl"),
    "HIP_RAISE":          dict(cn="臀桥",       primary=["glute_max"], secondary=["hamstrings", "abs"], equipment="hip_thrust"),
    "BARBELL_HIP_THRUST_ON_FLOOR": dict(cn="杠铃臀推", primary=["glute_max"], secondary=["hamstrings", "abs"], equipment="hip_thrust"),
    "HIP_STABILITY":      dict(cn="髋稳定",     primary=["glute_med"], secondary=["glute_max"], equipment="abductor"),
    "WEIGHTED_STANDING_HIP_ABDUCTION": dict(cn="站姿髋外展", primary=["glute_med"], secondary=["glute_max"], equipment="abductor"),
    "STANDING_CALF_RAISE": dict(cn="站姿提踵",  primary=["calves"], secondary=[], equipment="dumbbell"),
    "SEATED_CALF_RAISE":  dict(cn="坐姿提踵",   primary=["calves"], secondary=[], equipment="calf_machine"),
    # 核心
    "SIT_UP":             dict(cn="仰卧起坐",   primary=["abs"], secondary=["obliques"], equipment="bodyweight"),
    "CRUNCH":             dict(cn="卷腹",       primary=["abs"], secondary=["obliques"], equipment="bodyweight"),
    "PLANK":              dict(cn="平板支撑",   primary=["abs"], secondary=["obliques"], equipment="bodyweight"),
    "HANGING_LEG_RAISE":  dict(cn="悬垂举腿",   primary=["abs"], secondary=["obliques", "forearm"], equipment="pullup_bar"),
    # 前臂
    "WRIST_CURL":         dict(cn="腕弯举",     primary=["forearm"], secondary=[], equipment="dumbbell"),
    "FARMER_CARRY":       dict(cn="农夫行走",   primary=["forearm"], secondary=["traps", "abs"], equipment="dumbbell"),
}

UNKNOWN_EXERCISE = dict(cn="未分类", primary=[], secondary=[], equipment="bodyweight")


def lookup(category, sub_category=None):
    """子类优先；没有子类回退到大类；都没有返回未分类。"""
    if sub_category and sub_category in EXERCISES:
        return sub_category, EXERCISES[sub_category]
    if category and category in EXERCISES:
        return category, EXERCISES[category]
    return None, UNKNOWN_EXERCISE


def muscle_units(exercise, sets):
    """把一次动作拆成「有效组」贡献：主要肌群 1.0 组、次要 0.5 组。

    同一个动作里，若某肌群既出现在主要也出现在次要，按主要计，不重复。
    """
    primary = [(m, sets * 1.0) for m in exercise["primary"]]
    pset = set(exercise["primary"])
    secondary = [(m, sets * 0.5) for m in exercise["secondary"] if m not in pset]
    return primary, secondary


def coverage_units(exercise, sets):
    """把一次动作折算成覆盖部位的有效组，避免同一部位的多个肌群重复计数。"""
    pg = {COVERAGE_OF[m] for m in exercise["primary"] if m in COVERAGE_OF}
    sg = {COVERAGE_OF[m] for m in exercise["secondary"] if m in COVERAGE_OF} - pg
    return [(g, sets * 1.0) for g in pg], [(g, sets * 0.5) for g in sg]


# ---------------------------------------------------------------- 补充动作建议
# 只在「本周缺某部位」时给出；equipment 用于和 gym_equipment.json 取交集
SUGGESTIONS = {
    "胸": [
        dict(name="卧推", equipment="bench", why="胸部主力动作，能上重量"),
        dict(name="绳索夹胸", equipment="cable", why="补充胸部内侧与顶峰收缩"),
        dict(name="俯卧撑", equipment="bodyweight", why="没有器械时的兜底动作"),
    ],
    "背": [
        dict(name="高位下拉", equipment="lat_pulldown", why="背阔肌垂直拉，容易找到发力"),
        dict(name="坐姿绳索划船", equipment="cable_row", why="背部水平拉，兼顾斜方肌中束"),
        dict(name="引体向上", equipment="pullup_bar", why="自重垂直拉，强度高"),
    ],
    "肩": [
        dict(name="哑铃肩推", equipment="dumbbell", why="三角肌前束与中束"),
        dict(name="侧平举", equipment="dumbbell", why="中束孤立，改善肩宽视觉"),
        dict(name="反向飞鸟", equipment="dumbbell", why="后束，久坐人群普遍薄弱"),
    ],
    "二头": [
        dict(name="哑铃弯举", equipment="dumbbell", why="二头基础动作"),
        dict(name="锤式弯举", equipment="dumbbell", why="兼顾肱肌与前臂"),
    ],
    "三头": [
        dict(name="绳索下压", equipment="cable", why="三头外侧，动作稳定"),
        dict(name="过头臂屈伸", equipment="dumbbell", why="三头长头，拉伸位发力"),
    ],
    "前臂": [
        dict(name="农夫行走", equipment="dumbbell", why="握力与核心一起练"),
        dict(name="腕弯举", equipment="dumbbell", why="前臂孤立"),
    ],
    "核心": [
        dict(name="卷腹", equipment="bodyweight", why="腹直肌基础动作"),
        dict(name="平板支撑", equipment="bodyweight", why="抗伸展，练深层稳定"),
        dict(name="悬垂举腿", equipment="pullup_bar", why="下腹与髋屈肌"),
    ],
    "臀": [
        dict(name="杠铃臀推", equipment="hip_thrust", why="臀大肌孤立，可上重量"),
        dict(name="保加利亚分腿蹲", equipment="dumbbell", why="单腿臀腿，兼练稳定"),
    ],
    "腿前": [
        dict(name="腿举", equipment="leg_press", why="股四头安全堆量"),
        dict(name="哈克深蹲", equipment="hack_squat", why="股四头主导，腰背压力小于自由深蹲"),
        dict(name="深蹲", equipment="squat_rack", why="下肢综合动作"),
        dict(name="弓步", equipment="dumbbell", why="单腿模式，补左右差异"),
    ],
    "腿后": [
        dict(name="罗马尼亚硬拉", equipment="barbell", why="腘绳肌拉伸位发力"),
        dict(name="哑铃罗马尼亚硬拉", equipment="dumbbell", why="重量可控，适合找感觉"),
    ],
    "小腿": [
        dict(name="站姿提踵", equipment="dumbbell", why="腓肠肌，站姿屈膝少"),
        dict(name="腿举机提踵", equipment="leg_press", why="用腿举机做提踵，负重大"),
    ],
}

# 动作 → 线稿图片（assets/exercises/{stem}.png，Everkinetic，CC BY-SA 3.0）
EXERCISE_IMAGES = {
    "BENCH_PRESS": "bench-press",
    "PUSH_UP": "push-up",
    "FLYE": "dumbbell-fly",
    "CABLE_CROSSOVER": "cable-crossover",
    "CHEST_FLY": "butterfly",
    "PEC_DECK": "butterfly",
    "SHOULDER_PRESS": "shoulder-press",
    "LATERAL_RAISE": "lateral-raise",
    "CURL": "biceps-curl",
    "HAMMER_CURL": "biceps-curl",
    "TRICEPS_EXTENSION": "triceps-pushdown",
    "DUMBBELL_KICKBACK": "triceps-kickback",
    "OVERHEAD_TRICEPS": "triceps-pushdown",
    "PULL_UP": "pull-up",
    "LAT_PULLDOWN": "lat-pulldown",
    "ROW": "seated-cable-row",
    "SEATED_CABLE_ROW": "seated-cable-row",
    "SQUAT": "squat",
    "WEIGHTED_SQUAT": "squat",
    "HACK_SQUAT": "hack-squat",
    "LEG_PRESS": "leg-press",
    "LUNGE": "lunge",
    "DEADLIFT": "romanian-deadlift",
    "BARBELL_DEADLIFT": "romanian-deadlift",
    "ROMANIAN_DEADLIFT": "romanian-deadlift",
    "LEG_CURL": "leg-curl",
    "HIP_RAISE": "bridge",
    "BARBELL_HIP_THRUST_ON_FLOOR": "bridge",
    "HIP_STABILITY": "hip-abduction",
    "WEIGHTED_STANDING_HIP_ABDUCTION": "hip-abduction",
    "STANDING_CALF_RAISE": "calf-raise",
    "SEATED_CALF_RAISE": "calf-raise",
    "SIT_UP": "crunch",
    "CRUNCH": "crunch",
}
