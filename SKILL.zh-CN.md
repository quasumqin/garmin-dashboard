---
name: garmin-dashboard
description: 同步 Garmin Connect 个人 API 数据（活动/睡眠/HRV/体重）到本地 SQLite，并生成单文件训练与健康看板；首次使用会引导申请个人 API Key。当用户说“同步 Garmin”“生成 Garmin 看板”“分析我的 Garmin 数据”“装一下 Garmin 看板”时使用。
---

# Garmin 训练与健康看板

**中文 | [English](SKILL.md)**

本目录既是独立 Python 项目，也是 Claude Code skill。数据只在本机，不上传。

## 首次使用

先跑向导，不要直接问用户要 Key：

```bash
python3 setup.py
```

向导会：

1. 问账号区域（国际区 `.com` / 中国区 `.cn`）
2. 打开 Garmin 个人 API 页面，让用户自己生成并粘贴 Key（`getpass`，不回显）
3. 验证 token、拉取 90 天、生成 `reports/dashboard.html`

如果用户不知道怎么申请，读 `API.zh-CN.md`，把对应区域的链接发给他：
- 国际区：<https://connect.garmin.com/app/settings/personalApiToken>
- 中国区：<https://connect.garmin.cn/app/settings/personalApiToken>

**绝对不要**在聊天里索要或粘贴 API Key；让用户自己在 `setup.py` 的隐藏输入里填。

## 日常

```bash
python3 garmin.py sync --days 7     # 增量
python3 garmin.py dashboard         # 出图
python3 garmin.py status            # 库状态
```

输出：`reports/dashboard.html`（单文件，双击可看）。

## 规则

- 不要提交 `data/`、`fit/`、`reports/`；里面是个人健康数据。
- 不要读取或打印 `~/.config/garmin/` 里的 Key / token。
- 遇到 404 先查区域是否配错；401 让用户重新生成 Key。
- 中国大陆访问 `.com` 端点可能需要代理；`.cn` 账号用 `.cn`。
- 看板口径：训练负荷是 Garmin `activityTrainingLoad`，只作相对趋势；力量动作来自手表按组记录。

## 排障

| 现象 | 处理 |
|---|---|
| `404 Personal API Key … does not exist` | 区域配错，换 `--region cn` / `com` 重跑 |
| `401` | Key 不全或失效，让用户回设置页重新生成 |
| 没有数据 | 确认手表已同步到 Connect；再 `sync --days 30` |
| 页面打不开 | 直接打开 `reports/dashboard.html`，Chart.js 已内联 |

更多说明见 `README.zh-CN.md`、`API.zh-CN.md`。
