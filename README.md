# Apple Malaysia TRX 库存监测（GitHub Actions + Discord）

这是一个不需要购买服务器的版本。GitHub Actions 每 5 分钟检查一次 Apple 马来西亚 `The Exchange TRX`，有货状态从“无货”变成“有货”时发送 Discord 通知。

当前只监测：

- 最新 iPhone Pro / Pro Max（32 个马来西亚 SKU）
- 最新 iPhone Duo（8 个马来西亚 SKU）
- 门店：The Exchange TRX（店铺编号 R742）

## 部署步骤

### 1. 创建 GitHub 仓库

在 GitHub 创建一个新的仓库，建议设为 Private。然后把本目录中的全部文件上传，必须保留这个路径：

```text
.github/workflows/stock-monitor.yml
```

也可以在本目录执行：

```powershell
git init
git branch -M main
git add .
git commit -m "Initial Apple TRX stock monitor"
git remote add origin https://github.com/<你的用户名>/<你的仓库名>.git
git push -u origin main
```

### 2. 创建 Discord Webhook Secret

在 Discord 服务器中打开目标频道：

`编辑频道 → 集成 → Webhooks → 新建 Webhook → 复制 Webhook URL`

不要把这个 URL 写进代码，也不要发到聊天里。

然后在 GitHub 仓库打开：

`Settings → Secrets and variables → Actions → New repository secret`

填写：

```text
Name: DISCORD_WEBHOOK_URL
Secret: 粘贴 Discord Webhook URL
```

### 3. 手动测试

打开仓库的 `Actions` 标签，选择 `Apple TRX stock monitor`，点击 `Run workflow`。

运行完成后点击任务查看日志。如果接口正常，会看到每个 SKU 的 `unavailable` 或 `AVAILABLE` 状态。

## 说明

- 任务默认每 5 分钟运行一次，但 GitHub 的定时任务可能延迟，不是秒级实时监控。
- GitHub Actions 会把 `stock_state.json` 提交回仓库，用于只在“首次变有货”时通知，避免重复刷屏。
- Discord Webhook 只保存在 GitHub Secret 中，不进入公开代码。
- 如果 Apple 接口临时限流，当前运行会记录错误；只有全部 SKU 请求失败时才会让 Actions 任务失败。
- GitHub 对长时间没有活动的公开仓库可能自动停用定时任务；偶尔打开仓库或手动运行一次即可保持活跃。
