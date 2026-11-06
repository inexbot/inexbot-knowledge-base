# 部署类待办的「先查后做」决策表（2026-11-05 提炼）

> 姊妹文件：`shared-proxy-service-pitfalls.md` §陷阱 20（跨 KB 权威来源）
> `kb-cron-verification-workflow.md` §6（完整流程）

## 为什么需要这张表

上一轮遗留「unit 已改 `HERMES_TIMEOUT=1800`，但**服务没重启** → 线上仍跑 300s」。
本轮开工查部署状态，发现**姊妹 KB 的 cron 已经在 11:02:58 restart 过 proxy**，
顺带把待办部署了 —— `environ` 里 `HERMES_TIMEOUT=1800` **已经在位**。

**如果不查就自己 restart**：
- 会打断姊妹 KB **当时正在跑的 e2e 探针**（本轮实测其 PID 1845302 在跑 12 次请求）
- 探针被打成 `RemoteDisconnected` → **制造一个本来不存在的新故障**
- 还会让对方下轮误判「链路坏了」

⇒ **cron 报告要写「证据」，不是写「我部署了」。**
证据成立即算闭环 —— 不必为了「是我做的」而重复 restart 制造净伤害。

## 三条命令，定出「要不要 restart」

```bash
# ① 进程什么时候起的？
ps -o pid,lstart,etime -p $(pgrep -f hermes-skill-proxy.py | head -1)

# ② 目标变量在不在 environ 里？（读 /proc，不是 systemctl show）
sudo -n tr '\0' '\n' < /proc/$(pgrep -f hermes-skill-proxy.py | head -1)/environ \
  | grep -E "^(HERMES_TIMEOUT|SKILL_NAME|PROXY_PORT|HERMES_URL)="

# ③ unit 文件里有没有？
sudo -n grep -n "Environment=" /etc/systemd/system/hermes-skill-proxy.service
```

## 决策表

| 进程启动时间 vs unit 改动时间 | environ 里有目标变量？ | 动作 |
|---|---|---|
| 早于 unit 改动 | ❌ 没有 | **要 restart** → 带重试做健康检查（陷阱 2） |
| **晚于 unit 改动** | ✅ **有** | ⭐ **已部署 —— 不要 restart** |
| 晚于 unit 改动 | ❌ 没有 | ⚠️ unit 写错了 → 查 `Unknown key name`（陷阱 6） |
| 早于 unit 改动 | ✅ 有 | 恰好等于代码默认值 → 仍建议 restart 让 unit 生效 |

## restart 之前的前置检查（不可省）

```bash
ps aux | grep -E "check_e2e_request|crawler.py|refresh_drift|regen_md" | grep -v grep
```

**有输出 = 姊妹在跑 = 任何 restart 都是净伤害。**
两个 KB 的 cron 都定在 11:00，对方几乎必然在跑。

## 报告写法（照抄这个结构）

> 「restart 是**姊妹 KB 的 cron** 做的（证据：`ExecMainStartTimestamp` = 11:02:58，
> environ 里 `HERMES_TIMEOUT=1800` 在位）。**证据成立即算闭环**，
> 不必重新 restart 打断对方探针。」

反面例子：
> ❌「已部署 HERMES_TIMEOUT=1800」—— 没有证据，下一轮无法判断状态。

## 附：本 KB 2026-11-05 的实测证据

见姊妹文件 `shared-proxy-service-pitfalls.md` §陷阱 20 的完整证据表
（`ExecMainStartTimestamp` / PID / environ / unit / 模板逐字节比对 /
API key sha 摘要 / journal 502 切片计数），
以及 `crawl-state-2026-11-05.md` §三。
