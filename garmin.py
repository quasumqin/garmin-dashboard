#!/usr/bin/env python3
"""Garmin Connect 个人 API 同步与周报。

用法：
    python3 garmin.py sync --days 90 [--fit]
    python3 garmin.py report [--week]
    python3 garmin.py status
"""
import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import config
import db


# ---------------------------------------------------------------- 客户端
class ApiError(RuntimeError):
    pass


class Client:
    def __init__(self):
        self.token = None
        self._load_token()

    # -- token
    def _load_token(self):
        try:
            c = json.loads(config.TOKEN_CACHE.read_text())
            if c.get("base") == config.BASE and c.get("exp", 0) > time.time() + 60:
                self.token = c["token"]
                print(f"[token] 复用缓存，剩余 {int((c['exp']-time.time())/60)} 分钟")
        except Exception:
            pass

    def _fetch_token(self):
        key = config.KEY_FILE.read_text().strip()
        req = urllib.request.Request(
            f"{config.BASE}/personalapitoken-service/personal-api/personal-api-key/token",
            method="POST", headers={"Authorization": "ApiKey " + key})
        with urllib.request.urlopen(req, timeout=config.TIMEOUT) as r:
            tok = r.read().decode().strip()
        exp = time.time() + 23 * 3600          # 官方 24h，留 1h 余量
        try:
            import base64
            p = tok.split(".")[1]
            p += "=" * (-len(p) % 4)
            exp = json.loads(base64.urlsafe_b64decode(p)).get("exp", exp)
        except Exception:
            pass
        self.token = tok
        config.TOKEN_CACHE.write_text(json.dumps(
            {"token": tok, "exp": exp, "base": config.BASE}))
        config.TOKEN_CACHE.chmod(0o600)
        print(f"[token] 已换取，有效至 {datetime.fromtimestamp(exp):%Y-%m-%d %H:%M}")

    def _auth(self):
        if not self.token:
            self._fetch_token()
        return {"Authorization": "Bearer " + self.token}

    # -- request
    def get(self, path, retries=3):
        if path.startswith("/personalapitoken"):
            raise ValueError("token 端点请走 _fetch_token")
        url = config.BASE + path
        last = None
        for attempt in range(retries):
            t0 = time.time()
            try:
                req = urllib.request.Request(url, headers=self._auth())
                with urllib.request.urlopen(req, timeout=config.TIMEOUT) as r:
                    ms = int((time.time() - t0) * 1000)
                    body = r.read().decode()
                    return json.loads(body) if body.strip() else None, ms
            except urllib.error.HTTPError as e:
                ms = int((time.time() - t0) * 1000)
                body = e.read().decode()[:300]
                if e.code == 401 and attempt == 0:      # token 过期，重换一次
                    print("[token] 401，重新换取")
                    self._fetch_token()
                    continue
                if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                    wait = 2 ** attempt * 2
                    print(f"    {e.code} 退避 {wait}s")
                    time.sleep(wait)
                    last = f"{e.code} {body}"
                    continue
                raise ApiError(f"{e.code} {path} {body}") from None
            except Exception as e:                      # 网络抖动
                if attempt < retries - 1:
                    time.sleep(2 ** attempt * 2)
                    last = repr(e)
                    continue
                raise ApiError(f"{path} {e!r}") from None
        raise ApiError(f"{path} 重试耗尽 {last}")


# ---------------------------------------------------------------- 解析
def _g(d, *path, default=None):
    for k in path:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
        if d is None:
            return default
    return d


def parse_daily(records):
    out = []
    for r in records:
        out.append(dict(
            calendar_date=r.get("calendarDate"),
            steps=_g(r, "movement", "steps", "value"),
            step_goal=_g(r, "movement", "steps", "goal"),
            distance_m=_g(r, "movement", "steps", "distanceInMeters"),
            pushes=_g(r, "movement", "pushes", "value"),
            floors_up=_g(r, "movement", "floorsAscended", "value"),
            floors_down=_g(r, "movement", "floorsDescended", "value"),
            cal_resting=_g(r, "calories", "burnedResting"),
            cal_active=_g(r, "calories", "burnedActive"),
            cal_total=_g(r, "calories", "burnedTotal"),
            cal_consumed=_g(r, "calories", "consumedValue"),
            hr_min=_g(r, "heartRate", "minValue"),
            hr_max=_g(r, "heartRate", "maxValue"),
            hr_resting=_g(r, "heartRate", "restingValue"),
            intensity_moderate=_g(r, "intensityMinutes", "moderate"),
            intensity_vigorous=_g(r, "intensityMinutes", "vigorous"),
            intensity_goal=_g(r, "intensityMinutes", "goal"),
            stress_avg=_g(r, "stress", "avgLevel"),
            stress_max=_g(r, "stress", "maxLevel"),
            stress_high_min=_g(r, "stress", "highStressDurationInMillis"),
            bb_min=_g(r, "bodyBattery", "minValue"),
            bb_max=_g(r, "bodyBattery", "maxValue"),
            bb_charged=_g(r, "bodyBattery", "chargedValue"),
            bb_drained=_g(r, "bodyBattery", "drainedValue"),
            bb_latest=_g(r, "bodyBattery", "latestValue"),
            hydration_ml=_g(r, "hydration", "consumedInMl"),
            hydration_goal_ml=_g(r, "hydration", "goalInMl"),
            resp_avg=_g(r, "respiration", "avgValue"),
            resp_max=_g(r, "respiration", "maxValue"),
            resp_min=_g(r, "respiration", "minValue"),
            spo2_avg=_g(r, "pulseOx", "avgValue"),
            spo2_min=_g(r, "pulseOx", "minValue"),
            raw=json.dumps(r, ensure_ascii=False),
        ))
    return out


def _sleep_score(s):
    """官方把总分放在 sleepScores[overall] 里，不同账号结构略有差异。"""
    scores = s.get("sleepScores") or {}
    overall = scores.get("overall") or {}
    val = overall.get("value")
    if val is None:
        for v in scores.values():
            if isinstance(v, dict) and isinstance(v.get("value"), (int, float)):
                val = v["value"]
                break
    return val, overall.get("qualifierKey")


def parse_sleep(s):
    if not s:
        return None
    score, qual = _sleep_score(s)
    return dict(
        calendar_date=s.get("calendarDate"),
        sleep_seconds=s.get("sleepTimeSeconds"),
        nap_seconds=s.get("napTimeSeconds"),
        deep_seconds=s.get("deepSleepSeconds"),
        light_seconds=s.get("lightSleepSeconds"),
        rem_seconds=s.get("remSleepSeconds"),
        awake_seconds=s.get("awakeSleepSeconds"),
        awake_count=s.get("awakeCount"),
        start_local=_iso_local(s.get("sleepStartTimestampLocal")),
        end_local=_iso_local(s.get("sleepEndTimestampLocal")),
        hr_avg=s.get("avgHeartRate"),
        stress_avg=s.get("avgSleepStress"),
        spo2_avg=s.get("averageSpO2Value"),
        resp_avg=s.get("averageRespirationValue"),
        score=score,
        score_qualifier=qual,
        raw=json.dumps(s, ensure_ascii=False),
    )


def _iso_local(ms):
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")


def parse_weight(records):
    out = []
    for w in records:
        if not w.get("calendarDate"):
            continue
        out.append(dict(
            calendar_date=w["calendarDate"],
            weight_g=w.get("weight"),
            bmi=w.get("bmi"), body_fat=w.get("bodyFat"), body_water=w.get("bodyWater"),
            bone_mass=w.get("boneMass"), muscle_mass=w.get("muscleMass"),
            visceral_fat=w.get("visceralFat"), metabolic_age=w.get("metabolicAge"),
            source=w.get("sourceType"), ts_gmt=w.get("timestampGMT"),
        ))
    return out


def parse_hrv(records):
    out = []
    for h in records or []:
        out.append(dict(
            calendar_date=h.get("calendarDate"),
            weekly_avg=h.get("weeklyAvg"),
            last_night_avg=h.get("lastNightAvg"),
            last_night_high=h.get("lastNight5MinHigh"),
            status=h.get("status"),
            base_low_upper=_g(h, "baseline", "lowUpper"),
            base_balanced_low=_g(h, "baseline", "balancedLow"),
            base_balanced_upper=_g(h, "baseline", "balancedUpper"),
            feedback=h.get("feedbackPhrase"),
            raw=json.dumps(h, ensure_ascii=False),
        ))
    return out


def parse_activity(a):
    return dict(
        activity_id=a.get("activityId"),
        name=a.get("activityName"),
        type_key=_g(a, "activityType", "typeKey"),
        start_local=a.get("startTimeLocal"),
        start_gmt=a.get("startTimeGMT"),
        distance_m=a.get("distance"),
        duration_s=a.get("duration"),
        moving_s=a.get("movingDuration"),
        elapsed_s=a.get("elapsedDuration"),
        calories=a.get("calories"),
        avg_hr=a.get("averageHR"),
        max_hr=a.get("maxHR"),
        steps=a.get("steps"),
        aerobic_te=a.get("aerobicTrainingEffect"),
        anaerobic_te=a.get("anaerobicTrainingEffect"),
        training_load=a.get("activityTrainingLoad"),
        bb_diff=a.get("differenceBodyBattery"),
        moderate_min=a.get("moderateIntensityMinutes"),
        vigorous_min=a.get("vigorousIntensityMinutes"),
        raw=json.dumps(a, ensure_ascii=False),
    )


# ---------------------------------------------------------------- 同步
def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def sync(days=90, with_fit=False):
    api = Client()
    conn = db.connect()
    db.init()
    today = date.today()
    start = today - timedelta(days=days - 1)
    s, e = start.isoformat(), today.isoformat()
    print(f"[sync] 区间 {s} → {e}（{days} 天），端点 {config.BASE}")

    def run(label, path, parser, table, chunk=None):
        try:
            data, ms = api.get(path)
            rows = parser(data) if data else []
            n = db.upsert(conn, table, rows) if table else 0
            db.log_fetch(conn, path, 200, ms, n)
            print(f"  ✓ {label:<10} {n:>4} 行  {ms}ms")
            return data
        except ApiError as ex:
            db.log_fetch(conn, path, 0, 0, 0, str(ex)[:300])
            print(f"  ✗ {label:<10} {ex}")
            return None
        finally:
            time.sleep(config.THROTTLE_SEC)

    # 1) 每日汇总（一次拿全，90 天实测可一次返回）
    data = run("每日汇总", f"/usersummary-service/v2/dailysummaries?startDate={s}&endDate={e}",
               lambda d: parse_daily(d.get("data", [])), "daily")
    if data is None and days > 30:                       # 太长就按月切
        print("  · 退回按 30 天分段")
        cur = start
        while cur <= today:
            end = min(cur + timedelta(days=29), today)
            run(f"每日汇总{cur:%m-%d}",
                f"/usersummary-service/v2/dailysummaries?startDate={cur.isoformat()}&endDate={end.isoformat()}",
                lambda d: parse_daily(d.get("data", [])), "daily")
            cur = end + timedelta(days=1)

    # 2) 睡眠：只能按天取，慢（单请求约 3s），4 线程并发
    print("[sleep] 逐日拉取（4 线程）")
    n_sleep, n_fail = 0, 0
    lock = threading.Lock()

    def fetch_sleep(d):
        nonlocal n_sleep, n_fail
        try:
            data, ms = api.get(f"/sleep-service/sleep/dailySleep?date={d.isoformat()}")
            row = parse_sleep(data)
            with lock:
                if row:
                    db.upsert(conn, "sleep", [row])
                    n_sleep += 1
                db.log_fetch(conn, f"sleep?date={d}", 200, ms, 1 if row else 0)
        except ApiError as ex:
            with lock:
                n_fail += 1
                db.log_fetch(conn, f"sleep?date={d}", 0, 0, 0, str(ex)[:200])
        time.sleep(0.15)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch_sleep, list(daterange(start, today))))
    print(f"  ✓ 睡眠 {n_sleep} 天" + (f"（失败 {n_fail}）" if n_fail else ""))

    # 3) HRV / 体重（支持区间）
    run("HRV", f"/hrv-service/hrv/daily/{s}/{e}",
        lambda d: parse_hrv(d.get("hrvSummaries", []) if isinstance(d, dict) else d), "hrv")
    try:
        data, ms = api.get(f"/weight-service/weight/all/{s}/{e}")
        rows = parse_weight(data or [])
        n = db.upsert(conn, "weight", rows, pk=["calendar_date", "weight_g"])
        db.log_fetch(conn, "weight/all", 200, ms, n)
        print(f"  ✓ {'体重':<10} {n:>4} 行  {ms}ms")
    except ApiError as ex:
        print(f"  ✗ {'体重':<10} {ex}")

    # 4) 活动（分页）
    print("[activity] 分页拉取")
    offset, total = 0, 0
    while True:
        try:
            data, ms = api.get(
                f"/activitylist-service/activities/search/activities?start={offset}&limit=100")
        except ApiError as ex:
            print(f"  活动分页失败 {ex}")
            break
        if not data:
            break
        rows = [parse_activity(a) for a in data
                if (a.get("startTimeLocal") or "")[:10] >= s]
        db.upsert(conn, "activities", rows)
        total += len(rows)
        db.log_fetch(conn, f"activities start={offset}", 200, ms, len(rows))
        if len(data) < 100:
            break
        offset += 100
        time.sleep(config.THROTTLE_SEC)
    print(f"  ✓ 活动 {total} 条")

    # 5) 快照类
    for label, path, key in [
        ("健身年龄", f"/fitnessage-service/fitnessage/v2/{today.isoformat()}", "fitness_age"),
        ("心率区间", "/biometric-service/heartRateZones/v2", "hr_zones"),
        ("用户资料", "/userprofile-service/userprofile/settings", "profile"),
    ]:
        try:
            data, ms = api.get(path)
            db.set_meta(conn, key, json.dumps(data, ensure_ascii=False))
            db.log_fetch(conn, path, 200, ms, 1)
            print(f"  ✓ {label}")
        except ApiError as ex:
            print(f"  ✗ {label} {ex}")
        time.sleep(config.THROTTLE_SEC)

    # 6) 可选：FIT 归档
    if with_fit:
        sync_fit(conn, api)

    db.set_meta(conn, "last_sync", datetime.now().isoformat(timespec="seconds"))
    db.set_meta(conn, "last_sync_range", f"{s}~{e}")

    print("\n[结果]")
    for t in ("daily", "sleep", "weight", "hrv", "activities"):
        n = conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
        print(f"  {t:<11}{n:>5}")
    conn.close()


def backfill(since="2019-01-01", with_daily=False):
    """回填历史活动（只读，按页拉全）。日常同步仍用 sync。"""
    api = Client()
    conn = db.connect()
    db.init()
    print(f"[backfill] 活动自 {since} 起，端点 {config.BASE}")

    offset, total, years, stop = 0, 0, {}, False
    while not stop:
        try:
            data, ms = api.get(
                f"/activitylist-service/activities/search/activities?start={offset}&limit=100")
        except ApiError as ex:
            print(f"\n  分页失败 {ex}")
            break
        if not data:
            break
        rows = []
        for a in data:
            d = (a.get("startTimeLocal") or "")[:10]
            if d and d >= since:
                rows.append(parse_activity(a))
                years[d[:4]] = years.get(d[:4], 0) + 1
            else:
                stop = True                      # 活动按时间倒序，越过起点就收工
        if rows:
            db.upsert(conn, "activities", rows)
            total += len(rows)
        db.log_fetch(conn, f"backfill start={offset}", 200, ms, len(rows))
        print(f"\r  已拉 {total} 条", end="", flush=True)
        if stop or len(data) < 100:
            break
        offset += 100
        time.sleep(config.THROTTLE_SEC)
    print()

    if with_daily:                                # 可选：顺带补每日汇总（按月切）
        cur = date.fromisoformat(since)
        today = date.today()
        while cur <= today:
            end = min(cur + timedelta(days=29), today)
            try:
                data, ms = api.get(
                    f"/usersummary-service/v2/dailysummaries"
                    f"?startDate={cur.isoformat()}&endDate={end.isoformat()}")
                n = db.upsert(conn, "daily", parse_daily(data.get("data", []))) if data else 0
                db.log_fetch(conn, f"daily {cur}", 200, ms, n)
                print(f"\r  每日汇总 {cur} +{n} 天", end="", flush=True)
            except ApiError as ex:
                print(f"\n  每日汇总 {cur} 失败 {ex}")
            cur = end + timedelta(days=1)
            time.sleep(config.THROTTLE_SEC)
        print()

    db.set_meta(conn, "backfilled_from", since)
    print(f"[backfill] 本次写入 {total} 条活动")
    for y in sorted(years):
        print(f"  {y}  {years[y]:>4} 条")
    n = conn.execute("SELECT COUNT(*) c FROM activities").fetchone()["c"]
    r = conn.execute("SELECT MIN(substr(start_local,1,10)) a, MAX(substr(start_local,1,10)) b FROM activities").fetchone()
    print(f"  库内活动合计 {n} 条（{r['a'] or '—'} → {r['b'] or '—'}）")
    conn.close()


def sync_fit(conn, api):
    have = {p.stem.split("_")[0] for p in config.FIT_DIR.glob("*.fit")}
    ids = [r["activity_id"] for r in
           conn.execute("SELECT activity_id FROM activities ORDER BY start_local DESC")]
    todo = [i for i in ids if str(i) not in have]
    print(f"[fit] 需归档 {len(todo)} 个")
    for aid in todo:
        url = config.BASE + f"/download-service/files/activity/{aid}"
        try:
            req = urllib.request.Request(url, headers=api._auth())
            with urllib.request.urlopen(req, timeout=120) as r:
                blob = r.read()
            (config.FIT_DIR / f"{aid}.fit").write_bytes(blob)
            print(f"  ✓ {aid} {len(blob)//1024} KB")
        except Exception as ex:
            print(f"  ✗ {aid} {ex}")
        time.sleep(config.THROTTLE_SEC)


# ---------------------------------------------------------------- 月报/周报
def _fmt_hms(sec):
    if not sec:
        return "—"
    h, m = divmod(int(sec) // 60, 60)
    return f"{h}h{m:02d}m"


TYPE_CN = {
    "strength_training": "力量训练", "running": "跑步", "trail_running": "越野跑",
    "treadmill_running": "跑步机", "cycling": "骑行", "indoor_cycling": "室内骑行",
    "virtual_ride": "虚拟骑行",
    "walking": "步行", "hiking": "徒步", "swimming": "游泳", "lap_swimming": "泳池",
    "open_water_swimming": "公开水域", "indoor_cardio": "室内有氧", "yoga": "瑜伽",
    "pilates": "普拉提", "breathwork": "呼吸训练", "strength_training_hit": "力量训练",
    "elliptical_training": "椭圆机", "elliptical": "椭圆机",
    "stair_climbing": "爬楼", "rowing": "划船",
    "skiing": "滑雪", "snowboarding": "单板", "golf": "高尔夫", "tennis": "网球",
    "other": "其他",
}


def _type_cn(key):
    return TYPE_CN.get(key, key or "—")


def _activities_by_day(conn, start, end):
    idx = {}
    for r in conn.execute(
            "SELECT * FROM activities WHERE substr(start_local,1,10) BETWEEN ? AND ? "
            "ORDER BY start_local", (start, end)):
        idx.setdefault(r["start_local"][:10], []).append(dict(r))
    return idx


def report(week=True):
    conn = db.connect()
    db.init()
    today = date.today()
    days = 7 if week else 30
    start = today - timedelta(days=days - 1)
    s, e = start.isoformat(), today.isoformat()

    daily = {r["calendar_date"]: dict(r) for r in conn.execute(
        "SELECT * FROM daily WHERE calendar_date BETWEEN ? AND ?", (s, e))}
    sleep = {r["calendar_date"]: dict(r) for r in conn.execute(
        "SELECT * FROM sleep WHERE calendar_date BETWEEN ? AND ?", (s, e))}
    hrv = {r["calendar_date"]: dict(r) for r in conn.execute(
        "SELECT * FROM hrv WHERE calendar_date BETWEEN ? AND ?", (s, e))}
    acts = _activities_by_day(conn, s, e)

    if not daily and not sleep:
        print("库里没有这段数据，先跑 sync")
        return

    lines = []
    lines.append(f"# Garmin 周报（{s} ~ {e}）\n")
    lines.append("> 数据来自 Garmin Connect 个人 API，只读同步。\n")

    lines.append("## 逐日\n")
    lines.append("| 日期 | 步数 | 睡眠 | 静息心率 | 压力 | Body Battery | 训练 |")
    lines.append("|---|---|---|---|---|---|---|")
    for d in daterange(start, today):
        k = d.isoformat()
        dl, sl = daily.get(k, {}), sleep.get(k, {})
        steps = f"{dl.get('steps'):,}" if dl.get("steps") is not None else "—"
        st = _fmt_hms(sl.get("sleep_seconds"))
        rhr = dl.get("hr_resting") if dl.get("hr_resting") else "—"
        stress = dl.get("stress_avg") if dl.get("stress_avg") is not None else "—"
        bb = (f"{dl.get('bb_min')}–{dl.get('bb_max')}"
              if dl.get("bb_min") is not None else "—")
        tr = "; ".join(f"{_type_cn(a['type_key'])} {int((a['duration_s'] or 0)//60)}min"
                       for a in acts.get(k, [])) or "—"
        lines.append(f"| {k[5:]} | {steps} | {st} | {rhr} | {stress} | {bb} | {tr} |")

    # 汇总
    def avg(vals):
        vals = [v for v in vals if isinstance(v, (int, float))]
        return sum(vals) / len(vals) if vals else None

    steps_avg = avg([v.get("steps") for v in daily.values()])
    sleep_avg = avg([v.get("sleep_seconds") for v in sleep.values()])
    rhr_avg = avg([v.get("hr_resting") for v in daily.values()])
    hrv_avg = avg([v.get("last_night_avg") for v in hrv.values()])
    n_act = sum(len(v) for v in acts.values())
    act_sec = sum((a.get("duration_s") or 0) for v in acts.values() for a in v)

    lines.append("\n## 本期汇总\n")
    lines.append(f"- 日均步数：{f'{steps_avg:,.0f}' if steps_avg else '—'}")
    lines.append(f"- 日均睡眠：{_fmt_hms(sleep_avg)}")
    lines.append(f"- 平均静息心率：{f'{rhr_avg:.0f}' if rhr_avg else '—'}")
    lines.append(f"- 平均夜间 HRV：{f'{hrv_avg:.0f}' if hrv_avg else '—'}")
    lines.append(f"- 训练：{n_act} 次，累计 {_fmt_hms(act_sec)}")

    # 上周对比
    p_start = start - timedelta(days=days)
    p_end = start - timedelta(days=1)
    p_steps = avg([r["steps"] for r in conn.execute(
        "SELECT steps FROM daily WHERE calendar_date BETWEEN ? AND ?",
        (p_start.isoformat(), p_end.isoformat()))])
    if p_steps and steps_avg:
        delta = (steps_avg - p_steps) / p_steps * 100
        lines.append(f"- 步数环比上周：{delta:+.1f}%")

    # 关注项
    flags = []
    short = [k for k, v in sorted(sleep.items())
             if v.get("sleep_seconds") and v["sleep_seconds"] < 6 * 3600]
    for i in range(len(short) - 1):
        if (date.fromisoformat(short[i + 1]) - date.fromisoformat(short[i])).days == 1:
            flags.append(f"{short[i]} 与 {short[i+1]} 连续两晚睡眠不足 6 小时")
            break
    if sleep_avg and sleep_avg < 7 * 3600:
        flags.append(f"本期日均睡眠 {_fmt_hms(sleep_avg)}，低于 7 小时")
    if p_steps and steps_avg and steps_avg > p_steps * 1.5:
        flags.append(f"步数较上周增 {((steps_avg-p_steps)/p_steps*100):.0f}%，注意别一上来就加量")
    low_hrv = [k for k, v in hrv.items() if v.get("status") == "LOW"]
    if len(low_hrv) >= 3:
        flags.append(f"HRV 偏低 {len(low_hrv)} 天（{'、'.join(sorted(low_hrv)[-3:])}…），恢复不充分")

    lines.append("\n## 关注\n")
    lines.extend([f"- {f}" for f in flags] or ["- 无异常"])

    lines.append(f"\n> 今日（{today.isoformat()}）数据不完整，统计口径截至同步时刻。")
    missing = [d.isoformat() for d in daterange(start, today) if d.isoformat() not in daily]
    if missing:
        lines.append(f"\n> 缺数据：{'、'.join(missing)}（可能是没戴表或未同步）")

    text = "\n".join(lines) + "\n"
    out = config.REPORT_DIR / f"{'周报' if week else '月报'}-{today.isoformat()}.md"
    out.write_text(text)
    print(text)
    print(f"[写入] {out}")
    conn.close()


# ---------------------------------------------------------------- 状态
def status():
    conn = db.connect()
    db.init()
    print(f"端点：{config.BASE}")
    print(f"库：{config.DB_PATH}")
    for t in ("daily", "sleep", "weight", "hrv", "activities"):
        r = conn.execute(f"SELECT COUNT(*) c, MIN(calendar_date) a, MAX(calendar_date) b FROM {t}"
                         ).fetchone() if t != "activities" else None
        if t == "activities":
            r = conn.execute("SELECT COUNT(*) c, MIN(start_local) a, MAX(start_local) b FROM activities").fetchone()
        print(f"  {t:<11}{r['c']:>5}  {r['a'] or '—'} → {r['b'] or '—'}")
    print(f"最后同步：{db.get_meta(conn, 'last_sync', '从未')}  区间 {db.get_meta(conn, 'last_sync_range', '—')}")
    errs = conn.execute("SELECT COUNT(*) c FROM fetch_log WHERE status=0 OR status>=400").fetchone()["c"]
    print(f"失败请求（累计）：{errs}")
    conn.close()


def main():
    ap = argparse.ArgumentParser(description="Garmin Connect 个人 API 工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_sync = sub.add_parser("sync", help="拉取数据入库")
    p_sync.add_argument("--days", type=int, default=90)
    p_sync.add_argument("--fit", action="store_true", help="同时归档 FIT 原始文件")
    p_rep = sub.add_parser("report", help="生成周报/月报")
    p_rep.add_argument("--week", action="store_true", default=True)
    p_rep.add_argument("--month", action="store_true")
    p_dash = sub.add_parser("dashboard", help="生成 HTML 看板")
    p_dash.add_argument("--days", type=int, default=90)
    p_bf = sub.add_parser("backfill", help="回填历史活动（不含睡眠等逐日数据）")
    p_bf.add_argument("--since", default="2019-01-01")
    p_bf.add_argument("--daily", action="store_true", help="顺带补每日汇总（较慢）")
    sub.add_parser("status", help="查看库状态")

    args = ap.parse_args()
    if args.cmd == "sync":
        sync(args.days, args.fit)
    elif args.cmd == "report":
        report(week=not args.month)
    elif args.cmd == "dashboard":
        import dashboard
        dashboard.build(args.days)
    elif args.cmd == "backfill":
        backfill(args.since, args.daily)
    else:
        status()


if __name__ == "__main__":
    try:
        main()
    except ApiError as e:
        print(f"\n[错误] {e}", file=sys.stderr)
        sys.exit(1)
