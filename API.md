# Garmin Personal API Key

This dashboard uses the **Garmin Connect Personal API**: read-only, your own data only,
for personal use. It is **not** the business developer program — no company application,
no manual review, no approval queue. You generate the key yourself in Garmin Connect settings.

Official overview: <https://developer.garmin.com/gc-developer-program/overview/>

**English | [中文](API.zh-CN.md)**

## 1. Pick the right region

| Account region | Sign-in | Key page | API endpoint |
|---|---|---|---|
| International | <https://connect.garmin.com> | <https://connect.garmin.com/app/settings/personalApiToken> | `https://personal.connectapi.garmin.com` |
| China | <https://connect.garmin.cn> | <https://connect.garmin.cn/app/settings/personalApiToken> | `https://personal.connectapi.garmin.cn` |

**The key is region-bound.** A `.com` key against `.cn` returns
`404 Personal API Key with ID … does not exist`, which looks like an invalid key but is
actually the wrong host.

## 2. Generate the key

1. Sign in to Garmin Connect in the matching region.
2. Open the **Key page** above (or search for “Personal API” in Connect settings).
3. Generate the key and copy the whole string.
4. If the page says it is shown only once, store it safely; otherwise generate a new one.

> Garmin may change the page path or wording. If it moves, search for “Personal API” in
> Connect settings, or try `https://connect.garmin.com/app/settings/personalApiToken`.

## 3. Store the key

The wizard writes it to:

```
~/.config/garmin/personal_api_key.com.txt    # international
~/.config/garmin/personal_api_key.cn.txt     # China
```

Manual method:

```bash
mkdir -p ~/.config/garmin
chmod 700 ~/.config/garmin
printf '%s' 'YOUR_KEY' > ~/.config/garmin/personal_api_key.com.txt
chmod 600 ~/.config/garmin/personal_api_key.com.txt
```

**Never post the key, screenshot it or commit it.** It grants read-only access to your account.

## 4. How the key is used

The script exchanges the key for a 24-hour Bearer token:

```http
POST https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token
Authorization: ApiKey <YOUR_KEY>
```

The returned token is sent as `Authorization: Bearer <token>`. It expires after about
24 hours, and there is **no refresh token**; request a new one with the same key. The script
caches and renews it automatically.

## 5. What data is available

- Activities: JSON and original FIT files
- Health: steps, heart rate, sleep, HRV, stress, SpO2, weight and other daily summaries
- Women's health: related records, where applicable

**Read-only, pull only.** You cannot write back to Garmin and there are no webhooks.

## 6. Rate limits and etiquette

Garmin does not publish a Personal API rate limit but reserves the right to throttle.
This project:

- serial requests with a 0.35 s gap
- sleep fetched per day with 4 threads and a 0.15 s gap
- exponential backoff on 429 / 5xx

Do not turn it into a high-concurrency scraper. A daily `sync --days 7` is enough.

## 7. Common errors

| Error | Cause | Fix |
|---|---|---|
| `404 Personal API Key with ID … does not exist` | wrong region | `.com` for international, `.cn` for China |
| `401 Unauthorized` | incomplete / expired key | generate a new key and copy it fully |
| `403` | wrong key type or no permission | make sure it is a Personal API key |
| Empty data | watch not synced, or wrong date range | confirm data in Connect, then `sync --days 30` |
| Timeout | `.com` blocked from mainland China | use a proxy or a `.cn` account |

## 8. Privacy

- Data is written only to local `data/garmin.db`; the dashboard is static HTML and uploads nothing.
- Keys and tokens live in `~/.config/garmin/`, not in the project directory.
- `.gitignore` excludes `data/`, `fit/` and `reports/`.
- To remove everything: delete `~/.config/garmin/`, `data/` and `reports/`; you can also revoke the key in Garmin settings.

## 9. Personal vs Business API

| | Personal API | Business / Enterprise API |
|---|---|---|
| Audience | Individuals, own data | Companies, user-authorized data |
| Access | Self-service in Connect settings | Developer program application/review |
| Mode | Read-only pull | Push / Ping / Pull |
| Use | Personal analysis | Commercial product integration |

This dashboard uses the Personal API only; no company credentials are needed.
