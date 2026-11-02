# inexbot KB 爬取状态快照 — 2026-11-02

> 本文件记录 `inexbot`（doc.inexbot.com）知识库每日爬取的**基线与判读结论**。
> 姊妹 KB `inexbot-open` 的快照在
> `inexbot-open-knowledge-base/references/crawl-state-2026-*.md`。
> 上一份快照见 `crawl-state-2026-11-01.md`。

## 一、本轮结果

| 项目 | 值 |
|---|---|
| 爬取页数 | **558 / 558**（0 失败） |
| 耗时 | **2:57** |
| 网络请求 | **0**（全部命中 `raw/` 缓存，日志全「跳过（已存在）」） |
| index.json | **1,722,769 bytes**，sha256 `d565c39c433370c3e66ff8f1abd3e0c0cb42cf442f9fd88df922fca94d21d523` |
| index mtime | 2026-11-02 11:05:12 |
| md / raw 文件数 | 558 / 558（missing 0，orphan 0） |
| 漂移 verdict | **IDENTICAL** —— 抽样 25 页全部 `SAME` |
| proxy 进程 | PID **1792095**，启动于 2026-10-31 11:36:48（带 10-31 的 300s timeout 补丁） |
| 代理健康 | `/health` → `{"status":"ok","inexbot":{"docs":558},"inexbot-open":{"docs":799}}` |
| `.crawl_state.json` | `{"entries":558,"bytes":1722769,"sha256":"d565c39c…","checked_at":"2026-11-02T11:05:31"}` |

> ✅ index.json 与 2026-11-01 **逐字节相同**（sha `d565c39c…`）→ **558 篇连续多日零新增**（第 14 次持平）。
> ✅ index mtime（11-02 11:05:12）**晚于** proxy 启动时间（10-31 11:36:48）→ **不需要 restart proxy**。
> ✅ 姊妹 KB `inexbot-open` 仍为 799 docs。

## 二、验证闭环

### 2.1 索引完整性（`verify_kb.py`）

```
=== inexbot ===
  [PASS] index 条目数 > 0 — 558
  [PASS] md 文件数 == index 条目数 — 558 vs 558
  [PASS] raw 文件数 == index 条目数 — 558 vs 558
  [PASS] 无零长度 snippet（= 抓到 404 空壳页）
  [PASS] 无 description=='Not Found'
  [PASS] 无空标题
  [PASS] 标题/描述无零宽字符 U+200B
  [PASS] key 里无裸 %（否则引用链接必 404）
  [PASS] 所有 index key 都能定位到 md 文件 — 558/558
  [PASS] 含图 md 全部可从 index 反查 — 156/156
```

**逐条复核补充**（自写脚本，覆盖 `verify_kb.py` 未细分的项）：

| 项 | 值 |
|---|---|
| 零长度 snippet | **0** |
| `description == 'Not Found'` | **0** |
| 空标题 | **0** |
| 裸 / 畸形 `%`（`%` 后非两位十六进制） | **0** |
| 标题或描述含零宽字符（U+200B/200C/200D/FEFF） | **0** |
| slug 契约（复用 proxy `_md_slug_candidates()` + `.md`） | **558/558 解析成功** |
| **孤儿 md**（md 文件不可从 index 反查） | **0 / 558** |
| 检索链路 5 组查询的 800 字静默降级 | **0** |
| 检索结果 `%25` 双重编码计数 | **0** |
| 含 `&` 的 key（引用链接高风险） | **1**（`/zh/技术资料/通讯协议&地址码`） |

> 📌 **本轮新增检查项：孤儿 md 精确计数**（前几轮只记「missing 0 / orphan 0」的粗粒度）。
> 本轮用「index 可达 md 集合 vs `md/` 实际文件集合」做差集，
> 结果 **558 − 558 = 0 个孤儿** —— 本 KB 无死缓存，符合健康态。
> （姊妹 KB `inexbot-open` 有 1056 个历史死缓存孤儿，架构上不可达、不影响检索。）

### 2.2 短 snippet 逐条判别（静默降级 vs 页面本来就短）

判据：**proxy 检索结果**的 `content_snippet` 长度 `== 800` → **静默降级（BUG）**；
`< 800` 且 md 存在 → 页面本身就很短（正常）。

检索链路实测（5 组查询 × top-5 = 25 条）：

| 类别 | 条数 |
|---|---|
| 正常（读到正文） | **24** |
| **确实很短**（<200，md 存在） | **1**（`0x0050 - 风扇故障报警`，上游单行占位页） |
| **静默降级（恰好 800）** | **0** |
| 双重编码 URL（`%25`） | **0** |

> ⚠️ **注意区分两个不同的「800」**：
> - `crawler.py:448` 把 index 的 `content_snippet` **按设计**截到 800 字符
>   （`"content_snippet": content[:800]`）→ **index 层面 196 条恰好 800 是正常的**，
>   不是 BUG，只是摘要窗口。
> - **真正的静默降级判据在 proxy 检索结果上**：proxy 会去读 md 全文，
>   命中正文时长度是 1378–4000 字符（远超 800）。
>   **只有 proxy 返回恰好 800 才说明它没找到 md、回落到了 index 摘要。**
>   本轮 proxy 检索 25 条中 **0 条 == 800** ✅

### 2.3 proxy 内存索引 vs 磁盘 index.json（**token 级**比对）

| 项 | 值 |
|---|---|
| 磁盘条目 | 558 |
| 内存 `_index_data['inexbot']` | 558 |
| 内存 `_doc_scores['inexbot']` | 558 |
| 仅磁盘有 / 仅内存有 | **0 / 0** |
| **token 级不一致**（title + desc + content 三组） | **0** |

> ⚠️ **本轮修正了一个自写脚本的错误**：内存索引有两个结构 ——
> `_index_data['inexbot']` 是**原始 item dict**（`title` / `description` 是字符串），
> `_doc_scores['inexbot']` 才是**分词后的 token 集合**。
> 拿 `_index_data` 去比 token 会得到 558 条全不一致的**假阳性**。
>
> ⚠️ 另外必须用**同一套 jieba 规则（`len(w) >= 2`）**切词后比集合。
> 直接比 `mem[k]["title"] != disk[k]["title"]` → 恒为 True → 558 条全是假阳性。
>
> 唯一一条内存 `title_tokens` 为空的是 `/zh/操作手册/22.07版本/指令集手册`，
> 标题是 `"Q&A"`（3 字符，jieba 切成 `Q`/`&`/`A` 三个 1 字符 token）→ **良性**，
> index 层面「空标题」计数仍为 0。

### 2.4 端到端请求（proxy → gateway → LLM，第 5b 步）

`scripts/check_e2e_request.py --runs 4`（3 组查询 × 4 次 = **12 次**）：

```
[C1102 控制器 通讯接口 有哪些]   HTTP 200  136.2s / 183.9s / 150.4s / 32.8s
[冲压工艺 手册 参数设置]          HTTP 200  106.8s / 81.9s / ...
[示教器 操作手册 功能说明]        HTTP 200  ...
SUMMARY: 12/12 succeeded
```

> 🔴 **关键证据**：最慢一次 **183.9s**。
> 若 proxy 上游 timeout 还是修复前的 **120s**，这一批**至少 3 次必然 502**。
> → 10-31 的 `HERMES_TIMEOUT=300` 补丁**仍然承重**，不是摆设。
>
> ⚠️ **本轮耗时普遍偏高（32–184s）**，原因是姊妹 KB 的 cron 同时在跑
> 自己的 `check_e2e_request.py`（11:05 起），两个探针**并发打同一个 gateway（8642）**
> → 排队。**判据是状态码，不是耗时**（见 `kb-cron-verification-workflow.md`
> §「两个 KB 的 e2e 探针会并发打同一个 gateway」）。

### 2.5 proxy 服务状态（自 2026-10-31 11:36:48 本次进程启动起统计）

| 项 | 值 |
|---|---|
| `Unknown key name` 计数 | **0** |
| HTTP **500** 计数 | **0** |
| HTTP **502** 计数 | **0** |
| 进程环境变量 | `PROXY_PORT` / `HERMES_URL` / `HERMES_API_KEY` / `SKILL_NAME` **4 个全部到位** |
| 端口占用 | 仅 8643（proxy）+ 8642（gateway），无遗留压测进程 |
| proxy 仓库 | `a331618`，工作树 clean，与 `origin/main` 同步 |
| **重载链存活** | 定时器线程创建于 **2026-11-02 08:37:20**（`ps -L` 可见），5 小时周期正常重排 |

> ⚠️ journal 里 `Total: 1357 docs` 的重载记录本轮显示 **0**，但这**不代表重载链断了** ——
> systemd 下 stdout 是**块缓冲**（见 `proxy-runtime-freshness.md`），
> 小段输出会攒在用户态缓冲区。**真正的判据是 `ps -L` 看定时器线程的创建时间**：
> 线程 TID 1809513 创建于 11-02 08:37:20，早于本轮 11:02 的爬取
> 且晚于上一次重排，说明链条健在。
> 同时源码里的 `try/except/finally` 补丁（`schedule_reload()`）在运行进程中已生效。

### 2.6 引用链接实网可达性（补充抽样，含 `&` 风险区）

12 条抽样（含唯一一条含 `&` 的 key）→ **12/12 HTTP 200**。

> 含 `&` 的 key：`/zh/技术资料/通讯协议&地址码`
> → index.json 的 key 已是百分号编码，**直接拼接不要再 urlencode**，
> Markdown 链接里 `&` 原样保留（转义成 `%26` 反而会坏）。
> proxy 的 `_kb_url()` 对已含 `%` 的 key 用 `quote(path, safe="/%")` → **不双重编码**。

## 三、本轮发现的问题

### 🔴 1. 上一轮的成果**再次跨 session 泄漏**：工作树 3 个文件未提交

**现象**：11-01 那一轮的 cron 报告最后一节写「最终仓库状态干净，本地与远程 SHA 一致」，
但本轮 `git status` **独立实测**（不依赖上一轮报告的自述）显示：

```
 M SKILL.md                                    (version 2.12.0 -> 2.13.0)
 M references/kb-cron-verification-workflow.md (+42 行)
 M references/shared-proxy-service-pitfalls.md  (+41 行，陷阱 13)
```

**内容全部有效**（11-01 新增的「姊妹 KB agent 会改你 SKILL.md」陷阱 13 +
「两个 e2e 探针并发打同一 gateway」经验），已在本轮一并提交。

> 📌 **这就是 §0 / §0.5 的价值**：上一轮的**报告**说「已推送」，
> 但**代码**其实没进库 —— 只读报告会漏掉。
> **姊妹 KB 在自己那侧把它命名为「陷阱 14」**（见下节），两侧互补。

### ⚠️ 2. `shared-proxy-service-pitfalls.md` 两份副本**再次分叉**

| 文件 | sha1 前 12 | 陷阱数 |
|---|---|---|
| 本 KB 工作树（未提交） | `8f4064959139` | 1–13 |
| 姊妹 KB 工作树（未提交） | `272abb847972` | 1–**14** |

姊妹 KB 在其工作树里新增了 **陷阱 14**（cron 报告写「遗留：无」但工作其实没提交，
以及 `git status --short` 输出分类表）—— 那是**本轮我这边遇到的问题的镜像**，
内容有效且互补（我这边是「上一轮报告说已推送，实际没提交」）。

> ✅ **本轮处置**：把姊妹 KB 的 **陷阱 14** 增量补进本 KB 的副本，
> 保留本 KB 版本中姊妹 KB 没有的一句实测注解（「本轮正是靠这个发现对方补了长手册文件名陷阱」）。
> → 两份副本在 **陷阱 1–14 全部对齐**，仅剩叙述性措辞差异。

### 3. 两条判读经验（本轮实测补齐）

- **内存索引有两个结构**（`_index_data` vs `_doc_scores`）——
  比 token 必须用后者，用前者会得到 558 条全不一致的假阳性。
- **index 里的 800 截断不是 BUG** —— `crawler.py:448` 按设计截断；
  静默降级只在 **proxy 检索结果**上判定。

## 四、已提交 / 已推送

| 仓库 | commit | 状态 |
|---|---|---|
| `inexbot-knowledge-base` | 见 cron 报告 | 已 push，工作树干净 |
| `hermes-skill-proxy` | `a331618`（10-31） | 已 push，**已部署**，本轮未改动 |

SKILL.md 版本 2.13.0 → **2.14.0**，`last_verified: 2026-11-02`。

## 五、遗留事项

- **姊妹 KB 的 1056 个死缓存 md** 仍建议清理 → 属其 cron 职责
- 姊妹 KB 工作树有未提交改动（`SKILL.md` / `references/shared-proxy-service-pitfalls.md` /
  `?? references/cron-completion-discipline.md` / `?? references/e2e-request-probe.md`）
  → 属其 cron 职责，**本轮不代为提交**
- `verify_kb.py` 仍报 4 项 `[inexbot-open]` FAIL（md/raw 1855 vs 799、
  零长度 snippet、含图反查 73/177）→ 与 10-30/10-31/11-01 基线**逐项一致**，
  **不是新回归**；本 KB `[inexbot]` 分组 **11/11 全 PASS**
- 端口干净（仅 8643 + 8642），无遗留压测进程
