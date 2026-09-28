# Apple Malaysia TRX 库存监测（GitHub Actions + Discord）

这套程序不需要购买云服务器。GitHub Actions 每 5 分钟检查 Apple 马来西亚 `The Exchange TRX`，Discord Bot 可以查看型号、选择监测或静音。

当前只监测：

- 最新 iPhone Pro / Pro Max（32 个马来西亚 SKU）
- 最新 iPhone Duo（8 个马来西亚 SKU）
- 门店：The Exchange TRX（店铺编号 R742）

默认没有选择任何型号，因此默认全部免打扰。选择后，只有被选择的型号从无货变成有货时才会通知。

## Discord 指令

在配置的 Discord 频道发送：

```text
!help
!list
!status
!watch 1 3
!mute 1 3
!selected
!clear
```

`!list` 会显示编号、型号和 SKU。`!watch 1 3` 表示选择第 1 和第 3 个型号；`!clear` 会清空选择，让全部型号免打扰。

`!status` 会查询全部型号的最新库存状态，但不会触发提醒，也不会 @ 任何人。

由于检查器运行在 GitHub Actions，Discord 指令会在下一次任务运行时处理，通常最多等待约 5 分钟，不是实时对话机器人。

## 部署步骤

### 1. 创建 Discord Bot

打开 [Discord Developer Portal](https://discord.com/developers/applications)：

1. `New Application`，名称可填 `Apple TRX Monitor`。
2. 进入 `Bot` → `Add Bot`，复制 Bot Token。Token 只放在 GitHub Secret，不要发到聊天里。
3. 在 `Bot` 页面打开 `Message Content Intent`。
4. 进入 `OAuth2` → `URL Generator`，勾选 scope：`bot`。
5. 勾选权限：`View Channels`、`Read Message History`、`Send Messages`。
6. 打开生成的邀请链接，把 Bot 加入 `TRX APPLE` 服务器。

### 2. 获取频道 ID

Discord：`用户设置 → 高级 → 开发者模式`，打开后右键 `#常规` 频道，点击 `复制频道 ID`。

### 3. 添加 GitHub Secrets

仓库中打开：

`Settings → Secrets and variables → Actions → New repository secret`

添加：

```text
DISCORD_WEBHOOK_URL  = 现有 Discord Webhook URL
DISCORD_BOT_TOKEN    = Discord Developer Portal 复制的 Bot Token
DISCORD_CHANNEL_ID   = #常规频道 ID
```

Webhook 用于发送库存提醒，Bot Token 用于读取 `!list`、`!watch` 等指令并回复。三项都不要写进代码。

### 4. 测试

打开仓库 `Actions` → `Apple TRX stock monitor` → `Run workflow`。

第一次运行会初始化 Bot。下一次运行后，在 Discord 频道发送 `!help` 或 `!list`。

### 5. 推送升级后的代码

如果仓库已经有旧版本，在本目录执行：

```powershell
git add .
git commit -m "feat: add Discord model selection"
git push
```

GitHub Actions 的定时任务可能延迟，不是秒级实时监控。电脑可以关机，仓库和 Secret 不要删除。
