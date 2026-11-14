#!/usr/bin/env python3
"""正式看板与实验版共用的数据计算。

目前包含：
- 训练负荷 PMC / ACWR
- 睡眠需求、作息对齐、睡眠评分分项
- 训练结束→入睡、前夜恢复→次日负荷的相关性

口径与实验版保持一致；正式看板与实验版都从这里取，避免两套算法漂移。
"""
import base64
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

from muscle_map import (
    COVERAGE_ORDER, DEFAULT_ICON, EQUIPMENT, EQUIPMENT_ICONS, EXERCISE_IMAGES,
    EXERCISES, MUSCLE_TO_SLUGS, SUGGESTIONS, UNKNOWN_EXERCISE, WEEKLY_STD,
    coverage_units, muscle_units,
)

HERE = Path(__file__).parent
EQUIP_FILE = HERE / "gym_equipment.json"
EXERCISE_FILE = HERE / "exercise_map.json"
BODY_FILE = HERE / "body_paths.json"
EXERCISE_IMG_DIR = HERE / "assets" / "exercises"
RECORD_OVERRIDES = {}


# ---------------------------------------------------------------- 小工具
def _d(s):
    return date.fromisoformat(s[:10])


def _monday(d):
    return d - timedelta(days=d.weekday())


def _round(v, n=1):
    return None if v is None else round(v, n)


def _avg(vals):
    v = [x for x in vals if isinstance(x, (int, float))]
    return sum(v) / len(v) if v else None


def _hhmm(minutes):
    if minutes is None:
        return None
    m = int(minutes) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _hhmm_from_shift(shifted):
    return _hhmm(shifted + 18 * 60)


def spearman(xs, ys):
    """秩相关；样本太少或全同值时返回 (None, n)。"""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 5:
        return None, n
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return (num / den if den else None), n


# ---------------------------------------------------------------- 训练负荷
def load_activities(conn, since="2020-01-01"):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM activities WHERE substr(start_local,1,10) >= ? ORDER BY start_local",
        (since,))]


def build_pmc(conn):
    """逐日负荷 → CTL(42d) / ATL(7d) / TSB / ACWR。

    负荷口径：Garmin 的 activityTrainingLoad，只可横向比较相对趋势，
    不能当作 Coggan TSS 的绝对值使用。
    """
    loads = {}
    for a in conn.execute(
            "SELECT start_local, training_load FROM activities "
            "WHERE substr(start_local,1,10) >= '2020-01-01'"):
        d = (a["start_local"] or "")[:10]
        if d:
            loads[d] = loads.get(d, 0.0) + (a["training_load"] or 0.0)

    start = date(2020, 1, 1)
    end = date.today()
    out = []
    ctl = atl = 0.0
    d = start
    while d <= end:
        key = d.isoformat()
        load = loads.get(key, 0.0)
        ctl += (load - ctl) / 42
        atl += (load - atl) / 7
        out.append(dict(date=key, load=round(load, 1),
                        ctl=round(ctl, 1), atl=round(atl, 1),
                        tsb=round(ctl - atl, 1)))
        d += timedelta(days=1)

    for i, x in enumerate(out):
        win = out[max(0, i - 27):i + 1]
        w7 = sum(y["load"] for y in win[-7:])
        w28 = sum(y["load"] for y in win)
        # 28 天里至少 8 个训练日才计算，否则稀疏数据会把比值推到 3–4
        active = sum(1 for y in win if y["load"] > 0)
        x["acwr"] = _round(w7 / (w28 / 4), 2) if (w28 > 0 and active >= 8) else None

    # 页面只画近年，CTL 仍从 2020 起算，保证数值正确
    return [x for x in out if x["date"] >= "2025-01-01"]


def build_pmc_tiles(conn, pmc):
    """训练负荷区顶部的小卡片。"""
    today = date.today().isoformat()
    last = [x for x in pmc if x["date"] <= today]
    cur = last[-1] if last else {}
    week_mon = _monday(date.today()).isoformat()
    wk = [dict(r) for r in conn.execute(
        "SELECT start_local, duration_s FROM activities "
        "WHERE substr(start_local,1,10) >= ?", (week_mon,))]
    return dict(
        ctl=cur.get("ctl"), atl=cur.get("atl"),
        tsb=cur.get("tsb"), acwr=cur.get("acwr"),
        week_sessions=len(wk),
        week_minutes=sum(round((a["duration_s"] or 0) / 60) for a in wk),
    )


# ---------------------------------------------------------------- 睡眠
def build_sleep_extras(conn, acts, days=90):
    """睡眠需求、评分分项、作息对齐与两组训练相关性。

    acts 传最近 90 天的活动（dict 行），用于相关性。
    """
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM sleep WHERE calendar_date BETWEEN ? AND ? ORDER BY calendar_date",
        (start, date.today().isoformat()))]
    hrv = {r["calendar_date"]: dict(r) for r in conn.execute(
        "SELECT * FROM hrv WHERE calendar_date BETWEEN ? AND ?",
        (start, date.today().isoformat()))}

    need, scores, align = [], [], []
    for r in rows:
        raw = json.loads(r["raw"] or "{}")
        sn = raw.get("sleepNeed") or {}
        ns = raw.get("nextSleepNeed") or {}
        al = raw.get("sleepAlignment") or {}
        sc = raw.get("sleepScores") or {}
        scores.append(dict(
            date=r["calendar_date"], score=r["score"], qualifier=r["score_qualifier"],
            total_h=round((r["sleep_seconds"] or 0) / 3600, 2),
            deep_pct=(sc.get("deepPercentage") or {}).get("value"),
            rem_pct=(sc.get("remPercentage") or {}).get("value"),
            light_pct=(sc.get("lightPercentage") or {}).get("value"),
            awake_count=r["awake_count"],
            duration_q=(sc.get("totalDuration") or {}).get("qualifierKey"),
            stress_q=(sc.get("stress") or {}).get("qualifierKey"),
            awake_q=(sc.get("awakeCount") or {}).get("qualifierKey"),
            restless_q=(sc.get("restlessness") or {}).get("qualifierKey"),
        ))
        if sn:
            need.append(dict(
                date=r["calendar_date"],
                baseline=round((sn.get("baseline") or 0) / 60, 1),
                actual=round((sn.get("actual") or 0) / 60, 1),
                feedback=sn.get("feedback"),
                train_adj=sn.get("trainingFeedback"),
                hrv_adj=sn.get("hrvAdjustment"),
                rec_start=_hhmm(sn.get("recommendedBedtimeStartMins")),
                rec_end=_hhmm(sn.get("recommendedBedtimeEndMins")),
                next_actual=round((ns.get("actual") or 0) / 60, 1) if ns else None,
                next_rec_start=_hhmm(ns.get("recommendedBedtimeStartMins")),
                next_rec_end=_hhmm(ns.get("recommendedBedtimeEndMins")),
            ))
        if al:
            align.append(dict(
                date=r["calendar_date"], status=al.get("status"),
                last_mid=_hhmm(al.get("lastSleepMidpointMins")),
                opt_mid=_hhmm(al.get("optimalSleepWindowMidpointMins")),
                last_mid_min=al.get("lastSleepMidpointMins"),
                opt_mid_min=al.get("optimalSleepWindowMidpointMins"),
            ))

    # 逐日睡觉/起床（用于散点）
    sleep_time = {}
    for r in rows:
        raw = json.loads(r["raw"] or "{}")
        sm, em = raw.get("sleepStartTimestampGMT"), raw.get("sleepEndTimestampGMT")
        if not (sm and em):
            continue
        sdt = datetime.fromtimestamp(sm / 1000)
        edt = datetime.fromtimestamp(em / 1000)
        bed = (sdt.hour * 60 + sdt.minute - 18 * 60) % 1440
        sleep_time[r["calendar_date"]] = dict(
            bed_min=bed, bed=_hhmm_from_shift(bed),
            wake=_hhmm_from_shift((edt.hour * 60 + edt.minute - 18 * 60) % 1440),
            score=r["score"], total_h=round((r["sleep_seconds"] or 0) / 3600, 2))

    # 散点 1：训练结束 → 当晚入睡
    late_pts = []
    for a in acts:
        d = (a["start_local"] or "")[:10]
        if not d or d < start:
            continue
        st = datetime.fromisoformat(a["start_local"])
        end = st + timedelta(seconds=a["duration_s"] or 0)
        nxt = (st.date() + timedelta(days=1)).isoformat()
        info = sleep_time.get(nxt)
        if not info:
            continue
        end_min = (end.hour * 60 + end.minute - 18 * 60) % 1440
        late_pts.append(dict(x=end_min, y=info["bed_min"], date=d,
                             label=f"{d} 训练结束 {end:%H:%M} → 入睡 {info['bed']}"))
    r_late, n_late = spearman([p["x"] for p in late_pts], [p["y"] for p in late_pts])

    # 散点 2：前夜恢复 → 次日训练负荷
    load_by_day = {}
    for a in acts:
        d = (a["start_local"] or "")[:10]
        load_by_day[d] = load_by_day.get(d, 0) + (a["training_load"] or 0)
    rec_pts, rec_hrv_pts = [], []
    for s in scores:
        nxt = (_d(s["date"]) + timedelta(days=1)).isoformat()
        if nxt not in load_by_day:
            continue
        if s["score"]:
            rec_pts.append(dict(x=s["score"], y=round(load_by_day[nxt], 1), date=s["date"],
                                label=f"{s['date']} 睡眠 {s['score']} 分 → 次日负荷 {load_by_day[nxt]:.0f}"))
        h = hrv.get(s["date"])
        if h and h["last_night_avg"]:
            rec_hrv_pts.append(dict(x=h["last_night_avg"], y=round(load_by_day[nxt], 1), date=s["date"],
                                    label=f"{s['date']} HRV {h['last_night_avg']} → 次日负荷 {load_by_day[nxt]:.0f}"))
    r_rec, n_rec = spearman([p["x"] for p in rec_pts], [p["y"] for p in rec_pts])
    r_hrv, n_hrv = spearman([p["x"] for p in rec_hrv_pts], [p["y"] for p in rec_hrv_pts])

    from collections import Counter
    status_count = Counter(a["status"] for a in align)
    return dict(need=need, scores=scores, align=align,
                correlations=dict(
                    late=dict(points=late_pts, r=_round(r_late, 2), n=n_late),
                    recovery=dict(points=rec_pts, r=_round(r_rec, 2), n=n_rec),
                    hrv_load=dict(points=rec_hrv_pts, r=_round(r_hrv, 2), n=n_hrv),
                ), status_count=dict(status_count))


# ---------------------------------------------------------------- 力量训练
def parse_strength(acts):
    """从活动原始 JSON 里取力量训练的动作明细，并算好肌群/覆盖贡献。"""
    sessions, history, unknown_total = [], {}, 0
    for a in acts:
        if a["type_key"] != "strength_training":
            continue
        raw = json.loads(a["raw"] or "{}")
        sets = raw.get("summarizedExerciseSets") or []
        d = (a["start_local"] or "")[:10]
        time_s = (a["start_local"] or "")[11:16]
        ex_list = []
        prim_sets, sec_sets = {}, {}
        cov = {}
        unknown = vague = 0
        volume = 0.0
        for s in sets:
            cat = s.get("category") or "UNKNOWN"
            sub = s.get("subCategory")
            n = s.get("sets") or 0
            if cat == "UNKNOWN":
                unknown += n
                ex_list.append(dict(key=None, name="未分类", sets=n,
                                    reps=s.get("reps") or 0, max_kg=0, volume_kg=0,
                                    est_1rm=None, equipment="bodyweight",
                                    primary=[], secondary=[]))
                continue
            fix = RECORD_OVERRIDES.get(d, {})
            overridden = (sub or cat) in fix
            if not sub and cat in {"SQUAT", "PULL_UP", "ROW", "HIP_RAISE"} and not overridden:
                vague += n
            key, ex = (sub, EXERCISES[sub]) if (sub and sub in EXERCISES) else (
                (cat, EXERCISES[cat]) if cat in EXERCISES else (None, UNKNOWN_EXERCISE))
            if overridden and fix[sub or cat] in EXERCISES:
                key = fix[sub or cat]
                ex = EXERCISES[key]
            reps = s.get("reps") or 0
            max_kg = round((s.get("maxWeight") or 0) / 1000, 1)
            vol_kg = round((s.get("volume") or 0) / 1000)
            volume += vol_kg
            per_set_reps = (reps / n) if n else 0
            est = round(max_kg * (1 + per_set_reps / 30), 1) if (max_kg and n) else None
            item = dict(key=key, name=ex["cn"], sets=n, reps=reps,
                        max_kg=max_kg, volume_kg=vol_kg, est_1rm=est,
                        equipment=ex["equipment"],
                        primary=ex["primary"], secondary=ex["secondary"])
            ex_list.append(item)
            for m, v in muscle_units(ex, n)[0]:
                prim_sets[m] = prim_sets.get(m, 0) + v
            for m, v in muscle_units(ex, n)[1]:
                sec_sets[m] = sec_sets.get(m, 0) + v
            for g, v in coverage_units(ex, n)[0]:
                cov[g] = cov.get(g, 0) + v
            for g, v in coverage_units(ex, n)[1]:
                cov[g] = cov.get(g, 0) + v
            if key:
                history.setdefault(key, []).append(dict(
                    date=d, sets=n, reps=reps, max_kg=max_kg,
                    volume_kg=vol_kg, est_1rm=est))

        unknown_total += unknown
        sessions.append(dict(
            date=d, time=time_s,
            duration_min=round((a["duration_s"] or 0) / 60),
            calories=a["calories"], avg_hr=a["avg_hr"], max_hr=a["max_hr"],
            load=round(a["training_load"] or 0, 1),
            total_sets=raw.get("totalSets") or sum(e["sets"] for e in ex_list),
            total_reps=raw.get("totalReps") or sum(e["reps"] for e in ex_list),
            volume_kg=round(volume), unknown_sets=unknown, vague_sets=vague,
            exercises=ex_list,
            primary_sets={k: round(v, 1) for k, v in prim_sets.items()},
            secondary_sets={k: round(v, 1) for k, v in sec_sets.items()},
            coverage={k: round(v, 1) for k, v in cov.items()},
        ))
    sessions.sort(key=lambda s: s["date"], reverse=True)
    return sessions, history, unknown_total


def apply_exercise_overrides():
    """读取 exercise_map.json：补充动作映射，并按日期纠正单次记录。"""
    if not EXERCISE_FILE.exists():
        return 0
    try:
        data = json.loads(EXERCISE_FILE.read_text())
    except Exception:
        return 0
    n = 0
    for key, val in data.items():
        if key.startswith("_") or not isinstance(val, dict):
            continue
        ex = EXERCISES.setdefault(key, dict(cn=key, primary=[], secondary=[], equipment="bodyweight"))
        for field in ("cn", "primary", "secondary", "equipment"):
            if field in val:
                ex[field] = val[field]
        n += 1
    RECORD_OVERRIDES.clear()
    RECORD_OVERRIDES.update(data.get("_records") or {})
    return n


def build_body_svg():
    """把 MuscleMap 的路径拼成一张前后视图 SVG，每条路径带 data-k。"""
    paths = json.loads(BODY_FILE.read_text())
    rev = {}
    for muscle, slugs in MUSCLE_TO_SLUGS.items():
        for s in slugs:
            rev.setdefault(s, []).append(muscle)
    parts = ['<svg class="bodysvg" viewBox="0 0 1448 1448" xmlns="http://www.w3.org/2000/svg" '
             'aria-label="人体肌肉示意图">']
    for p in paths:
        keys = " ".join(rev.get(p["slug"], []))
        attr = f' data-k="{keys}"' if keys else ""
        parts.append(f'<path d="{p["d"]}"{attr}/>')
    parts.append("</svg>")
    return "".join(parts)


def load_exercise_images():
    """把线稿读成 data URI，页面保持单文件。"""
    if not EXERCISE_IMG_DIR.exists():
        return {}, {}
    files, mapping = {}, {}
    for key, stem in EXERCISE_IMAGES.items():
        if stem in files:
            mapping[key] = stem
            continue
        f = EXERCISE_IMG_DIR / f"{stem}.png"
        if not f.exists():
            continue
        files[stem] = "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode()
        mapping[key] = stem
    return files, mapping


def load_equipment(observed):
    """健身房器械清单：优先读用户手改的 json，缺失时按已出现器械推断并落盘。"""
    if EQUIP_FILE.exists():
        try:
            data = json.loads(EQUIP_FILE.read_text())
            keys = [k for k in data.get("available", []) if k in EQUIPMENT]
            if keys:
                return keys, "配置文件"
        except Exception:
            pass
    keys = sorted({e["equipment"] for e in EXERCISES.values()} & set(observed)) or sorted(observed)
    EQUIP_FILE.write_text(json.dumps({
        "available": sorted(keys),
        "note": "按现有训练记录推断。可增删下面的器械 key，页面只从这里推荐。",
        "names": {k: EQUIPMENT[k] for k in sorted(keys)},
    }, ensure_ascii=False, indent=2) + "\n")
    return sorted(keys), "按记录推断"


def build_weeks(sessions, equipment):
    """最近 8 个自然周的部位覆盖与建议。"""
    if not sessions:
        return []
    this_mon = _monday(date.today())
    weeks = [this_mon - timedelta(days=7 * i) for i in range(8)]
    by_week = {}
    for s in sessions:
        k = _monday(_d(s["date"]))
        by_week.setdefault(k, []).append(s)

    out = []
    for idx, mon in enumerate(weeks):
        ss = by_week.get(mon, [])
        cov = {}
        for s in ss:
            for g, v in s["coverage"].items():
                cov[g] = cov.get(g, 0) + v
        cov = {g: round(cov.get(g, 0), 1) for g in COVERAGE_ORDER}
        if not ss and idx >= 2:
            continue
        label = "本周" if idx == 0 else ("上周" if idx == 1 else f"{mon.month}-{mon.day} 起")
        when = "本周" if idx == 0 else "该周"
        out.append(dict(
            week=mon.isoformat(), label=label,
            start=mon.isoformat(), end=(mon + timedelta(days=6)).isoformat(),
            sessions=len(ss),
            total_sets=sum(x["total_sets"] for x in ss),
            unknown_sets=sum(x["unknown_sets"] for x in ss),
            vague_sets=sum(x["vague_sets"] for x in ss),
            minutes=sum(x["duration_min"] for x in ss),
            volume_kg=sum(x["volume_kg"] for x in ss),
            coverage=cov,
            advice=weekly_advice(cov, ss, equipment, when=when),
        ))
    return out


def weekly_advice(cov, sessions, equipment, when="本周"):
    items = []
    done = {e["name"] for s in sessions for e in s["exercises"]}

    if not sessions:
        return [dict(level="info", title=f"{when}还没有力量训练记录",
                     text="这张周卡只统计手表记录到的力量训练；若已经练过但没记录，先在手表上按组记录。",
                     basis=f"{when} 0 次力量训练", suggestions=[])]

    for g in COVERAGE_ORDER:
        v = cov.get(g, 0)
        lo, hi = WEEKLY_STD[g]
        if v == 0:
            level, title = "miss", f"{when}没练{g}"
            text = f"参考区间每周 {lo}–{hi} 个有效组。"
        elif v < lo:
            level, title = "low", f"{g}训练量偏低"
            text = f"{when} {v:g} 组，低于参考下限 {lo} 组。"
        elif v > hi * 1.5:
            level, title = "high", f"{g}训练量明显偏高"
            text = f"{when} {v:g} 组，明显高于参考上限 {hi} 组；若恢复跟不上，下周先减 1–2 组。"
        else:
            continue

        sugg = []
        if level in ("miss", "low"):
            for s in SUGGESTIONS.get(g, []):
                if s["equipment"] not in equipment or s["name"] in done:
                    continue
                sugg.append(dict(name=s["name"], equipment=EQUIPMENT.get(s["equipment"], ""),
                                 why=s["why"]))
                if len(sugg) == 2:
                    break
            if sugg:
                text += " 可补：" + "、".join(f"{x['name']}（{x['equipment']}）" for x in sugg) + "。"
            else:
                text += " 现有器械清单里没有合适的补足动作，可在 gym_equipment.json 里补充器械。"
        items.append(dict(level=level, title=title, text=text,
                          basis=f"{when} {g} 有效组 {v:g}，参考 {lo}–{hi}",
                          suggestions=sugg))

    push = sum(cov.get(x, 0) for x in ("胸", "肩", "三头"))
    pull = sum(cov.get(x, 0) for x in ("背", "二头"))
    if push and pull:
        ratio = push / pull
        if ratio > 1.25:
            items.append(dict(level="info", title="推多于拉",
                              text=f"推类 {push:g} 组、拉类 {pull:g} 组，比值 {ratio:.2f}。"
                                   "长期推多于拉容易圆肩，下周可多补 1–2 组划船或面拉。",
                              basis=f"推拉比 {ratio:.2f}，参考 0.8–1.2", suggestions=[]))
        elif ratio < 0.8:
            items.append(dict(level="info", title="拉多于推",
                              text=f"推类 {push:g} 组、拉类 {pull:g} 组，比值 {ratio:.2f}。"
                                   "若没有体态问题，保持即可；想练胸可补卧推或夹胸。",
                              basis=f"推拉比 {ratio:.2f}，参考 0.8–1.2", suggestions=[]))

    upper = sum(cov.get(x, 0) for x in ("胸", "背", "肩", "二头", "三头", "前臂"))
    lower = sum(cov.get(x, 0) for x in ("臀", "腿前", "腿后", "小腿"))
    if upper and lower:
        r = upper / lower
        if r > 1.8:
            items.append(dict(level="info", title="上肢明显多于下肢",
                              text=f"上肢 {upper:g} 组、下肢 {lower:g} 组（{r:.1f}:1）。"
                                   "若目标是整体力量，建议把下肢提到每周至少 10 组。",
                              basis=f"上肢:下肢 = {r:.1f}:1", suggestions=[]))

    by_day = {}
    for s in sessions:
        by_day.setdefault(s["date"], {}).update(s["coverage"])
    dates = sorted(by_day)
    for a, b in zip(dates, dates[1:]):
        if (_d(b) - _d(a)).days != 1:
            continue
        for g in COVERAGE_ORDER:
            va, vb = by_day[a].get(g, 0), by_day[b].get(g, 0)
            if va >= 4 and vb >= 4:
                items.append(dict(level="info", title=f"{g}连续两天训练",
                                  text=f"{a} 与 {b} 都练了{g}（{va:g} 组 / {vb:g} 组）。"
                                       "同一部位间隔 48 小时恢复更充分；若状态正常可忽略。",
                                  basis=f"连续两天{g}均 ≥4 组", suggestions=[]))
                break

    if not any(x["level"] in ("miss", "low", "high") for x in items):
        items.insert(0, dict(level="ok", title=f"{when}部位覆盖完整",
                             text="各部位都落在参考区间内，下周优先加重量或保持组数即可。",
                             basis="全部覆盖部位均在参考区间", suggestions=[]))

    order = {"miss": 0, "low": 1, "high": 2, "info": 3, "ok": 4}
    items.sort(key=lambda x: order[x["level"]])
    return items
