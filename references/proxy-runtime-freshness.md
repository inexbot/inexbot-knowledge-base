# hermes-skill-proxy 运行时新鲜度：内存索引 / 重载链 / 缓冲陷阱

2026-10-27 现场沉淀。适用于 `inexbot-knowledge-base` / `inexbot-open-knowledge-base`。

## 核心认知

**proxy 的内存索引和磁盘上的 `index.json` 是两份东西。**
爬虫更新了磁盘文件，**不等于** proxy 立刻用上了新内容 —— proxy 启动时把
`index.json` 读进内存，之后靠定时重载刷新。

本次现场：proxy 进程从 Oct 25 11:11 连续运行，**11:16 才被我重启**。
在这 48 小时里，磁盘上的 `index.json` 已被 Oct 26 的 cron 换过，
但 proxy 内存里仍是 Oct 25 的版本。

**后果**：如果这次 cron 同时发生「上游改 URL」（旧 md 文件被删、新 md 另存），
旧内存索引指向的 md 路径已经不存在 → `read_full_content()` 找不到文件 →
正文取不到 → **引用链接指向已 404 的旧 URL**，而 `/health` 依然报
`docs=558 loaded=true` 全绿。

### 判据：proxy 内存索引是否已过期

```bash
# proxy 启动时间
ps -o pid,lstart,etime -p $(pgrep -f hermes-skill-proxy.py | head -1)

# 对比 index.json 的修改时间
ls -la ~/.hermes/kb/inexbot/index.json
```

`index.json` 的 mtime **晚于** proxy 启动时间 → 内存索引已过期，需要重启。

## ⚠️ 陷阱 1：journal 里没有重载记录 ≠ 重载没发生（stdout 块缓冲）

**这是本次最容易误判的一点。**

在 systemd 下，Python 的 **stdout 是块缓冲**（不是行缓冲）。journal 记录的是
写入管道的内容，块缓冲意味着**小段输出会攒在用户态缓冲区里，直到进程退出
或缓冲区满（~8KB）才一次性刷入**。

实测证据（`systemd-run` + `StandardOutput=journal`）：

```python
print("EARLY_LINE_1")   # 进程启动后立刻打印
time.sleep(45)
print("LATE_LINE")
```

进程存活期间 journal 里 **一行都没有**；进程结束后三行**同时**出现，
时间戳全是同一刻。

后果：proxy 的重载日志 `[proxy] Total: 1357 docs across 2 indexes` 每次约 200 字节，
**远达不到 8KB 刷写阈值** → journal 里可能**几十小时看不到任何重载记录**，
哪怕重载一直在正常发生。

> ✅ **stderr 是行缓冲的**（实测立即可见）。所以诊断类输出要写 stderr。
> ✅ 加 `PYTHONUNBUFFERED=1` 可让 stdout 变行缓冲，journal 立刻可见。
>
> **正确判据**：不要用「journal 里有没有重载日志」来判断重载是否工作。
> 要用**进程内实测**（见下）。

### 进程内实测重载是否工作

```python
# 复制一份 proxy，把间隔改短，跑几十秒看是否反复触发
cp hermes-skill-proxy.py /tmp/proxy_reload_test.py
sed -i 's/^RELOAD_INTERVAL = 5 \* 3600.*/RELOAD_INTERVAL = 10/' /tmp/proxy_reload_test.py
# 直接前台跑即可（stdout 缓冲不影响文件输出）
/usr/bin/python3 /tmp/proxy_reload_test.py > /tmp/reload.log 2>&1 &
sleep 40 && grep -c "Total:" /tmp/reload.log
```

或在 systemd 下跑并加 `PYTHONUNBUFFERED=1`：

```bash
sudo systemd-run --unit=proxy-test --property=Type=exec \
  --property=User=ecs-user --property=WorkingDirectory=/home/ecs-user/hermes-skill-proxy \
  --property=StandardOutput=journal --property=StandardError=journal \
  --property=Environment=PYTHONUNBUFFERED=1 --property=Environment=PROXY_PORT=8646 \
  /usr/bin/python3 /tmp/proxy_reload_test.py
```

实测：10s 间隔下 journal 稳定出现 5 次 `Total:` → **重载机制本身是好的**。

> ⚠️ 别用 `pkill -f <pattern>` 清理测试进程 —— 那个 pattern 会匹配到
> **自己的 shell 命令行**（`pgrep -f` 匹配完整 cmdline，含 pattern 本身），
> 把自己一起杀掉，命令返回 `-15`。用 systemd unit 停：
> `sudo systemctl stop <unit>.service`，或记下 PID 再 `kill <pid>`。

## ⚠️ 陷阱 2：定时重载的异常会**永久**断链（已修）

```python
def schedule_reload():
    load_all_indexes()                      # ← 这里抛异常，下面两行永远不执行
    t = threading.Timer(RELOAD_INTERVAL, schedule_reload)
    t.daemon = True
    t.start()
```

`threading.Timer` 的回调抛异常 → 线程死掉 → **不再排下一次** →
proxy 永远停在旧索引上，且**没有任何报错**（异常只打到该线程的 stderr）。

最小复现（已验证）：把 `load_all_indexes` 换成会抛异常的桩，
第一次重载后线程数从 2 掉回 1，`load_all_indexes` 调用次数停在 2。

**修复**（已应用到 `hermes-skill-proxy.py`）：

```python
def schedule_reload():
    try:
        load_all_indexes()
    except Exception as e:
        print(f"[proxy] RELOAD FAILED: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    finally:
        t = threading.Timer(RELOAD_INTERVAL, schedule_reload)
        t.daemon = True
        t.start()
```

要点：
- `finally` 里排期 → **无论成功失败都继续**
- 错误信息写 **stderr + flush=True**（stdout 块缓冲，journal 里看不到）
- 记得 `import sys`（原文件只 import 了 `os`/`json`/`re`/`time`…，**没有 sys**）

## ⚠️ 陷阱 3：`index.json` 非原子写 → 撞上就抛 JSON 解析错

`crawler.py` 原来是：

```python
with open(path, "w", encoding="utf-8") as f:   # ← 先把文件截断成空
    json.dump(obj, f, ...)                     # ← 再慢慢写 1.7MB
```

proxy 每 5 小时读一次这个文件。**在这 ~1 秒的窗口里读到空文件/半截 JSON**
→ `json.load()` 抛 `json.JSONDecodeError` → 正好命中陷阱 2 → 定时器链断裂。

**修复**（已应用到 `crawler.py` 的 `save_json()`）：

```python
def save_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)          # 原子替换：读者要么看到旧全文，要么看到新全文
```

`os.replace()` 在同一文件系统内是原子的 → 读者**永远**读到完整 JSON。

## cron 收尾：什么时候必须重启 proxy

| 情况 | 是否要重启 |
|---|---|
| 只是正文改了，URL 路径没变 | 不必须（等 5h 自动重载即可） |
| **上游改了 URL 路径**（旧 md 被删） | **必须** —— 旧内存索引指向已删文件 → 404 引用链接 |
| 改了 proxy 代码 | **必须** |
| 改了 `slugify()` / 清洗逻辑 | **必须**（md 文件名变了，内存索引里的 path 映射失效） |

判断是否该重启：

```bash
ls -la ~/.hermes/kb/inexbot/index.json
ps -o pid,lstart -p $(pgrep -f hermes-skill-proxy.py | head -1)
# index.json mtime > proxy 启动时间 → 内存已过期
```

重启（`systemctl --user` 不行，必须用系统级 + sudo）：

```bash
sudo -n systemctl restart hermes-skill-proxy.service
sleep 2
curl -s http://127.0.0.1:8643/health
journalctl -u hermes-skill-proxy --since "2 minutes ago" --no-pager | grep "docs loaded"
```

> ⚠️ `systemctl restart hermes-skill-proxy.service`（不带 sudo）报
> `Interactive authentication required` —— 这是**系统级** unit。
> 本机 `sudo -n` 免密可用。
> ⚠️ `systemctl --user cat hermes-skill-proxy.service` **什么都返回不了**，
> 因为它不是 user unit；要看配置用 `cat /etc/systemd/system/hermes-skill-proxy.service`。
> ⚠️ 仓库里的 `hermes-skill-proxy.service` 副本是**旧的**（`User=inexbot`、
> `WorkingDirectory=/home/inexbot` —— 该目录根本不存在）。以
> `/etc/systemd/system/` 下的为准。

## proxy 检索链路的进程内测试（不依赖 LLM）

`POST /v1/chat/completions` 会**同步调 LLM**，压测时会超时（本次 120s timeout）。
要单独测检索链路，用 `search_single_kb()` 直接调：

```python
import importlib.util, sys
spec = importlib.util.spec_from_file_location("hsp", "/home/ecs-user/hermes-skill-proxy/hermes-skill-proxy.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["hsp"] = mod          # ← 必须放进 sys.modules
spec.loader.exec_module(mod)
mod.load_all_indexes()            # ← 必须调用！否则 _doc_scores 为空，返回 []
for r in mod.search_single_kb("inexbot", "冲压工艺 手册 参数设置", 5):
    print(r["title"], len(r["content_snippet"]), r["url"].count("%25"))
```

两个必踩的坑：
1. **必须 `/usr/bin/python3`** —— 沙盒 `python3` 没装 flask，`import` 直接失败
2. **必须 `mod.load_all_indexes()`** —— 不调用则 `_doc_scores` 为空，
   `search_single_kb()` 静默返回 **空列表**（不报错！看起来像「检索不到」）

判据：
- `len(content_snippet) > 800` = 正文命中
- `== 800` = 静默降级成 index 摘要 → BUG
- `< 200` = 上游占位页（伺服报错系列），正常
- `url.count("%25") == 0` = 无双重编码
