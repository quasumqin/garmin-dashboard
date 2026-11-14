# Garmin 个人 API Key 申请说明

这套看板用的是 **Garmin Connect Personal API**：只读、只能访问**本人**数据、自用。
它不是企业开发者计划，**不需要公司资质、不需要提交申请、没有人工审核**，在 Garmin Connect
设置页自助生成即可。

官方说明：<https://developer.garmin.com/gc-developer-program/overview/>

## 1. 先确认账号属于哪个区

| 账号区域 | 登录地址 | Key 页面 | API 端点 |
|---|---|---|---|
| 国际区 | <https://connect.garmin.com> | <https://connect.garmin.com/app/settings/personalApiToken> | `https://personal.connectapi.garmin.com` |
| 中国区 | <https://connect.garmin.cn> | <https://connect.garmin.cn/app/settings/personalApiToken> | `https://personal.connectapi.garmin.cn` |

**Key 与区域绑定**：`.com` 的 Key 只能配 `.com` 端点，配 `.cn` 会返回
`404 Personal API Key with ID … does not exist`，看起来像 Key 失效，其实是走错主机。

## 2. 生成 Personal API Key

1. 用你的 Garmin 账号登录对应区域的 Garmin Connect。
2. 打开上面的 **Key 页面**（也可以在 Connect 的账号设置里找 “Personal API” / “个人 API”）。
3. 按页面提示生成 Key，复制完整字符串。
4. 如果页面提示只能查看一次，先粘到安全的地方；丢了就重新生成。

> Garmin 可能调整页面路径或文案。找不到时，在 Connect 设置里搜索 “Personal API”，
> 或直接访问 `https://connect.garmin.com/app/settings/personalApiToken`。

## 3. 保存 Key

向导会帮你保存到：

```
~/.config/garmin/personal_api_key.com.txt    # 国际区
~/.config/garmin/personal_api_key.cn.txt     # 中国区
```

手动保存：

```bash
mkdir -p ~/.config/garmin
chmod 700 ~/.config/garmin
printf '%s' '你的KEY' > ~/.config/garmin/personal_api_key.com.txt
chmod 600 ~/.config/garmin/personal_api_key.com.txt
```

**不要把 Key 发到群里、截图里或提交到 git。** 它等同于你账号的只读访问权限。

## 4. Key 是怎么用的

脚本不直接拿 Key 调数据接口，而是先换一个 24 小时的 Bearer token：

```http
POST https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token
Authorization: ApiKey <你的Key>
```

返回一串 token，之后所有请求带 `Authorization: Bearer <token>`。
token 约 24 小时有效，**没有 refresh token**；过期后用同一个 Key 再换一次。
脚本会自动缓存和续换，你不需要手动操作。

## 5. 能拿到什么数据

Personal API 支持拉取：

- 活动：JSON、FIT 原始文件
- 健康：步数、心率、睡眠、HRV、压力、血氧、体重等每日汇总
- 女性健康：相关记录（如适用）

**只读、Pull 模式**，不能写回 Garmin，也没有 webhook/推送。

## 6. 限流与礼貌使用

官方没有公布个人 API 的限流阈值，但保留限流权。本项目的默认策略：

- 普通请求串行，间隔 0.35 秒
- 睡眠按天取，4 线程并发，间隔 0.15 秒
- 429 / 5xx 指数退避重试

不要改成高并发批量拉取；日常增量 `sync --days 7` 就够了。

## 7. 常见报错

| 报错 | 原因 | 处理 |
|---|---|---|
| `404 Personal API Key with ID … does not exist` | 区域配错 | 国际区用 `.com`，中国区用 `.cn` |
| `401 Unauthorized` | Key 复制不全 / 已失效 | 回设置页重新生成，完整复制 |
| `403` | 账号无权限或 Key 类型不对 | 确认用的是 Personal API，不是企业 Key |
| 拉到的数据为空 | 手表还没同步到 Connect，或日期范围不对 | 先在手机/网页确认数据存在，再 `sync --days 30` |
| 连接超时 | 中国大陆访问 `.com` 受限 | 配代理，或改用 `.cn` 账号 |

## 8. 隐私

- 数据只写入本机 `data/garmin.db`，看板是静态 HTML，不上传。
- Key 与 token 在 `~/.config/garmin/`，不在项目目录。
- 项目 `.gitignore` 已排除 `data/`、`fit/`、`reports/`。
- 不想用了：删除 `~/.config/garmin/` 和项目里的 `data/`、`reports/` 即可；也可以去 Garmin 设置页吊销 Key。

## 9. 和企业 API 的区别

| | Personal API | Business / Enterprise API |
|---|---|---|
| 对象 | 个人，访问本人数据 | 企业应用，访问用户授权数据 |
| 申请 | Connect 设置页自助生成 | 企业开发者计划，需申请/审核 |
| 模式 | 只读 Pull | Push / Ping / Pull |
| 用途 | 自用分析 | 商业产品集成 |

这套看板只用 Personal API，不需要企业资质。
