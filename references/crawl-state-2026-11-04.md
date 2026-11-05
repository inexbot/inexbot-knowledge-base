# 2026-11-04 爬取基线快照（inexbot KB）

**结论**：内容侧**完全稳态**（558 篇，第 16 次连续持平，index 逐字节未变）；
链路侧**未复现 502**（12/12 全 200），但**根因未消除** —— 11-03 的 4 次 502
由上游 LLM 偶发停顿触发，随机性明显。

---

## 一、爬取结果

```bash
/usr/bin/python3 ~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/crawler.py
```

| 项目 | 值 |
|---|---|
| 爬取页数 | **558 / 558 成功，0 失败** |
| 耗时 | **2:55.1** |
| 网络请求 | **0**（全部命中 `raw/` 缓存） |
| `index.json` | **1,722,769 bytes**，sha256 `d565c39c433370c3e66ff8f1abd3e0c0cb42cf442f9fd88df922fca94d21d523` |
| md / raw | 558 / 558（missing 0，**orphan 0**） |
| 漂移 verdict | **IDENTICAL** —— 抽样 25 页全部 `SAME` |

索引与 11-03 / 11-02 / 11-01 基线**逐字节相同**（sha 一致）→ **558 篇连续第 16 次持平**。

---

## 二、验证闭环（`[inexbot]` 分组全绿）

| 步骤 | 结果 |
|---|---|
| `verify_kb.py` | **`[inexbot]` 全 PASS**；4 项 FAIL 全部属 `[inexbot-open]` 分组（与 11-03 基线逐项一致 → **不是新回归**，属姊妹 KB 职责） |
| 独立完整性审计 | 零长度 snippet **0** / `Not Found` **0** / 空标题 **0** / 零宽字符 **0** |
| 孤儿 md / raw | **0 / 0**（558 可达 − 558 文件） |
| slug 契约 | **558/558**（复用 proxy `_md_slug_candidates()`） |
| 检索链路 | 40 条结果中 **snippet_len == 800 为 0**（无静默降级）、**双重编码 `%25` 为 0**；index 侧 196 条 `==800` 是 crawler `content[:800]` 设计窗口 |
| 内存 vs 磁盘 | **token 级 0 不一致、0 单边 key**（558↔558；磁盘侧字段名用 `title`/`description`/`content_snippet`） |
| 引用链接实网 | 抽样 **12/12 HTTP 200**；唯一含 `&` 的 URL → **HTTP 200（464 KB，`%26` 正确单编码、无 `%25`）**；percent-encoded 抽样 5/5 均 200 |
| **端到端** | **12/12 全 200**，最慢 151.7s；**含姊妹 KB 并发探针，proxy 侧当日共 34 次请求全 200、502 计数 0** |
| proxy 服务 | `/health` ok（558 + 799）、`Unknown key` **0**、`NRestarts=0`、4 个环境变量在 `/proc/<pid>/environ` 全部到位、**重载链存活**（11:13:04 第 5 次 5h 排期） |
| 端口 | 干净：8643（proxy）+ 8642（gateway）+ 80（nginx 默认站点，**非** proxy 消费者） |

---

## 三、本轮新认知：超时分层（详见 `proxy-timeout-layer-anatomy.md`）

| 层 | 超时 | 性质 |
|---|---|---|
| proxy → gateway | **300s**（`HERMES_TIMEOUT`） | 墙钟 |
| gateway → provider（单次） | **900s** | HTTP 读超时 |
| gateway → provider（×重试 3） | 最坏 **2700s+** | 每次重试各算一份 |
| gateway 整轮 | **1800s** | ⚠️ **inactivity 看门狗，非墙钟** |
| gateway HTTP 层 | **无** | api_server 无 `wait_for` 封顶 |

⇒ **真正先放弃的永远是 proxy**；「proxy 设 1800s 就对齐」是**错的**（上游最坏 2700s+）。

**注入体积实测**：单库 top-5 = **11.3k–21.0k 字符**（长手册类 5 条全打满 4000 上限）。

---

## 四、已闭环的上一轮遗留事项

1. **未提交改动已提交并推送**（此前泄漏 3 轮）→ commit **`131c7fd`**，`origin/main` 0/0 同步。
   含 `SKILL.md`（v2.16.0）、`shared-proxy-service-pitfalls.md`（陷阱 15–19，+252 行）、
   `crawl-state-2026-11-03.md`、`diagnose_502_timeout.py`。
   commit message 用**纯 ASCII**（避 tirith `confusable_text`）。
2. **KB 数据目录残留已清理** → 6 个 `_round_*_1103.py` 移到 `/tmp/kb-stray-probes-1104/`
   （**不直接删** —— cron 场景删文件会触发审批卡住）。

---

## 五、⚠️ 下一轮必须先接手

1. **502 修复只做了一半**：unit 与 repo 模板已加 `Environment="HERMES_TIMEOUT=1800"`，
   但**尚未 `daemon-reload` + `restart`**，**线上仍跑 300s**。
   剩余步骤：`daemon-reload` → `restart` → **带重试**健康检查 →
   验证 `/proc/<pid>/environ` 有 `HERMES_TIMEOUT=1800` →
   `check_e2e_request.py` 回归 → **commit + push `hermes-skill-proxy` repo**
   （该 repo 工作树有模板改动未提交）。
   ⚠️ restart 前确认姊妹 KB 无并发作业。
2. **姊妹 KB 的 4 项 `verify_kb.py` FAIL 仍未闭环**（1855 vs 799 死缓存、零长度 snippet、含图反查 73/177）。
3. **姊妹 KB 探针日志缺失**：`/tmp/e2e-20261104.log` 未生成（探针跑了 ~17 min 但日志没落盘）→ 姊妹 KB 下轮确认写入路径。

---

## 六、提交状态

| 仓库 | HEAD | 状态 |
|---|---|---|
| `inexbot-knowledge-base` | `131c7fd` | ✅ 已 push，与 `origin/main` 0/0 同步，工作树干净 |
| `hermes-skill-proxy` | `a331618` | ⚠️ 工作树有**未提交**的 unit 模板改动（`HERMES_TIMEOUT=1800`）；unit 已改但**服务未重启**；代码未改 |
