#!/usr/bin/env python3
"""Garmin dashboard first-run wizard / 首次使用向导.

    python3 setup.py

Guides you through: region → Personal API Key → token check → sync → dashboard.
The key is stored only in ~/.config/garmin/ and never printed.
"""
import argparse
import getpass
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def ask(prompt, default=None):
    tip = f" (default {default})" if default else ""
    v = input(f"{prompt}{tip}: ").strip()
    return v or (default or "")


def yes(prompt, default=True):
    tip = "Y/n" if default else "y/N"
    v = input(f"{prompt} [{tip}]: ").strip().lower()
    if not v:
        return default
    return v in ("y", "yes", "是")


def main():
    ap = argparse.ArgumentParser(description="Garmin dashboard first-run wizard")
    ap.add_argument("--region", choices=["com", "cn"], help="com = international, cn = China")
    ap.add_argument("--key-file", help="path to an existing Personal API Key file")
    ap.add_argument("--days", type=int, default=90, help="initial sync days (default 90)")
    ap.add_argument("--no-sync", action="store_true", help="skip sync, build from the existing DB")
    ap.add_argument("--no-open", action="store_true", help="do not open a browser")
    ap.add_argument("--yes", action="store_true", help="use defaults without prompting (testing)")
    args = ap.parse_args()

    region = args.region
    if not region:
        if args.yes:
            region = "com"
        else:
            print("Which Garmin Connect region is your account?")
            print("  1) International (connect.garmin.com)")
            print("  2) China (connect.garmin.cn)")
            region = "cn" if ask("Choose 1 or 2", "1") == "2" else "com"

    os.environ["GARMIN_REGION"] = region
    import config  # noqa: E402  (must follow GARMIN_REGION)
    import garmin  # noqa: E402

    EN = config.LANG == "en"

    def L(zh, en):
        return en if EN else zh

    print("=" * 62)
    print(L("  Garmin 训练与健康看板 · 首次使用向导",
            "  Garmin Training & Health Dashboard · First-run setup"))
    print("=" * 62)
    print(L("数据只保存在本机 SQLite，不上传任何服务器。",
            "Data stays in a local SQLite file; nothing is uploaded."))
    print()

    print(f"{L('区域', 'Region')}: {region} ({config.BASE})")
    print(f"{L('数据目录', 'Data directory')}: {config.DATA_DIR}")
    print(f"{L('报告目录', 'Report directory')}: {config.REPORT_DIR}\n")

    key_file = Path(args.key_file) if args.key_file else config.KEY_FILE
    print("-" * 62)
    print(L("第 1 步：申请 Personal API Key", "Step 1: Get a Personal API Key"))
    print("-" * 62)
    print(L("个人 API 不需要企业申请、没有人工审核，在 Garmin Connect 设置页自助生成：",
            "The Personal API is self-service: no company application, no manual review."))
    print(f"  {config.KEY_PAGE}")
    print(L("登录后打开该页，生成/复制 Personal API Key。",
            "Sign in, open that page, generate/copy the Personal API Key."))
    print(L("注意：Key 与区域绑定，国际区配 .com、中国区配 .cn，不能混用。\n",
            "The key is region-bound: .com for international, .cn for China.\n"))

    if not args.no_open:
        try:
            webbrowser.open(config.KEY_PAGE)
        except Exception:
            pass

    key_exists = key_file.exists()
    if key_exists:
        reuse = True if args.yes else yes(
            L(f"已存在密钥 {key_file}，继续用它吗？", f"Key exists at {key_file}; reuse it?"), True)
        if not reuse:
            print(L("将重新输入密钥。", "Enter a new key."))
            key_exists = False

    if not key_exists:
        key = getpass.getpass(L("粘贴 Personal API Key（输入不回显）: ",
                                "Paste the Personal API Key (hidden): ")).strip()
        if not key:
            print(L("没有输入密钥，退出。", "No key entered; exiting."))
            return 2
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(key)
        try:
            os.chmod(key_file, 0o600)
        except Exception:
            pass
        print(L(f"密钥已保存：{key_file}（仅本机可读）",
                f"Key saved to {key_file} (local only)"))

    config.KEY_FILE = key_file

    print(L("\n第 2 步：验证密钥", "\nStep 2: Validate the key"))
    try:
        client = garmin.Client()
        client._fetch_token()
    except Exception as e:
        print(L(f"\n验证失败：{type(e).__name__}: {e}",
                f"\nValidation failed: {type(e).__name__}: {e}"))
        print(L("\n常见原因：", "\nCommon causes:"))
        print(L("  404 / Key does not exist → 区域配错，试另一个区（--region cn / com）",
                "  404 / Key does not exist → wrong region; try --region cn / com"))
        print(L("  401 → Key 复制不全或已失效，回设置页重新生成",
                "  401 → key incomplete or expired; generate a new one"))
        print(L(f"  网络 → 本机能否访问 {config.BASE}",
                f"  Network → can this machine reach {config.BASE}?"))
        return 1
    print(L("密钥有效。", "Key is valid."))

    if args.no_sync:
        print(L("\n跳过拉取数据（--no-sync）。", "\nSkipping sync (--no-sync)."))
    else:
        days = args.days if args.yes else int(ask(
            L("第 3 步：首次拉取多少天", "Step 3: initial sync days"), str(args.days)))
        print(L(f"\n第 3 步：拉取最近 {days} 天数据（约 1–3 分钟）",
                f"\nStep 3: syncing the last {days} days (about 1–3 min)"))
        r = subprocess.run([sys.executable, "garmin.py", "sync", "--days", str(days)], cwd=ROOT)
        if r.returncode != 0:
            print(L("同步失败，请把上面的报错发给我。",
                    "Sync failed; send me the error above."))
            return r.returncode

    print(L("\n第 4 步：生成看板", "\nStep 4: build the dashboard"))
    r = subprocess.run([sys.executable, "garmin.py", "dashboard"], cwd=ROOT)
    if r.returncode != 0:
        return r.returncode

    out = config.REPORT_DIR / "dashboard.html"
    print("\n" + "=" * 62)
    print(L(f"完成：{out}", f"Done: {out}"))
    print(L("以后日常更新：", "Daily update:"))
    print(f"  cd {ROOT}")
    print("  python3 garmin.py sync --days 7")
    print("  python3 garmin.py dashboard")
    print("=" * 62)
    if not args.no_open and out.exists():
        try:
            webbrowser.open(out.as_uri())
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
