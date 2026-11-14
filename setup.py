#!/usr/bin/env python3
"""Garmin 看板首次使用向导。

    python3 setup.py

会依次完成：选区域 → 引导申请/粘贴个人 API Key → 验证 token → 拉取数据 → 生成看板。
密钥只写到本机 ~/.config/garmin/，不会进仓库、不会打印。
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
    tip = f"（默认 {default}）" if default else ""
    v = input(f"{prompt}{tip}: ").strip()
    return v or (default or "")


def yes(prompt, default=True):
    tip = "Y/n" if default else "y/N"
    v = input(f"{prompt} [{tip}]: ").strip().lower()
    if not v:
        return default
    return v in ("y", "yes", "是")


def main():
    ap = argparse.ArgumentParser(description="Garmin 看板首次使用向导")
    ap.add_argument("--region", choices=["com", "cn"], help="账号区域：com 国际区 / cn 中国区")
    ap.add_argument("--key-file", help="已有的 Personal API Key 文件路径")
    ap.add_argument("--days", type=int, default=90, help="首次拉取天数，默认 90")
    ap.add_argument("--no-sync", action="store_true", help="不拉数据，只用现有库出图")
    ap.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    ap.add_argument("--yes", action="store_true", help="全部用默认值，不交互（测试用）")
    args = ap.parse_args()

    print("=" * 62)
    print("  Garmin 训练与健康看板 · 首次使用向导")
    print("=" * 62)
    print("数据只保存在本机 SQLite，不上传任何服务器。")
    print()

    region = args.region
    if not region:
        if args.yes:
            region = "com"
        else:
            print("你的 Garmin Connect 账号属于哪个区？")
            print("  1) 国际区（connect.garmin.com）")
            print("  2) 中国区（connect.garmin.cn）")
            region = "cn" if ask("选 1 或 2", "1") == "2" else "com"

    os.environ["GARMIN_REGION"] = region
    import config  # noqa: E402  （必须在设置 GARMIN_REGION 之后导入）
    import garmin  # noqa: E402

    print(f"\n区域：{region}（{config.BASE}）")
    print(f"数据目录：{config.DATA_DIR}")
    print(f"报告目录：{config.REPORT_DIR}\n")

    key_file = Path(args.key_file) if args.key_file else config.KEY_FILE
    print("-" * 62)
    print("第 1 步：申请 Personal API Key")
    print("-" * 62)
    print("个人 API 不需要企业申请、没有人工审核，在 Garmin Connect 设置页自助生成：")
    print(f"  {config.KEY_PAGE}")
    print("登录后打开该页，生成/复制 Personal API Key。")
    print("注意：Key 与区域绑定，国际区配 .com、中国区配 .cn，不能混用。\n")

    if not args.no_open:
        try:
            webbrowser.open(config.KEY_PAGE)
        except Exception:
            pass

    key_exists = key_file.exists()
    if key_exists:
        reuse = True if args.yes else yes(f"已存在密钥 {key_file}，继续用它吗？", True)
        if not reuse:
            print("将重新输入密钥。")
            key_exists = False

    if not key_exists:
        key = getpass.getpass("粘贴 Personal API Key（输入不回显）: ").strip()
        if not key:
            print("没有输入密钥，退出。")
            return 2
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(key)
        try:
            os.chmod(key_file, 0o600)
        except Exception:
            pass
        print(f"密钥已保存：{key_file}（仅本机可读）")

    # 让 garmin.Client 使用本次选定的密钥文件（--key-file 或默认路径）
    config.KEY_FILE = key_file

    print("\n第 2 步：验证密钥")
    try:
        client = garmin.Client()
        client._fetch_token()
    except Exception as e:
        print(f"\n验证失败：{type(e).__name__}: {e}")
        print("\n常见原因：")
        print("  404 / Key does not exist → 区域配错，试另一个区（--region cn / com）")
        print("  401 → Key 复制不全或已失效，回设置页重新生成")
        print(f"  网络 → 本机能否访问 {config.BASE}")
        return 1
    print("密钥有效。")

    if args.no_sync:
        print("\n跳过拉取数据（--no-sync）。")
    else:
        days = args.days if args.yes else int(ask("第 3 步：首次拉取多少天", str(args.days)))
        print(f"\n第 3 步：拉取最近 {days} 天数据（约 1–3 分钟）")
        r = subprocess.run([sys.executable, "garmin.py", "sync", "--days", str(days)], cwd=ROOT)
        if r.returncode != 0:
            print("同步失败，请把上面的报错发给我。")
            return r.returncode

    print("\n第 4 步：生成看板")
    r = subprocess.run([sys.executable, "garmin.py", "dashboard"], cwd=ROOT)
    if r.returncode != 0:
        return r.returncode

    out = config.REPORT_DIR / "dashboard.html"
    print("\n" + "=" * 62)
    print(f"完成：{out}")
    print("以后日常更新：")
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
