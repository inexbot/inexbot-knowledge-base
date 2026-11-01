# inexbot KB 爬取状态快照 — 2026-11-01

> 本文件记录 `inexbot`（doc.inexbot.com）知识库每日爬取的**基线与判读结论**。
> 姊妹 KB `inexbot-open` 的快照在
> `inexbot-open-knowledge-base/references/crawl-state-2026-*.md`。
> 上一份快照见 `crawl-state-2026-10-31.md`（含 10-31 修复的完整记录）。

## 一、本轮结果

| 项目 | 值 |
|---|---|
| 爬取页数 | **558 / 558**（0 失败） |
| 耗时 | **2:44** |
| 网络请求 | **0**（全部命中 `raw/` 缓存，日志全「跳过（已存在）」） |
| index.json | **1,722,769 bytes**，sha256 `d565c39c433370c3e66ff8f1abd3e0c0cb42cf442f9fd88df922fca94d21d523` |
| index mtime | 2026-11-01 11:03:52 |
| md / raw 文件数 | 558 / 558（missing 0，orphan 0） |
| 漂移 verdict | **IDENTICAL** —— 抽样 25 页全部 `SAME` |
| proxy 进程 | PID **1792095**，启动于 2026-10-31 11:36:48（23:29 elapsed，带 10-31 的 300s timeout 补丁） |
| 代理健康 | `/health` → `{"status":"ok","inexbot":{"docs":558},"inexbot-open":{"docs":799}}` |

> ✅ index.json 与 2026-10-31 **逐字节相同**（sha `d565c39c…`）→ **558 篇连续多日零新增**。
> ✅ index mtime（11:03:52）**晚于** proxy 启动时间（10-31 11:36:48）→ **不需要 restart proxy**。
> ✅ 姊妹 KB `inexbot-open` index 2,450,869 bytes，与 10-29/10-30/10-31 基线**逐字节相同**。

## 二、验证闭环

### 2.1 索引完整性（`verify_kb.py` + 逐条复核）

```
[PASS] index 条目数 > 0 — 558
[PASS] md 文件数 == index 条目数 — 558 vs 558
[PASS] raw 文件数 == index 条目数 — 558 vs 558
[PASS] 无零长度 snippet（= 抓到 404 空壳页）— 0
[PASS] 无 description=='Not Found' — 0
[PASS] 无空标题 — 0
[PASS] 标题/描述无零宽字符 U+200B — 0
[PASS] key 里无裸 % — 0
[PASS] 所有 index key 都能定位到 md 文件 — 558/558
[PASS] 含图 md 全部可从 index 反查 — 156/156
[PASS] 引用链接实网抽样全部 HTTP 200 — 12/12
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
| 检索链路 5 组查询的 800 字静默降级 | **0** |
| 检索结果 `%25` 双重编码计数 | **0** |

> ⚠️ **自己拼 md 文件名时会踩的坑**：proxy 的 `_md_slug_candidates()` 返回的是
> **不带 `.md` 后缀的 slug**，调用方要自己拼 `md_dir / f"{slug}.md"`。
> 漏拼后缀 → `resolved: 0/558` 的**假阳性**（看起来像契约断裂，其实是自己写错了）。
> 2026-11-01 实测踩了这个坑，已修正。

### 2.2 短 snippet 逐条判别（静默降级 vs 页面本来就短）

判据：`== 800` → **静默降级（BUG）**；`< 800` 且 md 存在 → 页面本身就很短（正常）。

| 类别 | 条数 |
|---|---|
| 正常（≥800 字符） | 196 |
| **确实很短**（<800，md 存在） | 362 |
| **静默降级（恰好 800）** | **0** |
| 短条目但 md 缺失 | **0** |

> ✅ 362 条短条目全部是伺服报错系列的一行占位页（FAQ 页），
> md 均存在、无 404 空壳页 —— 与 10-29/10-30/10-31 的判定一致。

### 2.3 proxy 内存索引 vs 磁盘 index.json（**token 级**比对）

| 项 | 值 |
|---|---|
| 磁盘条目 | 558 |
| 内存条目 | 558 |
| 仅磁盘有 / 仅内存有 | **0 / 0** |
| **token 级不一致** | **0** |

> ⚠️ 必须用**同一套 jieba 规则（`len(w) >= 2`）**切词后比集合。
> 直接比 `mem[k]["title"] != disk[k]["title"]` → 恒为 True → 558 条全是假阳性。
>
> 唯一一条内存 `title_tokens` 为空的是 `/zh/操作手册/22.07版本/指令集手册`，
> 标题是 `"Q&A"`（3 字符，jieba 切成 `Q`/`&`/`A` 三个 1 字符 token）→ **良性**，
> index 层面「空标题」计数仍为 0。

### 2.4 端到端请求（proxy → gateway → LLM，第 5b 步）

`scripts/check_e2e_request.py`（3 组查询 × 4 次 = **12 次**）：

```
[C1102 控制器 通讯接口 有哪些]   HTTP 200  46.4s / 71.0s / 69.7s / 144.7s
[冲压工艺 手册 参数设置]          HTTP 200  80.5s / 86.5s / 82.8s / 76.6s
[示教器 操作手册 功能说明]        HTTP 200  50.0s / 53.5s / 41.8s / 53.7s
SUMMARY: 12/12 succeeded
```

> 🔴 **关键证据**：最慢一次 **144.7s**。
> 若 proxy 上游 timeout 还是修复前的 **120s**，这一次**必然 502**。
> → 10-31 的 `HERMES_TIMEOUT=300` 补丁**仍然承重**，不是摆设。

### 2.5 proxy 服务状态（自 10-31 11:36:48 本次进程启动起统计）

| 项 | 值 |
|---|---|
| `Unknown key name` 计数 | **0** |
| HTTP **500** 计数 | **0** |
| HTTP **502** 计数 | **0** |
| 重载记录（`Total: 1357 docs`） | 2（重载链健在） |
| 端口占用 | 仅 8643（proxy）+ 8642（gateway） |

> ⚠️ journal 里 `500`/`502` 的**历史累计**计数（606 / 0）跨越多个旧进程，
> **必须按进程启动时间切片**统计，否则会把历史故障算到今天头上。

### 2.6 引用链接实网可达性（补充抽样，含 `&` 风险区）

10 条抽样（含唯一一条含 `&` 的 key）→ **10/10 HTTP 200**。

> 含 `&` 的 key：`/zh/技术资料/通讯协议&地址码`
> → index.json 的 key 已是百分号编码，**直接拼接不要再 urlencode**，
> Markdown 链接里 `&` 原样保留（转义成 `%26` 反而会坏）。

## 三、本轮发现并修复的问题

### 🔴 1. 上一轮的成果**跨 session 泄漏**：工作树 5 个文件 + 1 个新脚本未提交

**现象**：10-31 那一轮因**工具调用次数达上限**以 `RuntimeError` 收尾，
报告尾部自己都写了「§陷阱 10 的内容仅已写入两个 reference 文件」——
但**所有这些成果都只躺在工作树里，没有 commit**。

本轮 `git status` 实测（**独立跑，不依赖上一轮报告的自述**）：

```
 M SKILL.md                                    (version 2.10.0 -> 2.11.0)
 M references/controller-interface-specs.md
 M references/crawl-state-2026-10-31.md
 M references/kb-cron-verification-workflow.md
 M references/shared-proxy-service-pitfalls.md
?? scripts/check_e2e_request.py
```

**内容全部有效**（10-31 的 502 timeout 修复文档 + 新增的端到端探针脚本），
已在本轮连同 11-01 的实测数据一并提交。

> 📌 **这就是 §0「先读上一轮待办」与 §「工作树」的组合价值**：
> 上一轮的**报告**说「已推送」，但**代码**其实没进库 —— 只读报告会漏掉。

### ⚠️ 2. `shared-proxy-service-pitfalls.md` 两份副本**已分叉**

| 文件 | sha1 | 含 §陷阱 10 |
|---|---|---|
| 本 KB `inexbot-knowledge-base` | `5976db81…` | **有** |
| 姊妹 KB `inexbot-open-knowledge-base` | `1cf6cb5a…` | 无（只到 §陷阱 9） |

**本轮未越界处理** —— 姊妹 KB 的 cron 当时正在跑（PID 1799522 在跑它自己的
`crawler.py`，11:06 又起了它自己的 `check_e2e_request.py`），
按既定规矩「不要替姊妹 KB 提交」。留给姊妹 KB 自己的 cron 同步。

### 3. 两条判读经验（本轮实测补齐）

- **`_md_slug_candidates()` 不带 `.md` 后缀** —— 调用方必须自己拼，
  否则得到 `0/558` 的假阳性（详见 §2.1）。
- **journal 的 500/502 计数必须按进程启动时间切片** —— 跨进程累计会把
  历史故障误算到今天（详见 §2.5）。

## 四、已提交 / 已推送

| 仓库 | commit | 状态 |
|---|---|---|
| `inexbot-knowledge-base` | 见 cron 报告 | 已 push，工作树干净 |
| `hermes-skill-proxy` | `a331618`（10-31） | 已 push，**已部署**，本轮未改动 |

SKILL.md 版本 2.11.0 → **2.12.0**，`last_verified: 2026-11-01`。

## 五、遗留事项

- **姊妹 KB 的 `shared-proxy-service-pitfalls.md` 缺 §陷阱 10** → 属其 cron 职责
- 姊妹 KB 的 1056 个死缓存 md 仍建议清理 → 属其 cron 职责
- 姊妹 KB 工作树有未提交改动（`SKILL.md` / `references/crawl-state-2026-10-31.md` /
  `scripts/check_staleness.py` / `?? scripts/check_index_hygiene.py`）→ 属其 cron 职责
- 端口干净（仅 8643 + 8642），无遗留压测进程
