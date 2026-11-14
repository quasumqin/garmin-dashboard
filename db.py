#!/usr/bin/env python3
"""SQLite schema 与通用 upsert。"""
import json
import sqlite3
from datetime import datetime

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily (
    calendar_date      TEXT PRIMARY KEY,
    steps              INTEGER,
    step_goal          INTEGER,
    distance_m         REAL,
    pushes             INTEGER,
    floors_up          INTEGER,
    floors_down        INTEGER,
    cal_resting        INTEGER,
    cal_active         INTEGER,
    cal_total          INTEGER,
    cal_consumed       INTEGER,
    hr_min             INTEGER,
    hr_max             INTEGER,
    hr_resting         INTEGER,
    intensity_moderate INTEGER,
    intensity_vigorous INTEGER,
    intensity_goal     INTEGER,
    stress_avg         INTEGER,
    stress_max         INTEGER,
    stress_high_min    INTEGER,
    bb_min             INTEGER,
    bb_max             INTEGER,
    bb_charged         INTEGER,
    bb_drained         INTEGER,
    bb_latest          INTEGER,
    hydration_ml       INTEGER,
    hydration_goal_ml  INTEGER,
    resp_avg           REAL,
    resp_max           REAL,
    resp_min           REAL,
    spo2_avg           REAL,
    spo2_min           REAL,
    raw                TEXT,
    synced_at          TEXT
);

CREATE TABLE IF NOT EXISTS sleep (
    calendar_date   TEXT PRIMARY KEY,
    sleep_seconds   INTEGER,
    nap_seconds     INTEGER,
    deep_seconds    INTEGER,
    light_seconds   INTEGER,
    rem_seconds     INTEGER,
    awake_seconds   INTEGER,
    awake_count     INTEGER,
    start_local     TEXT,
    end_local       TEXT,
    hr_avg          INTEGER,
    stress_avg      INTEGER,
    spo2_avg        REAL,
    resp_avg        REAL,
    score           INTEGER,
    score_qualifier TEXT,
    raw             TEXT,
    synced_at       TEXT
);

CREATE TABLE IF NOT EXISTS weight (
    calendar_date TEXT,
    weight_g      REAL,
    bmi           REAL,
    body_fat      REAL,
    body_water    REAL,
    bone_mass     REAL,
    muscle_mass   REAL,
    visceral_fat  REAL,
    metabolic_age REAL,
    source        TEXT,
    ts_gmt        INTEGER,
    synced_at     TEXT,
    PRIMARY KEY (calendar_date, weight_g)
);

CREATE TABLE IF NOT EXISTS hrv (
    calendar_date      TEXT PRIMARY KEY,
    weekly_avg         INTEGER,
    last_night_avg     INTEGER,
    last_night_high    INTEGER,
    status             TEXT,
    base_low_upper     INTEGER,
    base_balanced_low  INTEGER,
    base_balanced_upper INTEGER,
    feedback           TEXT,
    raw                TEXT,
    synced_at          TEXT
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id    INTEGER PRIMARY KEY,
    name           TEXT,
    type_key       TEXT,
    start_local    TEXT,
    start_gmt      TEXT,
    distance_m     REAL,
    duration_s     REAL,
    moving_s       REAL,
    elapsed_s      REAL,
    calories       INTEGER,
    avg_hr         INTEGER,
    max_hr         INTEGER,
    steps          INTEGER,
    aerobic_te     REAL,
    anaerobic_te   REAL,
    training_load  REAL,
    bb_diff        INTEGER,
    moderate_min   INTEGER,
    vigorous_min   INTEGER,
    raw            TEXT,
    synced_at      TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS fetch_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint   TEXT,
    status     INTEGER,
    ms         INTEGER,
    rows       INTEGER,
    error      TEXT,
    created_at TEXT
);
"""


def connect():
    # 睡眠并发拉取时写库在同一把锁内，允许跨线程共享连接
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init():
    with connect() as conn:
        conn.executescript(SCHEMA)


def upsert(conn, table, rows, pk=None):
    """rows 为 dict 列表；pk 默认取第一列，可传复合主键列表。"""
    if not rows:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    rows = [dict(r) for r in rows]
    for r in rows:
        r["synced_at"] = now
        for k, v in r.items():                    # 兜底：嵌套结构存成 JSON
            if isinstance(v, (dict, list)):
                r[k] = json.dumps(v, ensure_ascii=False)
    cols = [k for k in rows[0].keys()]
    pk = pk or [cols[0]]
    placeholders = ",".join("?" * len(cols))
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in pk)
    sql = (f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) "
           f"ON CONFLICT({','.join(pk)}) DO UPDATE SET {updates}")
    conn.executemany(sql, [[r.get(c) for c in cols] for r in rows])
    conn.commit()
    return len(rows)


def log_fetch(conn, endpoint, status, ms, rows, error=None):
    conn.execute(
        "INSERT INTO fetch_log (endpoint,status,ms,rows,error,created_at) VALUES (?,?,?,?,?,?)",
        (endpoint, status, ms, rows, error, datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta (key,value,updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, str(value), datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default
