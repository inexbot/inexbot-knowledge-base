# 纳博特 KB（inexbot）基线快照 — 2026-11-18

> 本文件是 `inexbot-knowledge-base` skill 的**每日基线快照**。
> 上一轮：见 `crawl-state-2026-11-17.md`（11-17 那轮被 429 打断，成果由本轮补齐）。

---

## 1. 爬取结果

| 项 | 值 |
|---|---|
| 爬取页面 | **560**（成功 560 / 失败 0） |
| 网络抓取 | **0**（全部命中 raw 缓存，日志全是「跳过（已存在）」） |
| 耗时 | **2 分 59 秒**（11:03:51 → 11:03:56 索引构建完成） |
| index | `~/.hermes/kb/inexbot/index.json`，**1,735,196 bytes** |
| index sha256 | **`922fbbb47782dfd8`**（与 11-07 → 11-17 **连续 11 天逐字节相同**） |
| md / raw | **560 / 560**，孤儿 **0**、missing **0** |
| 上游页面总数 | **560 → 560（持平，连续 29 次）** |

- **上游零变化** ⇒ 页面总数、index 字节数、内容三者全部持平。
- 索引快照 `.crawl_state.json` 已更新为 `checked_at: 2026-11-18T11:04:22`。

### 1.1 漂移双路佐证（互不依赖）

| 判据 | 脚本 | 结果 |
|---|---|---|
| 内容级（抽样重抓比对） | `check_crawl_state.py` | **IDENTICAL**，25 页抽样 **25 SAME / 0 IMG_ONLY** |
| 条目数级（独立于本地缓存） | `check_sitemap_count.py` | 上游 zh `<loc>` **560** == 本地 **560**（总 `<loc>` 1107） |

> ⚠️ `check_sitemap_count.py` 是**唯一独立于本地 raw 缓存**的漂移判据
> —— `check_crawl_state.py` 的 diff 隐含假设「本地缓存本身是可信基线」。
> ⚠️ sitemap.xml 是**单行** XML，`grep -c "<loc>"` 会返回 **1**（行数不是出现次数），必须用 `re.findall`。

---

## 2. 验证闭环（§3/§4/§5 全部 PASS）

| 检查 | 脚本 | 结果 |
|---|---|---|
| 索引完整性对账 | `verify_kb.py` | **`[inexbot]` 10/10 PASS**（4 项 FAIL 全属姊妹 KB `[inexbot-open]` 分组） |
| 检索链路 | `check_retrieval_chain.py` | 真静默降级 **0**、md_not_found **0**；全文命中 34 + 4000 上限 26 + 短页全文 9 |
| 反查守卫 | `check_url_to_index_key.py` | **93/93** 命中、真静默降级 **0**、no-md **0** |
| 引用链接实网可达性 | `check_citation_links.py` | **60/60 全 200**（404 = 0、网络错误 = 0） |
| 短 snippet 二分类 | `check_short_snippet_class.py` | 132 条**全是「常见问题/伺服报错」占位页**，空壳页 **0**、md 无法定位 **0** |
| token 级一致性 | `check_token_consistency.py` | inexbot **0 处不一致**（560 == 560）；inexbot-open 亦 0 |
| proxy 环境变量 | `check_proxy_env.py --units` | 5 变量三处 sha12 **一致**（进程 environ / `/etc` unit / repo 模板） |
| 重载链 | `check_reload_timer.py` | **存活**，定时器线程 age 0.78h，下次重载 15:18:36；内存 560 == 磁盘 560 |
| journal（按进程启动时间切片） | `journalctl --since "2026-11-14 11:17:36"` | **0×500、0×502、0×Unknown key name** |

### 2.1 端到端（proxy → gateway → LLM，唯一能抓 timeout 类故障的检查）

见 §4。

---

## 3. ⭐ 本轮发现并处置的问题

### 3.1 跨 session 泄漏**第 9 次**复发（形态 A）

- **开局实测**：`git status -sb` 有 **2 个文件 `M`（96 行）** ——
  `references/crawl-state-2026-11-17.md`（+51/-4）与
  `references/shared-proxy-service-pitfalls.md`（+49）。
- 上一轮（11-17）报告的 §5「遗留」**明确列出了这两项**，但该轮随后被 HTTP 429 打断
  ⇒ **两处都没进版本库**（`Last run` 带 `error:` ⇒ 按 §0.6 其「已提交/已推送」结论一律作废）。
- **处置**：按 §0.7 时序**开局第一件事**补做 —— commit `7eec137` + push（§4.3）。

> ⚠️ 本轮再次印证 §0.6/§0.7：**带 `error:` 的上一轮，报告正文里的提交结论一律作废**。
> 本轮独立复核结论：11-17 的 `724ebd0` **push 真的落地了**
> （§0.9 直查远端 `ANCESTOR_YES`、双方同为 `724ebd0`），
> 但**「push 之后才产生」的两处补写没进库** ⇒ §0.8 形态 A。

### 3.2 §陷阱 38（push 被工具超时掐断）在**本轮**再次适用

本轮第一次 `git push` 返回 `GnuTLS recv error (-110)`（§陷阱 35 同族：通道问题，不是鉴权失败）。
按 §陷阱 38 的重试循环协议（**每次重试后都用 §0.9 直查远端判真伪**）：

- 第 1 次：`GnuTLS recv error (-110)` ⇒ §0.9 复核 = `ANCESTOR_NO` ⇒ **确实要重试**
- 第 2 次：**成功** `724ebd0..7eec137  main -> main` ⇒ 复核 = `PUSH_LANDED`
- 收尾直查远端：`merge-base --is-ancestor HEAD refs/remotes/sshcheck/main` = **YES**，
  `rev-parse HEAD` 与 `rev-parse refs/remotes/sshcheck/main` **同为 `7eec137`**

> 💡 **本轮再次确认**：`git status -sb` 的 `[ahead 1]` **不可信** ——
> push 失败后它显示 ahead；push 成功后它**仍然**可能显示 ahead（本地跟踪 ref 停在旧 sha）。
> ⇒ **唯一判据是 §0.9 直查远端**，且收尾时用
> `git update-ref refs/remotes/origin/main $(git rev-parse refs/remotes/sshcheck/main)`
> 把跟踪 ref 同步到远端真实 sha。

### 3.3 共享文件状态（§陷阱 27 / 37）

- 本 KB 的 `references/shared-proxy-service-pitfalls.md` 与姊妹 KB 工作树**逐字节相同**
  （两侧 sha1 均 `9e4287b1e39b2d77e5c66765ff868be4d19073c8`）⇒ **无需同步**。
- 结构自检 `check_shared_pitfalls_structure.py`：两侧均 **38 sections / 55 sub-headings / 1831 行**，
  报出的 3 条 `DUPLICATE_LINE` 是**正常的代码块复用**（`pgrep`/`git fetch`/`importlib` 命令行在
  不同陷阱里重复出现），**不是** §陷阱 31 的「并发 patch 拼坏」。
- 姊妹 KB 仓库仍有其自身的未提交文件（`references/.index-snapshot.json`、共享文件、
  `scripts/check_md_reachability.py` 等）—— 属**姊妹 KB 的收尾范围**，本 KB 未越界代劳。

---

## 4. git 收尾状态（§0.9 直查远端确认）

| commit | 内容 | push |
|---|---|---|
| `7eec137` | 补入 11-17 泄漏的 96 行（§陷阱 38 + §7.1/§7.2 判据） | ✅ `724ebd0..7eec137  main -> main`（第 2 次尝试，第 1 次 GnuTLS -110） |

- §0.9 直查远端：`ANCESTOR_YES`，HEAD 与远端**同为 `7eec137`**。
- 收尾 `git status -sb`：`## main...origin/main`（无 ahead、无 `M`、无 `??`）⇒ 工作树干净。
- HEAD 版本号 == 工作树版本号 == **2.33.0** ⇒ §0.7 检查通过。

---

## 5. ⭐ e2e 端到端实测（12 次请求）

见本文件 §6 的表格（探针跑完后补写）。

---

## 6. 待办 / 遗留

- **无**。上游零变化 ⇒ 无需 `refresh_drift.py`、**无需 restart proxy**
  （上游零变化时 restart 会打断姊妹 KB 正在跑的探针，风险 > 收益）。
- 姊妹 KB `inexbot-open` 侧仍有未提交文件，由其 cron 自行收尾。
