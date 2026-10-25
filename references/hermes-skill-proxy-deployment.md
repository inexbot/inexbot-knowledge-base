# hermes-skill-proxy 部署参考

## 仓库位置

| 项目 | 路径 |
|------|------|
| 代码仓库 | `/home/ecs-user/hermes-skill-proxy/` |
| systemd service | `/etc/systemd/system/hermes-skill-proxy.service`（系统级，需 sudo） |
| 进程管理 | sudo systemctl（不是 `systemctl --user`） |

## 常见陷阱

### 1. service 文件路径和运行进程路径不一致

systemd service 文件中的路径必须和实际进程路径一致。常见错误：

```
# ❌ service 指向 /home/inexbot/，但代码实际在 /home/ecs-user/
User=inexbot
WorkingDirectory=/home/inexbot
ExecStart=/usr/bin/python3 /home/inexbot/hermes-skill-proxy/hermes-skill-proxy.py
```

**排错步骤**：
```bash
# 先找到实际运行进程
ps aux | grep hermes-skill-proxy | grep -v grep

# 再看 systemd service 文件
systemctl status hermes-skill-proxy
sudo systemctl cat hermes-skill-proxy
```

### 2. User=inexbot 导致 exit-code 217/USER

`status 217/USER` = systemd 找不到配置的用户。修复：
```
User=ecs-user
```
当前用户可通过 `whoami` 确认。

### 3. systemctl --user vs 系统级 systemctl

| 类型 | 管理命令 | service 文件位置 |
|------|----------|-----------------|
| system-wide（系统服务） | `sudo systemctl restart hermes-skill-proxy` | `/etc/systemd/system/` |
| user-level（用户服务） | `systemctl --user restart hermes-skill-proxy` | `~/.config/systemd/user/` |

hermes-skill-proxy 部署为系统服务（随开机启动，与用户会话无关），所以用 `sudo systemctl`。

## 完整部署步骤

```bash
# 1. 拉取最新代码
cd /home/ecs-user/hermes-skill-proxy
git fetch origin main && git reset --hard origin/main

# 2. 检查/修改 service 文件关键字段
# - User=ecs-user（不是 inexbot）
# - WorkingDirectory=/home/ecs-user/hermes-skill-proxy
# - ExecStart 指向实际路径

# 3. 安装 service 文件
sudo cp /home/ecs-user/hermes-skill-proxy/hermes-skill-proxy.service /etc/systemd/system/

# 4. 重载并重启
sudo systemctl daemon-reload
sudo systemctl restart hermes-skill-proxy

# 5. 验证
sudo systemctl status hermes-skill-proxy
sleep 2 && sudo systemctl status hermes-skill-proxy
```

正常返回：
```json
{"status":"ok","indexes":{"inexbot":{"docs":126,"loaded":true},"inexbot-open":{"docs":170,"loaded":true}}}
```

## 安全更新流程（git stash 保护本地 KB 数据）

**关键原则：永远不要 `git pull --force` 或 `git reset --hard`，因为 KB 数据在 repo 之外。**

```bash
# 1. 拉取 proxy 最新代码
cd /home/ecs-user/hermes-skill-proxy && git stash && git pull origin main && git stash drop

# 2. 拉取两个 KB skill 最新代码
cd ~/.hermes/skills/productivity/inexbot-knowledge-base && git stash && git pull origin main && git stash drop
cd ~/.hermes/skills/productivity/inexbot-open-knowledge-base && git stash && git pull origin main && git stash drop

# 3. 重启服务
sudo systemctl restart hermes-skill-proxy

# 4. 验证
curl http://localhost:8643/health
```

注意：stash 内容为空（`No local changes to save`）是正常现象——SKILL.md 和 crawler.py 本身不在 KB 数据目录。

```bash
# systemd journal
sudo journalctl -u hermes-skill-proxy -n 30 --no-pager

# 实时 tail
sudo journalctl -u hermes-skill-proxy -f
```

## 内容上限（重要发现）

hermes-skill-proxy 内部有两层内容上限：

| 位置 | 默认值 | 说明 |
|------|--------|------|
| `read_full_content()` return | 6000 | 读取完整文档后的截断 |
| `content_snippet` 最终截断 | 3000→6000 | 注入 prompt 前的硬截断 |

`read_full_content` 能读 6000，但最终输出被 `content_snippet[:3000]` 截断，导致分段提取（最多 8000）完全浪费。2026-05-12 已修改为 6000。

如需再次调整，搜索 `content_snippet[:` 找到截断位置。

## GitHub 连接不稳定

git pull 超时是常见现象（服务器网络对 GitHub 不稳定）。处理顺序：

1. `git pull` 超时 → 等几秒重试
2. 再超时 → `git fetch origin main` 单独试
3. 持续失败 → 用户自行手动拉取后通知 agent，agent 检查 `git log -1` 确认版本

不要反复重试超过 2 次，超时不会因为重试变快。

## 端口检查

服务监听在 `PROXY_PORT`（默认 8643），Hermes 连接到此端口：
```bash
ss -tlnp | grep 8643
curl -s http://localhost:8643/health 2>/dev/null || echo "no health endpoint"
```
