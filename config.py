#!/usr/bin/env python3
"""路径、端点与凭据配置。"""
import locale
import os
from pathlib import Path


def _detect_lang():
    v = os.environ.get("GARMIN_LANG", "").lower()
    if v.startswith("en"):
        return "en"
    if v.startswith("zh"):
        return "zh"
    try:
        loc = locale.getlocale()[0] or os.environ.get("LANG", "")
    except Exception:
        loc = os.environ.get("LANG", "")
    return "en" if loc.lower().startswith("en") else "zh"


LANG = _detect_lang()

ROOT = Path(__file__).resolve().parent
# 数据目录默认在包内；分发时可用 GARMIN_HOME 指到别处
HOME = Path(os.environ.get("GARMIN_HOME", ROOT))
DATA_DIR = HOME / "data"
FIT_DIR = HOME / "fit"
REPORT_DIR = HOME / "reports"
DB_PATH = DATA_DIR / "garmin.db"

# 国际区 .com / 中国区 .cn —— 密钥与端点必须同区，否则 404
REGION = os.environ.get("GARMIN_REGION", "com").lower()
if REGION not in ("com", "cn"):
    REGION = "com"

# 密钥与 token 都放在仓库之外，避免误入库；可用环境变量覆盖
KEY_FILE = Path(os.environ.get(
    "GARMIN_KEY_FILE",
    Path.home() / ".config" / "garmin" / f"personal_api_key.{REGION}.txt"))
TOKEN_CACHE = Path(os.environ.get(
    "GARMIN_TOKEN_CACHE",
    Path.home() / ".config" / "garmin" / "token_cache.json"))
KEY_PAGE = f"https://connect.garmin.{REGION}/app/settings/personalApiToken"
BASE = f"https://personal.connectapi.garmin.{REGION}"

# 节流：实测串行 0.35s 无异常
THROTTLE_SEC = 0.35
TIMEOUT = 60

for d in (DATA_DIR, FIT_DIR, REPORT_DIR):
    d.mkdir(parents=True, exist_ok=True)
