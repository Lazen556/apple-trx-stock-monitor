# Apple Malaysia TRX 库存监测（Discord / 企业微信）

程序每 5 分钟检查 Apple 马来西亚 `The Exchange TRX`。Discord Bot 可以通过指令选择型号；企业微信或普通服务器部署可以通过 `select_models.py` 选择型号。

当前只监测：

- 最新 iPhone Pro / Pro Max（32 个马来西亚 SKU）
- 最新 iPhone Duo（8 个马来西亚 SKU）
- 门店：The Exchange TRX（店铺编号 R742）

程序只汇报已选型号：选项变化后下一轮立即汇报，之后每 30 分钟固定汇报一次；如果已选型号在两次固定汇报之间突然到货，也会立即提醒。消息第一行先显示总体“有货/无货”，后面再显示每个型号的详细信息。

当前已选择：

- iPhone 18 Pro 512GB Glacier（编号 30，SKU `MJRX4X/A`）
- iPhone 18 Pro 512GB Silver（编号 32，SKU `MJRV4X/A`）

## 命令行选择型号

适用于企业微信 Webhook、服务器或本地部署：

```powershell
python select_models.py
python select_models.py --set 30 32
python select_models.py --clear
```

`--set` 会替换当前选择；参数可以是编号、SKU 或 `all`。

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
WECOM_WEBHOOK_URL    = 企业微信群机器人 Webhook（可选）
```

Discord Webhook 或企业微信 Webhook 用于发送库存提醒，Bot Token 用于读取 Discord 的 `!list`、`!watch` 等指令并回复。密钥都不要写进代码。

`REPORT_INTERVAL_MINUTES` 默认是 30，可在运行环境中修改。企业微信群机器人 Webhook 只做推送；如需在企业微信里直接输入指令选择型号，需要由接手者增加企业微信自建应用和消息回调。

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
