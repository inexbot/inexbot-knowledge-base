# 2026-11-11 爬取状态基线快照（inexbot KB）

> 本文件是 cron 每轮「验证闭环」的**基线快照**。
> 下一轮 cron 先读本文件 + `hermes cron list` 的 `Last run` 字段，再开始工作。

---

## 1. 上游与索引状态

| 项 | 值 | 与 11-10 对比 |
|---|---|---|
| 页面总数 | **560** | 持平（**连续 22 次**） |
| `index.json` 大小 | **1,735,196 bytes** | **逐字节相同** |
| `index.json` sha256 前 16 位 | **`922fbbb47782dfd8`** | 相同（与 11-07 / 11-08 / 11-09 / 11-10 同值） |
| `md/` 文件数 | **560** | 相同 |
| `raw/` 文件数 | **560** | 相同 |
| 缺失 md | **0** | 相同 |
| 孤儿 md | **0** | 相同 |
| 本轮网络抓取 | **0 次**（全部命中 raw 缓存） | 相同 |
| `meta.yaml` | `pages_crawled: 560` / `pages_failed: 0` / `version: 20261111` | — |

**结论：上游 doc.inexbot.com 零变化**（drift probe verdict = `IDENTICAL`，抽样 60 页 = 59 SAME + 1 IMG_ONLY）。
`IMG_ONLY` 是 VitePress 资源 hash 重命名，**不算漂移**。

### ⭐ 新增独立佐证：上游 sitemap 直接计数

本轮第一次直接抓 `https://doc.inexbot.com/sitemap.xml` 并按 `<loc>` 计数：

```
total loc : 1107
zh  loc   : 560
zh unique: 560
```

⇒ **上游 sitemap 的 zh 条目数 = 560，与本地 index 条目数 1:1 相等** ——
这是**不依赖本地缓存**的独立「上游页面总数」证据（此前只靠 crawl state 的逐字节 diff 间接推断）。

> ⚠️ **坑**：sitemap.xml 是**单行** XML，`grep -c "<loc>"` 会返回 **1**（行数，不是出现次数）。
> 必须用 `re.findall(r'<loc>([^<]+)</loc>', xml)` 计数。

---

## 2. 本轮验证闭环（7 步）

| 步骤 | 脚本 | 结果 |
|---|---|---|
| 1 爬取 | `crawler.py` | **560 / 560 成功，0 失败**，耗时 2m33s |
| 2 漂移探针 | `check_crawl_state.py --sample 60` | **IDENTICAL**（59 SAME + 1 IMG_ONLY），孤儿 md 0 |
| 3 索引完整性 | `verify_kb.py` | **[inexbot] 10 / 10 全 PASS** |
| 4 检索链路 | `check_retrieval_chain.py` | **真静默降级 0**，md 全部可定位 |
| 5 引用链接 | `check_citation_links.py --sample 60` | **60 / 60 HTTP 200** |
| 5b 端到端 | `check_e2e_request.py` | 见「§7 本轮 e2e 实测」 |
| 6 收尾 | commit + push | 见「§8 本轮收尾」 |

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
| 短页（本身 < 800 字符）全文命中 | 9 |

> ⚠️ **判据提醒**：比**字符数**不是字节数（中文 1 字 = 3 字节）。
> 例：`0x0050 - 风扇故障报警（未实现）` md = 71 字符 / 157 字节，比字节会误判。

### 步骤 4b：反查守卫（`check_url_to_index_key.py`）

```
total proxy results              : 93
URL->index-key hit (norm)        : 93 / 93
true silent-degradation(==800)   : 0
full text hit (chars == md chars): 41
hit 4000-char cap                : 52
no-md lookup                     : 0
```

⇒ 11-10 修掉的「归一化按 KB 分派」在**本轮持续成立**（两个 KB 共 93 条全命中）。

---

## 3. token 级比对（proxy 内存索引 vs 磁盘 index.json）

| KB | memory | disk | key 集合相等 | token 级不一致 |
|---|---|---|---|---|
| `inexbot` | 560 | 560 | ✅ | **0** |
| `inexbot-open` | 799 | 799 | ✅ | **0** |

（字段名用 `title` / `description` / `content_snippet`，切词规则 `len(w) >= 2` —— 见陷阱 18。）

---

## 4. proxy 运行时状态

| 项 | 值 |
|---|---|
| proxy PID | **1844673**，启动于 **2026-11-05 11:02:57**（连续 6 天 0.08h 未重启） |
| `/health` | `{"status":"ok","inexbot":{"docs":560,"loaded":true},"inexbot-open":{"docs":799,"loaded":true}}` |
| 内存索引 vs 磁盘 | **560 == 560**（同步 ✅） |
| 重载链 | **存活** —— 定时器线程 tid=1915605，age **4.01h**，上次触发 **11-11 07:04:22**，下次 **12:04:22** |
| 环境变量 | **5 个全部到位**，运行进程 / `/etc` unit / repo 模板**三处 sha12 逐项一致**（`check_proxy_env.py --units` exit 0） |
| `HERMES_TIMEOUT` | **1800**（4 字符，sha12 `e49ec846db75`）→ 客户端 timeout 必须 **> 1800** |
| 端口 | 8643（proxy）+ 8642（gateway），**无遗留压测进程** |
| proxy 源码 mtime vs 进程启动 | 补丁已在线上（进程未重启 → 说明 11-05 之后无新补丁） |

---

## 5. 本轮修掉的真 bug：11-10 那轮的「已提交」结论是错的（第 5 次跨 session 泄漏）

### 现场

11-10 的 `hermes cron list` 记录：

```
Last run: 2026-11-10T11:28:39 error: RuntimeError: # 纳博特 KB 爬虫与验证闭环报告 — 2026-11-10
```

⇒ **`error:` 前缀 = 那一轮被中断**（HTTP 429「已达到 Token Plan 用量上限」）。
而那份报告正文第 5 节写着：

> 「### 提交与推送（已核验干净）」「✅ `c539eef..36e50f7`」

**实测本轮 `git status -sb`**：

```
## main...origin/main
 M SKILL.md
 M references/kb-cron-verification-workflow.md
 M references/shared-proxy-service-pitfalls.md
 M scripts/check_citation_links.py
```

⇒ **4 个文件 / 168 行根本没进版本库** —— 报告里那句「已核验干净」是**假的**。

**这就是「跨 session 泄漏」的第 5 次复现**（10-27 / 10-28 / 10-29 / 11-06-11-07 / 11-09 / 11-10）。
根因**从来不是「忘了做」**，而是**做的顺序**：11-10 那轮把 commit+push 放在了
「生成报告正文之后」，报告写完就被 429 打断 → 收尾动作没跑。

### ✅ 固化到 skill 的硬规则（本轮已写入 `references/kb-cron-verification-workflow.md`）

| 顺序 | 风险 |
|---|---|
| ❌ 「改 → 写报告 → commit → push」 | 报告长时**很可能在 commit 之前被打断**（429 / 额度耗尽）⇒ 改动泄漏 |
| ✅ 「改 → **commit → push** → 写报告」 | 收尾先完成；报告里写的 commit hash **当场就是真的** |

⇒ **硬规则：commit + push 放在生成报告正文之前。**

### ⚠️ 更细一层：**11-10 报告写「已提交」时的 `Last run` 已经是 `error:`**

⇒ 下一轮 cron 读 `Last run` 时，**只要看到 `error:`，就把它正文的「已提交/已推送」一律当作未完成**，
独立重跑 `git status -sb` 核对。**报告里的 commit hash 只证明「那个 commit 在库里」，
不证明「工作树此刻干净」。**

---

## 6. 本轮补做的 11-10 遗留（4 文件 / 168 行）

| 文件 | 内容 |
|---|---|
| `references/shared-proxy-service-pitfalls.md` | **§陷阱 26**（筛选/检测谓词作用在已编码字符串上 → 恒为空集 → 脚本静默降级测错东西；「兜底分支是在藏错，不是稳健」）+ **§陷阱 27**（共享文件同步后还会再分叉 → sync 必须放在所有编辑之后，sha1 核对放最后一步） |
| `references/kb-cron-verification-workflow.md` | §4 加「比字符数不是字节数」+「反查 md 归一化按 KB 分派」+「筛选谓词也要先解码」三段；§收尾加「收尾时序」小节（双仓库独立核验命令） |
| `scripts/check_citation_links.py` | **CJK 池为空时直接 FAIL 退出**（不再静默退化成全库随机抽）+ 文档化陷阱 26 |
| `SKILL.md` | 陷阱索引补 §陷阱 26 / §陷阱 27 |

---

## 7. 本轮 e2e 实测（步骤 5b）

> 本节在探针跑完后回填。

---

## 8. 本轮收尾（commit / push）

> 本轮**把 commit + push 放在生成报告正文之前**（11-10 教训）。

### 本轮提交内容

| 文件 | 变化 |
|---|---|
| `references/shared-proxy-service-pitfalls.md` | §陷阱 26 + §陷阱 27（补做 11-10 遗留） |
| `references/kb-cron-verification-workflow.md` | §4 三段补充 + §收尾「收尾时序」小节（补做 11-10 遗留） |
| `scripts/check_citation_links.py` | CJK 池为空 → FAIL 退出（补做 11-10 遗留） |
| `SKILL.md` | version 2.24.0 → 2.25.0；陷阱索引 +§26/§27；新增 11-11 快照行 |
| `references/crawl-state-2026-11-11.md` | 本文件 |

---

## 9. 遗留 / 交接给姊妹 KB

**`[inexbot-open]` 的 4 项 FAIL**（`verify_kb.py` 分组显示）：

| 项 | 值 |
|---|---|
| md 文件数 == index 条目数 | **1855 vs 799** ❌ |
| raw 文件数 == index 条目数 | **1855 vs 799** ❌ |
| 无零长度 snippet | ❌ |
| 含图 md 全部可从 index 反查 | **73 / 177** ❌ |

**这是姊妹 KB 的历史死缓存**，不是本 KB 的回归（11-09 / 11-10 已记录同样 4 项）。
姊妹 KB 11-11 也在 11:04:36 重建了自己的 index（size 2,450,869 不变），
⇒ **她的 4 项仍然没修**。本 KB **未改动**她的 KB 数据文件。

> ⚠️ 姊妹 KB 的 cron 与本 cron 同在 11:00，**会并发写同一个 proxy repo 和共享 reference 文件**。
> 本轮按 **§陷阱 27 的时序**处理：所有内容编辑完成 → 才 `cp` 共享文件 → commit → push → **最后**核对 sha1。

---

## 10. 本轮新增的可复用经验

### ⭐ 「上游 sitemap 条目数」是一个**独立**于本地缓存的漂移判据

`check_crawl_state.py` 的 drift 判定依赖「本地 raw 缓存 vs 上游重抓」的对比，
隐含假设是**本地缓存本身是可信基线**。直接数上游 sitemap 的 zh `<loc>` 个数，
是**不依赖任何本地缓存**的第三方证据：

```python
import re
x = open("/tmp/sitemap.xml", encoding="utf-8").read()
locs = re.findall(r"<loc>([^<]+)</loc>", x)
zh = [u for u in locs if "/zh/" in u]
print(len(locs), len(zh), len(set(zh)))   # 1107 / 560 / 560
```

⇒ 本地 index 560 == 上游 zh 560 ⇒ **上游无新增、无下线**。
建议以后每轮都顺手跑（成本 < 1s，网络一次 GET）。

### ⚠️ `grep -c "<loc>"` 在单行 XML 上返回 **1**

sitemap.xml 是**单行**（无换行）→ `grep -c` 统计的是**行数**不是**出现次数**。
必须用 `re.findall` 或 `grep -o ... | wc -l`。
