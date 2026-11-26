# 2026-11-25 基线快照（inexbot KB）

> 本文件是 2026-11-25 cron 轮次的基线快照。**下一次 cron 开盘请先读本文件**，
> 再读 `SKILL.md` 的「编排铁律」小节。

## 一、总览

| 项 | 值 |
|---|---|
| 上游状态 | ⭐ **新增 1 页 → 561 → 562**（连续 34 次持平后首次增长） |
| 新页 | `web协作示教系统操作手册`（`/zh/操作手册/web协作示教系统操作手册`） |
| index | **1,764,336 bytes**（sha12 `726ba3ba259d`；前值 1,756,935 / `89baf46193cd`） |
| md / raw | **562 / 562**（孤儿 0，缺失 0） |
| 爬虫 | 562/562 成功，失败 0，耗时 3m39s |
| proxy | PID **2016323**（自 11-20 未变），11:06:08 自动重载 → 内存 **562** == 磁盘 562 |
| 端到端 | **12/12 全 200**（本轮自跑：49.2–166.3s，0 次 500/502） |

## 二、逐项验证结果

| 检查 | 结果 |
|---|---|
| `crawler.py` | **562/562 成功**，失败 0 |
| `check_crawl_state.py` | verdict `CHANGED: 561 -> 562`；漂移抽样 **25/25 SAME**；missing md 0 / orphan md 0；空标题 0；ZWSP 0；health OK |
| `check_sitemap_count.py` | 上游 zh **562** == 本地 **562**（修爬后对账通过）；总 loc 1109 |
| sitemap 逐条 diff | **NEW 1 / REMOVED 0**（新增页 = web协作示教系统操作手册） |
| `check_citation_links.py` | **75/75 全 200**（含全部 15 个目录页），404 = 0，网络错误 = 0 |
| `check_retrieval_chain.py` | **真静默降级 0**；全文命中 33 / 4000 上限 27 / 短页全文 8；md 全部可定位 |
| `check_url_to_index_key.py` | **93/93** 命中；静默降级 0 |
| `check_token_consistency.py` | 两个 KB 均 **0 token 级不一致**（inexbot 562 / inexbot-open 832） |
| `check_short_snippet_class.py` | **PASS**：132 条短 snippet 全部是「常见问题/伺服报错」占位页，**空壳页 0** |
| `check_proxy_env.py --units` | **exit 0**：5 个变量三处（进程 environ / `/etc` unit / repo 模板）sha12 逐项一致 |
| `check_reload_timer.py` | **重载链存活**，11:06:08 触发，下次 16:06:08；内存/磁盘**同步** |
| `check_url_forms.py` | **两个 KB 都是 DUAL（两套并存）** ⇒ **不改代码**，保留 `url_suffix` 兼容层 |
| `verify_kb.py` | `[inexbot]` **10/10 全 PASS**；4 项 FAIL **全属 `[inexbot-open]`**（姊妹 KB 重建中间态） |
| journal（按 PID 2016323 启动时间切片） | **0×500、0×502、0×Unknown key name** |
| 端到端（本轮实跑） | **12/12 全 200** —— C1102×4（57.5–68.1s）/ 冲压×4（49.2–66.8s）/ 示教器×4（78.1–166.3s），**0 次 500/502** |
| 姊妹 KB 同时段 e2e | 也 **11/11 全 200**（48.7–236.3s）⇒ 本轮**无共享链路故障** |
| 新页检索实测 | 进程内检索命中 **rank #1**，`snip_chars=4000`（正文命中，非 800 摘要） |

## 三、本轮的两个动作

### ① 跨 session 泄漏第 10 次复发（已在开局补做）

11-24 那轮 `Last run` 是 `ok`，但工作树里仍有 **2 文件 112 行**未入库：

```
 M SKILL.md                                    |  10 +++
 M references/kb-cron-verification-workflow.md | 102 ++++++
```

**§0.7 时戳自检命中**：两处改动 mtime `11:21:02` / `11:20:53` **晚于**最后一次 commit 时间 `11:18:29`
⇒ 改动是「报告写完之后才补的」⇒ **必然被下一轮漏掉**。

处置（开局即做，**在爬取之前**）：
- `git add -A` → commit `02551ee` → SSH push **一次成功**（`427e56a..02551ee`）
- §0.9 直查远端复核：`merge-base --is-ancestor` = **YES**，`rev-parse HEAD` 与
  `rev-parse refs/remotes/sshcheck/main` **同为 `02551ee1a6b433845ebcec83e1a2b9f886edb658`**
- ⚠️ 本轮 push **全程走 SSH**（HTTPS :443 在 11-22 实测为 DEGRADED）

### ② 修掉一个「恒定红灯」的审计脚本（`check_shared_pitfalls_structure.py`）

**症状**：该脚本对**两个 KB 的真实文件都报 exit 1**，7 条 `DUPLICATE_LINE` flag。

**归因**：旧实现只做「按行去重」，把**两类完全正常的重复**也报成损坏：
1. **围栏代码块里的重复命令行**（如 `git merge-base --is-ancestor …` 在多个陷阱里各出现一次）——**7 条里 5 条是这类**
2. **跨节引用的归属注记**（「本条由姊妹 KB 在 X 日实测并写入…」，有意在两节各留一份）

⇒ 独立分析证明**结构其实是完好的**：46 节、**重复标题 0**、**重复正文块 0**、**截断 0**、编号无缺口。
⇒ 且旧脚本算出了 `block_hashes` 却**从未使用** ⇒ 正是 §陷阱 40「定义了但没接进调用链」的**假探针**。

**修法**：重写为**直接对准真正的损坏形态**：
`DUPLICATE_HEADING` / `DUPLICATE_SECTION`（只比正文不含标题）/ `EMPTY_SECTION`（任意节，不只最后一节）/
`INTERLEAVED_BODY`（按重叠比例，天然容忍「一两句在多节重复」）/ `SUSPECT_ORPHAN`，并**跳过围栏代码块**。

**验收（§陷阱 46：新脚本入库前必须真跑）**：6 个合成样本全部通过 ——
`real`=0、`legit`(代码块重复命令)=0、`duphead`=1、`dupsec`=1、`trunc`=1、`interlv`=1；
对两个 KB 真实文件均 **PASS / exit 0**。

## 四、上游「URL 形态」

仍是 **DUAL（两套并存）**：

| KB | 抽样 | bare | `.html` | `/index.html` | 硬失败 |
|---|---|---|---|---|---|
| inexbot | 42 | 42/42 | 27/27 | 15/15 | 0 |
| inexbot-open | 30 | 30/30 | 25/25 | 0 | 5（仅 `.html` 形态，bare 全 200） |

⇒ **不改代码**，保留 `url_suffix` 兼容层（§陷阱 43：上游形态是反复漂移的变量，
一周内切过两次且方向相反 ⇒ 裸形态可用**绝不**构成删兼容层的依据）。

## 五、姊妹 KB（inexbot-open）状态

- `verify_kb.py` 的 4 项 FAIL **全属 `[inexbot-open]`**：md 1890 vs index 832、raw 1890 vs 832、
  零长度 snippet、含图 md 反查 73/177
- 判读：姊妹 KB 的 `index.json` 在 **11:05:22** 被重写（md/raw 1890 ⇒ 是它的**重建中间态**），
  **不是本 KB 回归**，也**不是**新的上游故障
- 共享 pitfalls 文件两侧**已对齐**：`HEAD` blob 同为 `4fb5ba43a01a`，工作树 sha1 同为 `0cc7ca1aab10`，
  2523 行 / 46 节 —— **无需同步**

## 六、遗留

**无。** 本轮所有改动（含跨 session 泄漏的补做 + 审计脚本重写）均已
**commit + push + §0.9 远端复核落地**。
