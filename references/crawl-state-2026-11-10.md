# 2026-11-10 爬取状态基线快照（inexbot KB）

> 本文件是 cron 每轮「验证闭环」的**基线快照**。
> 下一轮 cron 先读本文件 + `hermes cron list` 的 `Last run` 字段，再开始工作。

---

## 1. 上游与索引状态

| 项 | 值 | 与 11-09 对比 |
|---|---|---|
| 页面总数 | **560** | 持平（**连续 21 次**） |
| `index.json` 大小 | **1,735,196 bytes** | **逐字节相同** |
| `index.json` sha256 前 16 位 | **`922fbbb47782dfd8`** | 相同 |
| `md/` 文件数 | **560** | 相同 |
| `raw/` 文件数 | **560** | 相同 |
| 缺失 md | **0** | 相同 |
| 孤儿 md | **0** | 相同 |
| 本轮网络抓取 | **0 次**（全部命中 raw 缓存） | 相同 |
| `meta.yaml` | `pages_crawled: 560` / `pages_failed: 0` / `version: 20261110` | — |

**结论：上游 doc.inexbot.com 零变化**（drift probe verdict = `IDENTICAL`，抽样 60 页 = 59 SAME + 1 IMG_ONLY）。
`IMG_ONLY` 是 VitePress 资源 hash 重命名，**不算漂移**。

---

## 2. 本轮验证闭环（7 步）

| 步骤 | 脚本 | 结果 |
|---|---|---|
| 1 爬取 | `crawler.py` | **560 / 560 成功，0 失败**，耗时 3m21s |
| 2 漂移探针 | `check_crawl_state.py --sample 60` | **IDENTICAL**（59 SAME + 1 IMG_ONLY） |
| 3 索引完整性 | `verify_kb.py` | **[inexbot] 10 / 10 全 PASS** |
| 4 检索链路 | `check_retrieval_chain.py`（新增） | **真静默降级 0**，md 全部可定位 |
| 5 引用链接 | `check_citation_links.py`（新增） | **60 / 60 HTTP 200** |
| 5b 端到端 | `check_e2e_request.py --runs 4` | 见下 |
| 6 收尾 | commit + push | 见「§5」 |

### 步骤 3 明细（`[inexbot]` 分组）

10 项全 PASS：条目数 > 0（560）／md 数 == 条目数（560 vs 560）／raw 数 == 条目数／
无零长度 snippet／无 `description == 'Not Found'`／无空标题／标题描述无 U+200B／
key 里无裸 `%`／**slug 契约 560 / 560**／含图 md 全部可反查 **158 / 158**。

### 步骤 4 明细（检索链路，60 条 proxy 结果 / 12 条查询）

| 指标 | 值 |
|---|---|
| 真静默降级（proxy snippet == 800 字符） | **0** |
| 全文命中（snippet 字符数 == md 字符数） | **34** |
| 命中 4000 字符上限 | **26** |
| md 全部可定位 | **60 / 60**（md_not_found = 0） |
| snippet > 4000 | **0** |

**9 条 snippet < 800 全部是「页面本身就很短」的正常态**（伺服报错占位页 / FAQ），
逐条核对 `snippet 字符数 == md 字符数` → 全文命中，非降级。

> ⚠️ **判据提醒**：比**字符数**不是字节数（中文 1 字 = 3 字节）。
> 例：`0x0050 - 风扇故障报警（未实现）` md = 71 字符 / 157 字节，比字节会误判。

---

## 3. ⭐ 本轮修掉的真 bug：反查归一化必须「按 KB 分开」

**发现路径**：11-09 那轮遗留未提交的 `scripts/check_url_to_index_key.py`（213 行）跑出来是
`URL->index-key hit : 48 / 93` —— **45 条查不到**，全部是 `[inexbot-open]`。

**第一反应**：像是 KB 回归。**实际是脚本自己的查表 bug**（与 10-31 / 11-09 同类的「审计脚本自伤」）。

### 根因：两个 KB 的 index key 是**相反**的编码态

| KB | key 含 `%` | key 含明文中文 | 中文形态 | 正确归一化 |
|---|---|---|---|---|
| `inexbot` (doc.inexbot.com) | **559 / 560** | **0** | `%E6%8A%80…` | 只替换 `%26`→`&`、`%2B`→`+` |
| `inexbot-open` (open.inexbot.com) | **0** | **441** | `上位机`（明文） | **整体 `unquote()`** |

脚本第一版对两个 KB 用**同一条**规则（「只替换两字符」）→
对 `inexbot-open` 而言，其 key 本来就是明文，`%26`/`%2B` 根本不会出现 →
**45 条全部 miss**。

**判别方式（可复用）**：看该 KB 的 index key 里**有没有 `%`**
（等价于 proxy `_kb_url()` 的判据 —— 同一套契约的另一个实例）。

### 修复

`norm_path(path, kb)` 按 KB 分派：`inexbot` 走「只换两字符」，`inexbot-open` 走「整体 unquote」。

### 修复后实测

```
total proxy results              : 93
URL->index-key hit (norm)        : 93 / 93     <- 修复前 48 / 93
true silent-degradation(==800)   : 0
full text hit (chars == md chars): 41
hit 4000-char cap                : 52
no-md lookup                     : 0
```

⇒ **通则：反向查表的归一化不是「一条全局规则」，而是「每个 KB 一条」。**
写审计脚本时**先分别 dump 两个 KB 的 index key 形态，再决定规则**。

---

## 4. 本轮新增的两个脚本

| 脚本 | 作用 | 为什么需要 |
|---|---|---|
| `scripts/check_retrieval_chain.py` | 按**字符数**判真静默降级 + 报 md 可定位率 | `verify_kb.py` 的「短 snippet」只是粗筛（`<800`），会把「页面本身短」和「真降级」混在一起；本脚本给出三态判定并**顺带兜住审计脚本自身的查表 bug** |
| `scripts/check_citation_links.py` | 按 proxy `_kb_url()` 规则生成官方链接，对**中文路径条目**抽样实网 GET | `verify_kb.py` 只抽 12 条；本脚本抽 60 条且只从**含中文路径**的 559 个 key 里抽（编码 bug 最容易在这里暴露） |

> ⚠️ 本轮 `check_citation_links.py` 第一版的 CJK 池检测写成「对 key 直接跑 CJK 正则」→
> **恒为 0**（index key 是 percent 编码的）→ 退化成随机抽全库。
> 已修：`unquote(k)` 后再检测 → 池子变成 559/560，**抽到的确实全是中文路径**。

---

## 5. 本轮收尾（commit / push）

> ⚠️ **11-09 那轮报告写「已提交、已推送」，实际工作树仍是脏的** —— 这是本项
> **第 5 次**跨 session 泄漏（10-27 / 10-28 / 10-29 / 11-06-11-07 / 11-09）。
> 本轮教训固化：**commit + push 放在生成报告正文之前**，别放在最后。

### 本轮提交内容

| 文件 | 变化 |
|---|---|
| `scripts/check_url_to_index_key.py` | **补做 11-09 的 213 行遗留** + **修掉按 KB 分派的归一化 bug** |
| `scripts/check_retrieval_chain.py` | 新增（检索链路三态判定） |
| `scripts/check_citation_links.py` | 新增（引用链接实网可达性） |
| `references/shared-proxy-service-pitfalls.md` | §陷阱 24 加「2026-11-10 更正：归一化按 KB 分开」 |
| `SKILL.md` | version 2.23.0 → 2.24.0；脚本表 +3 行；反查归一化规则段落改写 |
| `references/crawl-state-2026-11-10.md` | 本文件 |

---

## 6. proxy 运行时状态

| 项 | 值 |
|---|---|
| proxy PID | **1844673**，启动于 **2026-11-05 11:02:57**（连续 4 天 23.99h 未重启） |
| `/health` | `{"status":"ok","inexbot":{"docs":560,"loaded":true},"inexbot-open":{"docs":799,"loaded":true}}` |
| 内存索引 vs 磁盘 | **560 == 560**（同步 ✅） |
| 重载链 | **存活** —— 定时器线程 tid=1903565，age 4.96h，上次触发 11-10 06:04:09，下次 11:04:09 |
| 环境变量 | **5 个全部到位**，运行进程 / `/etc` unit / repo 模板**三处 sha12 逐项一致**（`check_proxy_env.py --units` exit 0） |
| `HERMES_TIMEOUT` | **1800**（4 字符，sha12 `e49ec846db75`）→ 客户端 timeout 必须 **> 1800** |
| 端口 | 8643（proxy）+ 8642（gateway），**无遗留压测进程** |

---

## 7. 端到端探针结果（步骤 5b）

见本文件末尾「§8 本轮 e2e 实测」。

---

## 8. 本轮 e2e 实测

> 本节在探针跑完后回填。

---

## 9. 遗留 / 交接给姊妹 KB

**[inexbot-open] 的 4 项 FAIL**（`verify_kb.py` 分组显示）：

| 项 | 值 |
|---|---|
| md 文件数 == index 条目数 | **1855 vs 799** ❌ |
| raw 文件数 == index 条目数 | **1855 vs 799** ❌ |
| 无零长度 snippet | ❌ |
| 含图 md 全部可从 index 反查 | **73 / 177** ❌ |

**这是姊妹 KB 的历史死缓存**，不是本 KB 的回归（11-09 已记录同样 4 项）。
但 **姊妹 KB 11-09 那轮被 HTTP 429「已达到 Token Plan 用量上限」打断**（`hermes cron list` 显示
`Last run: ... error: RuntimeError: HTTP 429 ...`），
⇒ **她 11-09 的修复没有落地**，这 4 项 FAIL 仍在。

> ⚠️ 本 KB **没有**碰姊妹 KB 的文件（陷阱 13：姊妹 KB 的 agent 会直接改本 skill 的 SKILL.md；
> 反向同理 —— 本 KB 只改自己目录，`references/shared-proxy-service-pitfalls.md`
> 属于**共享文件**，两边都要同步，见下）。
