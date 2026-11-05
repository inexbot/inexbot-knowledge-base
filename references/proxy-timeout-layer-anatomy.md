# proxy → gateway → LLM 全链路超时解剖

> 2026-11-04 实测整理。用于决定 **proxy 的 `HERMES_TIMEOUT` 该设多少**，
> 以及区分「proxy 放弃太早」与「gateway 真的挂住」。
> 姊妹文件：`shared-proxy-service-pitfalls.md` §陷阱 10 / §陷阱 17。

---

## 一、各层超时一览（2026-11-04 实测值）

| 层 | 超时 | 位置 | 性质 |
|---|---|---|---|
| **proxy → gateway** | `HERMES_TIMEOUT`，默认 300s | `hermes-skill-proxy.py` 的 `HERMES_TIMEOUT = int(os.getenv("HERMES_TIMEOUT", "300"))` | **墙钟**（`requests.post(timeout=)`） |
| gateway → LLM provider（单次调用） | **900s** | `agent/anthropic_adapter.py` 的 `_read_timeout`（`Timeout(timeout=float(_read_timeout), connect=10.0)`） | **单次 HTTP 读超时** |
| gateway → LLM provider（重试） | 900s × `api_max_retries`（默认 **3**） | `run_agent.py` 的 `while retry_count < max_retries`（`api_max_retries` 来自 `config.yaml` 的 `agent.api_max_retries`） | **每次重试各算一份 900s** |
| gateway 整轮看门狗 | **1800s** | `config.yaml` 的 `agent.gateway_timeout`（`HERMES_AGENT_TIMEOUT` 环境变量优先） | ⚠️ **「无活动（inactivity）」不是墙钟** —— 见 §二 |
| gateway HTTP 层 | **无** | `gateway/platforms/api_server.py` 的 `_handle_chat_completions` → `_run_agent` → `loop.run_in_executor` | 无 `asyncio.wait_for` 包裹 |

### ⚠️ 关键：`gateway_timeout=1800` 是**无活动**看门狗，不是墙钟上限

`gateway/run.py` 里的注释写得很清楚：

> Use an *inactivity*-based timeout instead of a wall-clock limit: the agent can run
> for hours if it's actively calling tools / receiving stream tokens, but a hung
> API call or stuck tool with no activity for the configured duration is caught
> and killed.

**推论（对修法至关重要）**：

- ❌ **不能**把 1800s 当成「gateway 最多跑 1800s」→ 「proxy 设 1800s 就能对齐」这个推理是错的
- ✅ 1800s 是「**多久没有任何活动**才判定挂死」→ **合法长请求跑 3000s+ 完全正常**
- ✅ 真正的墙钟上限是 **900s × 重试次数**（最坏 2700s+），且 api_server 路径**没有**额外的墙钟封顶
- ✅ 结论：**proxy 的 timeout 只要别比「上游最坏耗时」小就行**；
  设 1800s 是合理兜底，但它**仍可能**小于 900×3=2700s 的最坏情况 →
  想彻底消除 502，proxy timeout 需 **≥ 2700s**，或改用「无限等待 + 自己重试」

> 💡 **通则**：判断「proxy 该设多少 timeout」时，**先问「上游最坏情况是多久」**，
> 而不是「上游的标称 timeout 是多少」。provider 的标称 900s 只是**单次调用**的读超时，
> 重试会把它乘起来。

---

## 二、注入体积 = 延迟的根因（2026-11-04 实测）

proxy 每次请求都把 top-5 检索结果全量拼进 system prompt。
**进程内测量方法**（不联网、不调 LLM）：

```python
import importlib.util, sys
spec = importlib.util.spec_from_file_location("hsp", "/home/ecs-user/hermes-skill-proxy/hermes-skill-proxy.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["hsp"] = mod          # ← 必须放进 sys.modules
spec.loader.exec_module(mod)
mod.load_all_indexes()            # ← 必须调用！否则返回 []

for q in ["冲压工艺 手册 参数设置", "伺服 报警 0x0051 怎么处理"]:
    res = mod.search_single_kb("inexbot", q, 5)
    chars = sum(len(r.get("content_snippet") or "") for r in res)
    print(q, "chars=", chars, [len(r.get("content_snippet") or "") for r in res])
```

**2026-11-04 实测（单库 top-5）**：

| 查询 | 注入字符数 | 各条 snippet 长度 |
|---|---|---|
| 冲压工艺 手册 参数设置 | **21,043** | 4000×5（全部打满） |
| 通讯协议 地址码 Modbus 寄存器 | **17,091** | 2701 / 4000 / 4000 / 4000 / 1378 |
| 示教器 手册 使用教程 | **14,201** | 4000 / 1093 / 2428 / 4000 / 1639 |
| 控制器 IO 组号 DOUT 怎么配置 | **13,594** | 3139 / 4000 / 1139 / 1387 / 2701 |
| 伺服 报警 0x0051 怎么处理 | **11,314** | 4000 / 453 / 2825 / 691 / 2392 |

⇒ **注入体积区间 11k–21k 字符**。这是 LLM 首 token 延迟的主因，
也是「prompt 越长越容易超 300s」的量化依据。

> ⚠️ **不要擅自降体积**：snippet 上限 4000 是为了让长手册正文完整可读
> （见 SKILL.md「长手册型主题」）。调小会牺牲答案质量 → **属产品决策，需人工确认**。

---

## 三、nginx 在 :80 —— **不是** proxy 的消费者（2026-11-04 实测）

排查「还有谁在调 proxy / 谁会受影响」时，`ss -ltn` 会看到：

```
LISTEN 0  511  0.0.0.0:80  0.0.0.0:*   users:(("nginx",pid=1767902,fd=6),...)
```

**这是 Debian 默认 nginx 站点**（`/etc/nginx/sites-enabled/default` → `root /var/www/html`），
**没有** `proxy_pass`、**没有**指向 8643、`/etc/nginx/conf.d/` 是空的。

⇒ **改 proxy 的 timeout / 重启 proxy 不会影响这个 nginx**。
但**别**因此假设「没人调 proxy」：实际调用方是 Hermes gateway（8642）
和两个 KB 的 e2e 探针。

判别命令：

```bash
sudo -n grep -rn "8643\|proxy_pass\|proxy_read_timeout" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/
# 无输出 = nginx 不参与这条链路
```

> 💡 若将来 nginx 真的加了 `proxy_pass http://localhost:8643`，
> 那 **`proxy_read_timeout` 就会成为真正的端到端上限** —— 必须一起调大，
> 否则 nginx 会先于 proxy 断开。

---

## 四、unit 文件改 timeout 的**安全做法**（2026-11-04 实测）

要给 `HERMES_TIMEOUT` 之类加 `Environment=` 行时，**不要用 `patch` 手打整块**
（会撞上「含密钥的行被脱敏污染」的坑，见 §陷阱 9 / SKILL.md「patch 工具写含密钥的行」）。

**安全做法**：读文件 → 在**稳定锚点行后**插入 → **sha256 校验密钥未被改动** → 才安装。

```python
import hashlib, re, subprocess
from pathlib import Path

DEPLOYED = Path("/etc/systemd/system/hermes-skill-proxy.service")
TEMPLATE = Path("/home/ecs-user/hermes-skill-proxy/hermes-skill-proxy.service")

ANCHOR = 'Environment="SKILL_NAME=inexbot-knowledge-base"'   # ← 稳定、绝不含密钥
NEW    = 'Environment="HERMES_TIMEOUT=1800"'

def key_digest(t):
    m = re.search(r'Environment="HERMES_API_KEY=([^"]*)"', t)
    v = m.group(1)
    return len(v), hashlib.sha256(v.encode()).hexdigest()[:12]

orig = DEPLOYED.read_text(encoding="utf-8")
before = key_digest(orig)
new = orig.replace(ANCHOR, ANCHOR + "\n" + NEW, 1)
assert key_digest(new) == before, "API key changed -- abort"   # ← 关键护栏
tmp = Path("/tmp/new-unit.service"); tmp.write_text(new, encoding="utf-8")
subprocess.run(["sudo", "-n", "cp", str(tmp), str(DEPLOYED)], check=True)
print("installed; key digest unchanged:", key_digest(DEPLOYED.read_text(encoding="utf-8")))
```

**2026-11-04 实测**：部署版与 repo 模板的 key digest 均为
`(21, '23760f4462da')` —— 改前改后一致，**未**被脱敏污染。
（`hermes...rch` 只是**显示层**脱敏，见 §陷阱 9。）

**改了 unit 之后必须做的完整链路**（缺一则「写了 ≠ 上线」）：

1. `sudo -n systemctl daemon-reload`
2. `sudo -n systemctl restart hermes-skill-proxy.service`
3. **带重试**的健康检查（首次可能 Connection refused，见 §陷阱「restart 后必须带重试」）
4. 验证环境变量真的进了进程：
   `sudo -n tr '\0' '\n' < /proc/$(pgrep -f hermes-skill-proxy.py|head -1)/environ | grep HERMES_TIMEOUT`
5. `git commit` + `git push` **proxy repo**（模板也改了 → 不提交下次 pull 会退回）
6. 报告里给出**新 PID + 新 PID 的 environ 证据 + commit hash**

> ⚠️ **restart 前必须确认姊妹 KB 无并发作业** —— 两个 cron 同在 11:00，
> 姊妹 KB 的 e2e 探针可能正在跑，restart 会把它打成 `RemoteDisconnected`。
> 判据：`ps aux | grep -E "check_e2e|crawler|verify_kb"`。

---

## 五、2026-11-04 一轮「没复现 502」的判读

11-03 出现 4 次 502（proxy 300s < gateway 900s）；**11-04 同样在两个 KB 探针并发
（proxy 侧当日共 34 次请求）的情况下 0 次 502**，端到端 12/12 全 200，最慢 151.7s。

**结论不是「问题已修复」**，而是：

1. 11-03 的 502 是**上游 LLM 偶发停顿**触发的，**随机性**明显 —— 不是每次并发都复现
2. 因此**不能**用「某轮全绿」判定已修复，**也不能**用「某轮有 502」判定必然故障
3. 正确判据仍是 §陷阱 17 的归因法：
   - **elapsed 精确等于 proxy timeout**（300.0s / 120.1s）→ timeout 类
   - 再查 gateway 侧同一 start-time 戳**最终有没有出现** → 有=proxy 放弃太早 / 无=gateway 挂住
4. **同时并发两个 KB 的探针会加剧上游停顿** → 排障时**尽量错开**两个 cron 的探针时段
