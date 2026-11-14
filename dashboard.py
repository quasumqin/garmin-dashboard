#!/usr/bin/env python3
"""把库里的数据渲染成单文件 HTML 看板。

    python3 garmin.py dashboard            # 默认 90 天
    python3 dashboard.py --days 90
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import common
import config
import db
from garmin import TYPE_CN, _type_cn
from muscle_map import (
    COVERAGE_ORDER, DEFAULT_ICON, EQUIPMENT, EQUIPMENT_EN, EQUIPMENT_ICONS,
    EXERCISE_EN, MUSCLES, MUSCLE_EN, WEEKLY_STD,
)

TEMPLATE = Path(__file__).parent / "template.html"
EN_LOCALE = Path(__file__).parent / "locale" / "en.json"
CHARTJS = Path(__file__).parent / "assets" / "chart.umd.min.js"
OUT = config.REPORT_DIR / "dashboard.html"


# 力量训练动作：Garmin 类别 → 中文名 / 部位
EX_CN = {
    "BENCH_PRESS": "卧推", "PUSH_UP": "俯卧撑", "FLYE": "飞鸟", "SHOULDER_PRESS": "肩推",
    "LATERAL_RAISE": "侧平举", "TRICEPS_EXTENSION": "三头下压",
    "CURL": "弯举", "PULL_UP": "引体向上", "ROW": "划船", "SUSPENSION": "悬吊",
    "SQUAT": "深蹲", "LUNGE": "弓步", "DEADLIFT": "硬拉", "HIP_RAISE": "臀桥",
    "SIT_UP": "仰卧起坐", "HIP_STABILITY": "髋稳定",
    "HACK_SQUAT": "哈克深蹲",
}
EX_GROUP = {
    "BENCH_PRESS": "推", "PUSH_UP": "推", "FLYE": "推", "SHOULDER_PRESS": "推",
    "LATERAL_RAISE": "推", "TRICEPS_EXTENSION": "推",
    "CURL": "拉", "PULL_UP": "拉", "ROW": "拉",
    "SQUAT": "腿", "LUNGE": "腿", "DEADLIFT": "腿", "HIP_RAISE": "腿", "HIP_STABILITY": "腿",
    "SIT_UP": "核心", "SUSPENSION": "核心",
    "HACK_SQUAT": "腿",
}

# 子类别比大类准得多：SQUAT 底下既有腿举也有负重深蹲，
# PULL_UP 底下其实是高位下拉。有子类别时优先用它。
SUB_CN = {
    "LEG_PRESS": "腿举", "WEIGHTED_SQUAT": "负重深蹲",
    "BARBELL_DEADLIFT": "杠铃硬拉", "BARBELL_HIP_THRUST_ON_FLOOR": "杠铃臀推",
    "WEIGHTED_STANDING_HIP_ABDUCTION": "站姿髋外展",
    "LAT_PULLDOWN": "高位下拉", "SEATED_CABLE_ROW": "坐姿绳索划船",
    "CABLE_CROSSOVER": "绳索夹胸", "CHEST_FLY": "悬吊夹胸",
    "DUMBBELL_KICKBACK": "哑铃臂后伸",
}
SUB_GROUP = {
    "LEG_PRESS": "腿", "WEIGHTED_SQUAT": "腿", "BARBELL_DEADLIFT": "腿",
    "BARBELL_HIP_THRUST_ON_FLOOR": "腿", "WEIGHTED_STANDING_HIP_ABDUCTION": "腿",
    "LAT_PULLDOWN": "拉", "SEATED_CABLE_ROW": "拉",
    "CABLE_CROSSOVER": "推", "CHEST_FLY": "推", "DUMBBELL_KICKBACK": "推",
}


# 这些大类底下混着不同器械，缺子类时名字不可信
AMBIG = {"SQUAT", "PULL_UP", "ROW", "HIP_RAISE"}


def _load_record_overrides():
    """与实验版共用 exercise_map.json 的 _records：按日期纠正单次记录。"""
    try:
        data = json.loads((Path(__file__).parent / "exercise_map.json").read_text())
        return {d: {k: v for k, v in m.items() if isinstance(v, str)}
                for d, m in (data.get("_records") or {}).items()}
    except Exception:
        return {}


RECORD_OVERRIDES = _load_record_overrides()


def parse_strength(acts):
    """从活动原始 JSON 里取力量训练的动作明细（手表按组记录的那部分）。"""
    ex, sess = [], []
    for a in acts:
        if a["type_key"] != "strength_training":
            continue
        raw = json.loads(a["raw"] or "{}")
        sets = raw.get("summarizedExerciseSets") or []
        d = (a["start_local"] or "")[:10]
        vol = sum((s.get("volume") or 0) for s in sets) / 1000
        unknown = vague = 0
        for s in sets:
            cat = s.get("category") or "UNKNOWN"
            sub = s.get("subCategory")
            n = s.get("sets") or 0
            raw_key = sub or cat
            fix = RECORD_OVERRIDES.get(d, {}).get(raw_key)
            if cat == "UNKNOWN":
                unknown += n
            elif not sub and cat in AMBIG and not fix:
                vague += n
            if fix:
                key, name, group = fix, EX_CN.get(fix, "未分类"), EX_GROUP.get(fix, "其他")
            else:
                key = raw_key
                name = SUB_CN.get(sub) or EX_CN.get(cat, "未分类")
                group = SUB_GROUP.get(sub) or EX_GROUP.get(cat, "其他")
            if config.LANG == "en":
                if key is None:
                    name, group = "Unclassified", "Other"
                else:
                    name = EXERCISE_EN.get(key, name)
                    group = common.GROUP_EN.get(group, group)
            ex.append(dict(
                date=d, key=key,
                name=name,
                group=group,
                sets=n, reps=s.get("reps") or 0,
                max_kg=round((s.get("maxWeight") or 0) / 1000, 1),
                volume_kg=round((s.get("volume") or 0) / 1000),
                duration_min=round((s.get("duration") or 0) / 60),
            ))
        sess.append(dict(
            date=d, duration_min=round((a["duration_s"] or 0) / 60),
            calories=a["calories"], avg_hr=a["avg_hr"], max_hr=a["max_hr"],
            load=round(a["training_load"] or 0, 1),
            sets=raw.get("totalSets") or sum(s.get("sets") or 0 for s in sets),
            reps=raw.get("totalReps") or sum(s.get("reps") or 0 for s in sets),
            volume_kg=round(vol), unknown_sets=unknown, vague_sets=vague,
        ))
    return ex, sess


def quality_label(s):
    """一次训练的记录质量：哪些组的动作名不可信。"""
    parts = []
    if s["unknown_sets"]:
        parts.append(f"未分类 {s['unknown_sets']} 组")
    if s["vague_sets"]:
        parts.append(f"待细分 {s['vague_sets']} 组")
    return "、".join(parts) or "完整"


# ---------------------------------------------------------------- 取数
def _avg(vals):
    v = [x for x in vals if isinstance(x, (int, float))]
    return sum(v) / len(v) if v else None


def load(days=90):
    conn = db.connect()
    db.init()
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    s, e = start, date.today().isoformat()

    daily = [dict(r) for r in conn.execute(
        "SELECT * FROM daily WHERE calendar_date BETWEEN ? AND ? ORDER BY calendar_date", (s, e))]
    sleep = [dict(r) for r in conn.execute(
        "SELECT * FROM sleep WHERE calendar_date BETWEEN ? AND ? ORDER BY calendar_date", (s, e))]
    hrv = [dict(r) for r in conn.execute(
        "SELECT * FROM hrv WHERE calendar_date BETWEEN ? AND ? ORDER BY calendar_date", (s, e))]
    weight = [dict(r) for r in conn.execute(
        "SELECT * FROM weight WHERE calendar_date BETWEEN ? AND ? ORDER BY calendar_date, ts_gmt", (s, e))]
    acts = [dict(r) for r in conn.execute(
        "SELECT * FROM activities WHERE substr(start_local,1,10) BETWEEN ? AND ? ORDER BY start_local", (s, e))]

    # 训练负荷、睡眠需求、力量明细：与实验版共用 common.py 的算法
    pmc = common.build_pmc(conn)
    pmc_tiles = common.build_pmc_tiles(conn, pmc)
    sleep_extras = common.build_sleep_extras(conn, acts, days=days)
    common.apply_exercise_overrides()
    sessions_rich, strength_history, strength_unknown = common.parse_strength(acts)
    equipment, equip_src = common.load_equipment(
        {x["equipment"] for s in sessions_rich for x in s["exercises"]})
    weeks = common.build_weeks(sessions_rich, equipment)
    image_files, image_map = common.load_exercise_images()
    conn.close()

    h = lambda sec: round((sec or 0) / 3600, 2)      # noqa: E731
    strength_ex, strength_sessions = parse_strength(acts)
    payload = {
        "range": {"start": s, "end": e, "days": days},
        "daily": [{
            "date": d["calendar_date"], "steps": d["steps"], "step_goal": d["step_goal"],
            "hr_resting": d["hr_resting"], "stress_avg": d["stress_avg"],
            "bb_min": d["bb_min"], "bb_max": d["bb_max"],
            "spo2_avg": d["spo2_avg"], "spo2_min": d["spo2_min"],
            "intensity_moderate": d["intensity_moderate"], "intensity_vigorous": d["intensity_vigorous"],
        } for d in daily],
        "sleep": [{
            "date": x["calendar_date"], "total_h": h(x["sleep_seconds"]),
            "deep_h": h(x["deep_seconds"]), "light_h": h(x["light_seconds"]),
            "rem_h": h(x["rem_seconds"]), "awake_h": h(x["awake_seconds"]),
            "score": x["score"], "qualifier": x["score_qualifier"],
        } for x in sleep],
        "hrv": [{"date": x["calendar_date"], "last_night_avg": x["last_night_avg"],
                 "status": x["status"]} for x in hrv],
        "weight": [{"date": w["calendar_date"], "kg": round(w["weight_g"] / 1000, 1)}
                   for w in weight if w["weight_g"]],
        "activities": [{
            "date": (a["start_local"] or "")[:10], "type_cn": _type_cn(a["type_key"]),
            "name": a["name"], "duration_min": round((a["duration_s"] or 0) / 60),
            "distance_km": round((a["distance_m"] or 0) / 1000, 2),
            "avg_hr": a["avg_hr"], "max_hr": a["max_hr"], "calories": a["calories"],
            "load": round(a["training_load"] or 0, 1), "te": round(a["aerobic_te"] or 0, 1),
        } for a in acts],
        "strength_sessions": strength_sessions,
        "strength_ex": strength_ex,
        "pmc": pmc,
        "pmc_tiles": pmc_tiles,
        "sleep_extras": sleep_extras,
        "training": {
            "sessions": sessions_rich,
            "history": strength_history,
            "unknown_sets": strength_unknown,
            "weeks": weeks,
            "equipment": equipment,
            "equipment_source": equip_src,
            "muscle_names": (MUSCLE_EN if config.LANG == "en"
                             else {k: v[0] for k, v in MUSCLES.items()}),
            "coverage_names": (common.COVERAGE_EN if config.LANG == "en"
                               else {g: g for g in COVERAGE_ORDER}),
            "coverage_order": COVERAGE_ORDER,
            "std": WEEKLY_STD,
            "equipment_names": (EQUIPMENT_EN if config.LANG == "en"
                                else {k: EQUIPMENT[k] for k in EQUIPMENT}),
            "equipment_icons": {k: EQUIPMENT_ICONS.get(k, DEFAULT_ICON) for k in EQUIPMENT},
            "exercise_images": image_files,
            "exercise_image": image_map,
        },
    }
    return payload


# ---------------------------------------------------------------- 建议规则
ICON = {"good": "✓", "warn": "!", "serious": "▲", "crit": "✕"}


def advice(p):
    """规则全部基于区间数据，每条带判断依据。"""
    D, S, H, A = p["daily"], p["sleep"], p["hrv"], p["activities"]
    out = []
    add = lambda lvl, title, text, basis: out.append(
        dict(level=lvl, icon=ICON[lvl], title=title, text=text, basis=basis))

    sleep_avg = _avg([x["total_h"] for x in S])
    score_avg = _avg([x["score"] for x in S])
    deep_pct = _avg([x["deep_h"] / x["total_h"] * 100 for x in S if x["total_h"]])
    rhr_avg = _avg([x["hr_resting"] for x in D])
    hrv_avg = _avg([x["last_night_avg"] for x in H])
    steps_avg = _avg([x["steps"] for x in D])
    stress_avg = _avg([x["stress_avg"] for x in D])
    spo2_min = min([x["spo2_min"] for x in D if x["spo2_min"] is not None], default=None)
    mod = sum(x["intensity_moderate"] or 0 for x in D)
    vig = sum(x["intensity_vigorous"] or 0 for x in D)
    vig_pct = vig / (mod + vig) * 100 if (mod + vig) else None

    # 训练节奏：补齐没有训练的周，否则断档会被平均掉
    weeks = {}
    w0 = date.fromisoformat(p["range"]["start"])
    w0 -= timedelta(days=w0.weekday())
    while w0 <= date.today():
        weeks[w0.isoformat()] = {"count": 0, "min": 0}
        w0 += timedelta(days=7)
    for a in A:
        d = date.fromisoformat(a["date"])
        k = (d - timedelta(days=d.weekday())).isoformat()
        w = weeks.setdefault(k, {"count": 0, "min": 0})
        w["count"] += 1
        w["min"] += a["duration_min"]
    wk_counts = [w["count"] for w in weeks.values()]
    sessions_avg = _avg(wk_counts)
    last_w = weeks[max(weeks)] if weeks else None
    prev_w = weeks[sorted(weeks)[-2]] if len(weeks) > 1 else None

    # 1 睡眠时长
    if sleep_avg and sleep_avg < 7:
        add("warn", "睡眠时长不够，先补时长再谈强度",
            f"每晚差 {(7 - sleep_avg) * 60:.0f} 分钟。连续缺觉时，同样的训练会让恢复成本明显变高——"
            "先把就寝时间往前挪 30 分钟，比加练更划算。",
            f"日均睡眠 {sleep_avg:.1f} 小时（{len(S)} 晚）")
    elif sleep_avg:
        add("good", "睡眠时长达标", "维持现在的作息节奏即可。",
            f"日均睡眠 {sleep_avg:.1f} 小时")

    # 2 深睡占比
    if deep_pct and deep_pct < 15:
        add("warn", "深睡占比偏低",
            "深睡是身体修复的主要阶段。试试：睡前 2 小时不进食、把卧室温度降一点、"
            "固定起床时间（比固定入睡时间更有效）。",
            f"深睡占睡眠时长 {deep_pct:.0f}%，参考区间 15–25%")

    # 3 睡眠评分
    if score_avg and score_avg < 70:
        add("warn", "睡眠评分整体偏低",
            "评分低通常不是单一原因，先看时长和深睡两项，再看睡前是否饮酒或高强度训练过晚。",
            f"平均评分 {score_avg:.0f}（0–100）")

    # 4 HRV 连续偏低
    low_streak, cur = 0, 0
    for x in H:
        cur = cur + 1 if x["status"] == "LOW" else 0
        low_streak = max(low_streak, cur)
    if low_streak >= 3:
        add("crit", "HRV 连续偏低，建议安排减量周",
            "HRV 长期低于基线，说明交感神经占优、恢复不足。这周把强度降到平时的六成，"
            "睡眠优先，不要用加练来「补」。",
            f"最长连续 {low_streak} 天 HRV 状态为 LOW（区间均值 {hrv_avg:.0f} ms）" if hrv_avg
            else f"最长连续 {low_streak} 天 HRV 低于基线")

    # 5 静息心率 vs 基线
    if rhr_avg and len(D) >= 20:
        base = _avg([x["hr_resting"] for x in D[:-14]])
        recent = _avg([x["hr_resting"] for x in D[-7:]])
        if base and recent and recent - base >= 5:
            add("serious", "静息心率比基线高",
                "先排除感冒、熬夜、酒精和睡前高强度训练。若同时伴随 HRV 走低，"
                "按恢复不足处理；若持续一周以上不回落，建议体检时提一句。",
                f"近 7 天 {recent:.0f} bpm，早前基线 {base:.0f} bpm")

    # 6 压力
    if stress_avg and stress_avg >= 45:
        add("warn", "日均压力偏高",
            "白天压力高会压缩夜间的恢复窗口。试着在午后安排 10 分钟慢走或呼吸练习，"
            "比晚上一次性放松更有效。",
            f"区间日均压力 {stress_avg:.0f}（0–100）")

    # 7 步数
    if steps_avg and steps_avg < 6000:
        add("warn", "日常活动量偏低",
            "非训练性的日常走动（NEAT）对代谢的影响常被低估。"
            "每天加两段 10 分钟步行，比偶尔一次长走更容易坚持。",
            f"日均 {steps_avg:,.0f} 步")
    elif steps_avg:
        add("good", "日常活动量不错", "保持即可，注意别用步数替代力量训练。",
            f"日均 {steps_avg:,.0f} 步")

    # 8 训练频率
    if sessions_avg is not None and sessions_avg < 2:
        add("warn", "训练频率偏低",
            "每周不到 2 次，肌肉刺激难以累积。哪怕每次只有 25 分钟，"
            "稳定在每周 3 次的效果也远好于攒到周末一次做完。",
            f"区间周均 {sessions_avg:.1f} 次训练")
    elif sessions_avg:
        add("good", "训练频率稳定", "维持每周的训练节奏，重点转向质量而不是次数。",
            f"区间周均 {sessions_avg:.1f} 次训练")

    # 9 周训练量突增
    if last_w and prev_w and prev_w["min"] and last_w["min"] > prev_w["min"] * 1.5:
        add("warn", "最近一周训练量涨得太快",
            "单周增幅超过 50%，受伤风险明显上升。下周回撤 20% 左右，让身体跟上。",
            f"本周 {last_w['min']} 分钟 vs 上周 {prev_w['min']} 分钟")

    # 10 强度结构
    if vig_pct is not None and vig_pct > 25:
        add("warn", "高强度占比偏高",
            "常见做法是 80% 低强度 + 20% 高强度。高强度的比例过高，"
            "容易挤占恢复窗口，也会让有氧基础变得不扎实。",
            f"剧烈强度分钟占全部强度分钟 {vig_pct:.0f}%")

    # 11 体重
    if len(p["weight"]) >= 2:
        w0, w1 = p["weight"][0], p["weight"][-1]
        d0, d1 = date.fromisoformat(w0["date"]), date.fromisoformat(w1["date"])
        span = max((d1 - d0).days, 1)
        rate = (w1["kg"] - w0["kg"]) / span * 7
        if abs(rate) > 1:
            add("warn", "体重变化偏快",
                "每周超过 1kg 的波动，通常不全是脂肪变化，水分和糖原占很大比重。"
                "建议固定同一时间（晨起空腹）称重，看 7 日均值而不是单点。",
                f"{w0['date']} {w0['kg']}kg → {w1['date']} {w1['kg']}kg，折合每周 {rate:+.1f}kg")

    # 12 血氧
    if spo2_min is not None and spo2_min < 88:
        add("crit", "夜间血氧出现低值",
            "单次低值可能是手腕位置或测量误差，但反复出现值得重视。"
            "如果同时有打鼾、白天嗜睡，建议就医做个睡眠监测。",
            f"区间最低夜间血氧 {spo2_min:.0f}%")

    if not out:
        add("good", "数据看起来平稳", "没有触发任何关注规则，继续保持。", "全部规则均未触发")

    order = {"crit": 0, "serious": 1, "warn": 2, "good": 3}
    out.sort(key=lambda x: order[x["level"]])
    return out


def advice_en(p):
    """English version of advice(); same rules and thresholds."""
    D, S, H, A = p["daily"], p["sleep"], p["hrv"], p["activities"]
    out = []
    add = lambda lvl, title, text, basis: out.append(
        dict(level=lvl, icon=ICON[lvl], title=title, text=text, basis=basis))

    sleep_avg = _avg([x["total_h"] for x in S])
    score_avg = _avg([x["score"] for x in S])
    deep_pct = _avg([x["deep_h"] / x["total_h"] * 100 for x in S if x["total_h"]])
    rhr_avg = _avg([x["hr_resting"] for x in D])
    hrv_avg = _avg([x["last_night_avg"] for x in H])
    steps_avg = _avg([x["steps"] for x in D])
    stress_avg = _avg([x["stress_avg"] for x in D])
    spo2_min = min([x["spo2_min"] for x in D if x["spo2_min"] is not None], default=None)
    mod = sum(x["intensity_moderate"] or 0 for x in D)
    vig = sum(x["intensity_vigorous"] or 0 for x in D)
    vig_pct = vig / (mod + vig) * 100 if (mod + vig) else None

    weeks = {}
    w0 = date.fromisoformat(p["range"]["start"])
    w0 -= timedelta(days=w0.weekday())
    while w0 <= date.today():
        weeks[w0.isoformat()] = {"count": 0, "min": 0}
        w0 += timedelta(days=7)
    for a in A:
        d = date.fromisoformat(a["date"])
        k = (d - timedelta(days=d.weekday())).isoformat()
        w = weeks.setdefault(k, {"count": 0, "min": 0})
        w["count"] += 1
        w["min"] += a["duration_min"]
    wk_counts = [w["count"] for w in weeks.values()]
    sessions_avg = _avg(wk_counts)
    last_w = weeks[max(weeks)] if weeks else None
    prev_w = weeks[sorted(weeks)[-2]] if len(weeks) > 1 else None

    if sleep_avg and sleep_avg < 7:
        add("warn", "Sleep is short — fix duration before intensity",
            f"You are {(7 - sleep_avg) * 60:.0f} min short per night. With chronic sleep debt, the same training costs more recovery. "
            "Move bedtime 30 minutes earlier; it beats adding another session.",
            f"Average sleep {sleep_avg:.1f} h ({len(S)} nights)")
    elif sleep_avg:
        add("good", "Sleep duration is on target", "Keep the current routine.",
            f"Average sleep {sleep_avg:.1f} h")

    if deep_pct and deep_pct < 15:
        add("warn", "Deep sleep is low",
            "Deep sleep is the main repair stage. Try no food 2 hours before bed, a cooler room, "
            "and a fixed wake time (more effective than a fixed bedtime).",
            f"Deep sleep {deep_pct:.0f}% of sleep (reference 15–25%)")

    if score_avg and score_avg < 70:
        add("warn", "Sleep score is low overall",
            "A low score rarely has one cause. Check duration and deep sleep first, then alcohol or late hard training.",
            f"Average score {score_avg:.0f} (0–100)")

    low_streak, cur = 0, 0
    for x in H:
        cur = cur + 1 if x["status"] == "LOW" else 0
        low_streak = max(low_streak, cur)
    if low_streak >= 3:
        add("crit", "HRV has been low for days — schedule a deload",
            "HRV below baseline means sympathetic dominance and incomplete recovery. Cut intensity to about 60% this week, "
            "prioritize sleep, and do not try to train your way out of it.",
            f"Longest LOW streak {low_streak} days (average {hrv_avg:.0f} ms)" if hrv_avg
            else f"Longest LOW streak {low_streak} days")

    if rhr_avg and len(D) >= 20:
        base = _avg([x["hr_resting"] for x in D[:-14]])
        recent = _avg([x["hr_resting"] for x in D[-7:]])
        if base and recent and recent - base >= 5:
            add("serious", "Resting heart rate is above baseline",
                "Rule out illness, poor sleep, alcohol and late hard training first. If HRV is also low, treat it as under-recovery; "
                "if it stays up for more than a week, mention it at a check-up.",
                f"Last 7 days {recent:.0f} bpm vs earlier baseline {base:.0f} bpm")

    if stress_avg and stress_avg >= 45:
        add("warn", "Daily stress is high",
            "High daytime stress narrows the recovery window at night. A 10-minute walk or breathing break in the afternoon "
            "works better than one big relaxation session at night.",
            f"Average stress {stress_avg:.0f} (0–100)")

    if steps_avg and steps_avg < 6000:
        add("warn", "Daily activity is low",
            "Non-exercise activity (NEAT) is easy to underestimate. Two 10-minute walks a day are easier to sustain than one long walk.",
            f"Average {steps_avg:,.0f} steps/day")
    elif steps_avg:
        add("good", "Daily activity looks good", "Keep it up, but do not let steps replace strength training.",
            f"Average {steps_avg:,.0f} steps/day")

    if sessions_avg is not None and sessions_avg < 2:
        add("warn", "Training frequency is low",
            "Under 2 sessions a week makes it hard to accumulate a stimulus. Even 25 minutes, "
            "3 times a week, beats one weekend session.",
            f"Average {sessions_avg:.1f} sessions/week")
    elif sessions_avg:
        add("good", "Training frequency is steady", "Keep the weekly rhythm and shift focus to quality.",
            f"Average {sessions_avg:.1f} sessions/week")

    if last_w and prev_w and prev_w["min"] and last_w["min"] > prev_w["min"] * 1.5:
        add("warn", "Training volume jumped too fast",
            "A single-week increase above 50% raises injury risk. Back off about 20% next week.",
            f"This week {last_w['min']} min vs last week {prev_w['min']} min")

    if vig_pct is not None and vig_pct > 25:
        add("warn", "Too much high-intensity work",
            "A common split is 80% easy / 20% hard. Too much hard work eats the recovery window and weakens the aerobic base.",
            f"Vigorous minutes {vig_pct:.0f}% of all intensity minutes")

    if len(p["weight"]) >= 2:
        w0, w1 = p["weight"][0], p["weight"][-1]
        d0, d1 = date.fromisoformat(w0["date"]), date.fromisoformat(w1["date"])
        span = max((d1 - d0).days, 1)
        rate = (w1["kg"] - w0["kg"]) / span * 7
        if abs(rate) > 1:
            add("warn", "Weight is moving fast",
                "Weekly swings above 1 kg are usually water and glycogen, not just fat. "
                "Weigh at the same time (morning, fasted) and look at the 7-day average.",
                f"{w0['date']} {w0['kg']}kg → {w1['date']} {w1['kg']}kg ({rate:+.1f} kg/week)")

    if spo2_min is not None and spo2_min < 88:
        add("crit", "Night-time SpO2 hit a low",
            "One low reading can be wrist position or measurement error, but repeated lows matter. "
            "If you also snore or feel sleepy during the day, ask about a sleep study.",
            f"Lowest night-time SpO2 {spo2_min:.0f}%")

    if not out:
        add("good", "Data looks stable", "No rule fired; keep doing what you are doing.", "All rules untriggered")

    order = {"crit": 0, "serious": 1, "warn": 2, "good": 3}
    out.sort(key=lambda x: order[x["level"]])
    return out


def render_advice(items):
    basis_label = "Basis: " if config.LANG == "en" else "依据："
    return "\n".join(
        f'<div class="adv"><div class="ico {i["level"]}">{i["icon"]}</div>'
        f'<div><h4>{i["title"]}</h4><p>{i["text"]}</p>'
        f'<div class="basis">{basis_label}{i["basis"]}</div></div></div>'
        for i in items)


# ---------------------------------------------------------------- 表格
def table_days(p):
    S = {x["date"]: x for x in p["sleep"]}
    by_day = {}
    for a in p["activities"]:
        by_day.setdefault(a["date"], []).append(a)
    rows = []
    for d in p["daily"][-16:][::-1]:
        s = S.get(d["date"], {})
        acts = by_day.get(d["date"], [])
        tr = "、".join(f"{a['type_cn']} {a['duration_min']}′" for a in acts) or "—"
        rows.append(
            f"<tr><td>{d['date']}</td><td>{d['steps'] or '—'}</td>"
            f"<td>{(s.get('total_h') or 0):.1f}h</td>"
            f"<td>{s.get('score') or '—'}</td>"
            f"<td>{(s.get('deep_h') or 0):.1f}h</td>"
            f"<td>{d['hr_resting'] or '—'}</td>"
            f"<td>{d['stress_avg'] if d['stress_avg'] is not None else '—'}</td>"
            f"<td>{d['bb_min'] if d['bb_min'] is not None else '—'}–{d['bb_max'] if d['bb_max'] is not None else '—'}</td>"
            f"<td>{tr}</td></tr>")
    head = ("<table><thead><tr><th>日期</th><th>步数</th><th>睡眠</th><th>评分</th>"
            "<th>深睡</th><th>静息心率</th><th>压力</th><th>Body Battery</th><th>训练</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")
    return head


def table_acts(p):
    rows = []
    for a in p["activities"][::-1]:
        rows.append(
            f"<tr><td>{a['date']}</td><td style='text-align:left'>{a['type_cn']}</td>"
            f"<td>{a['duration_min']}′</td>"
            f"<td>{a['distance_km'] if a['distance_km'] else '—'}</td>"
            f"<td>{a['avg_hr'] or '—'}</td><td>{a['max_hr'] or '—'}</td>"
            f"<td>{a['calories'] or '—'}</td><td>{a['load'] or '—'}</td>"
            f"<td>{a['te'] or '—'}</td></tr>")
    return ("<table><thead><tr><th>日期</th><th>类型</th><th>时长</th><th>距离 km</th>"
            "<th>平均心率</th><th>最高心率</th><th>卡路里</th><th>负荷</th><th>有氧效果</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def table_days_en(p):
    S = {x["date"]: x for x in p["sleep"]}
    by_day = {}
    for a in p["activities"]:
        by_day.setdefault(a["date"], []).append(a)
    rows = []
    for d in p["daily"][-16:][::-1]:
        s = S.get(d["date"], {})
        acts = by_day.get(d["date"], [])
        tr = ", ".join(f"{a['type_cn']} {a['duration_min']}′" for a in acts) or "—"
        rows.append(
            f"<tr><td>{d['date']}</td><td>{d['steps'] or '—'}</td>"
            f"<td>{(s.get('total_h') or 0):.1f}h</td>"
            f"<td>{s.get('score') or '—'}</td>"
            f"<td>{(s.get('deep_h') or 0):.1f}h</td>"
            f"<td>{d['hr_resting'] or '—'}</td>"
            f"<td>{d['stress_avg'] if d['stress_avg'] is not None else '—'}</td>"
            f"<td>{d['bb_min'] if d['bb_min'] is not None else '—'}–{d['bb_max'] if d['bb_max'] is not None else '—'}</td>"
            f"<td>{tr}</td></tr>")
    head = ("<table><thead><tr><th>Date</th><th>Steps</th><th>Sleep</th><th>Score</th>"
            "<th>Deep</th><th>Resting HR</th><th>Stress</th><th>Body Battery</th><th>Training</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")
    return head


def table_acts_en(p):
    rows = []
    for a in p["activities"][::-1]:
        rows.append(
            f"<tr><td>{a['date']}</td><td style='text-align:left'>{a['type_cn']}</td>"
            f"<td>{a['duration_min']}′</td>"
            f"<td>{a['distance_km'] if a['distance_km'] else '—'}</td>"
            f"<td>{a['avg_hr'] or '—'}</td><td>{a['max_hr'] or '—'}</td>"
            f"<td>{a['calories'] or '—'}</td><td>{a['load'] or '—'}</td>"
            f"<td>{a['te'] or '—'}</td></tr>")
    return ("<table><thead><tr><th>Date</th><th>Type</th><th>Duration</th><th>Distance km</th>"
            "<th>Avg HR</th><th>Max HR</th><th>Calories</th><th>Load</th><th>Aerobic TE</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def table_strength(p):
    ex = p["strength_ex"]
    if not ex:
        return '<p style="padding:16px;font-size:12.5px;color:#898781">区间内还没有力量训练动作记录。</p>'
    qual = {s["date"]: quality_label(s) for s in p["strength_sessions"]}
    by_date = {}
    for e in ex:
        by_date.setdefault(e["date"], []).append(e)
    rows = []
    for d in sorted(by_date, reverse=True):
        items = sorted(by_date[d], key=lambda x: (-x["sets"], x["name"]))
        n = len(items)
        q = qual.get(d, "—")
        qcls = "dim" if q != "完整" else ""
        for i, e in enumerate(items):
            date_cell = f'<td rowspan="{n}">{d}</td>' if i == 0 else ""
            q_cell = f'<td rowspan="{n}" class="{qcls}" style="text-align:left">{q}</td>' if i == 0 else ""
            rows.append(
                f"<tr>{date_cell}{q_cell}"
                f"<td style='text-align:left'>{e['name']}</td>"
                f"<td style='text-align:left' class='dim'>{e['group']}</td>"
                f"<td>{e['sets']}</td><td>{e['reps']}</td>"
                f"<td>{e['max_kg'] or '—'}</td><td>{e['volume_kg'] or '—'}</td></tr>")
    return ("<table><thead><tr><th style='width:110px'>日期</th>"
            "<th style='width:170px'>动作记录</th><th style='width:110px'>动作</th>"
            "<th style='width:70px'>部位</th><th>组数</th>"
            "<th>次数</th><th>最大重量 kg</th><th>容量 kg</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


# ---------------------------------------------------------------- 渲染
def build(days=90):
    p = load(days)
    r = p["range"]
    en = config.LANG == "en"
    html = TEMPLATE.read_text()
    if en:
        html = html.replace("<title>Garmin 数据看板</title>",
                            "<title>Garmin Training & Health Dashboard</title>")
    html = html.replace("%%CHARTJS%%", CHARTJS.read_text())
    html = html.replace("%%LANG%%", config.LANG)
    html = html.replace("%%EN_TEXT%%",
                        json.dumps(json.loads(EN_LOCALE.read_text()) if en else {},
                                   ensure_ascii=False))
    html = html.replace("%%DATA%%", json.dumps(p, ensure_ascii=False))
    html = html.replace("%%ADVICE%%", render_advice(advice_en(p) if en else advice(p)))
    html = html.replace("%%TABLE_DAYS%%", table_days_en(p) if en else table_days(p))
    html = html.replace("%%TABLE_ACTS%%", table_acts_en(p) if en else table_acts(p))
    html = html.replace("%%BODY_SVG%%", common.build_body_svg())
    if en:
        html = html.replace("%%RANGE_LINE%%",
                            f"Data range <b>{r['start']}</b> → <b>{r['end']}</b> ({r['days']} days)")
    else:
        html = html.replace("%%RANGE_LINE%%",
                            f"数据范围 <b>{r['start']}</b> → <b>{r['end']}</b>（{r['days']} 天）")
    html = html.replace("%%GENERATED%%", datetime.now().strftime("%Y-%m-%d %H:%M"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    print(f"[dashboard] {OUT}  {OUT.stat().st_size / 1024:.0f} KB")
    return OUT


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    build(ap.parse_args().days)
