# 纳博特 KB 爬取基线快照（2026-11-27）

## 一、总体状态

| 项 | 值 |
|---|---|
| 页面总数 | **562**（与 11-26 持平，**连续 36 次**） |
| index.json | **1,764,336 bytes**，sha12 `726ba3ba259d`（与 11-25 / 11-26 **逐字节相同**） |
| md / raw | **562 / 562**，孤儿 0，缺失 0 |
| 爬虫 | **562/562 成功**，失败 0，耗时 **3m23s**（全部命中 raw 缓存，0 次网络抓取） |
| index mtime | 2026-11-27 11:05:07 |
| 漂移 | **IDENTICAL**，抽样 25 页 → **SAME 24 + IMG_ONLY 1** |
| sitemap 对账 | 上游 zh **562 == 本地 562**（total loc 1109） |
| url_suffix 分布 | `.html` **547** / `/index.html` **15** |
| proxy | PID **2016323**（自 11-20 未变），11:06:34 自动重载 → 内存 **562** == 磁盘 562 |
| 下线页面 | **0** |

## 二、逐项验证结果（全部通过）

| 检查 | 结果 |
|---|---|
| `crawler.py` | 562/562 成功，失败 0 |
| `check_crawl_state.py --sample 25` | **IDENTICAL**；抽样 **SAME 24 + IMG_ONLY 1**；空标题 0、ZWSP 0 |
| `check_sitemap_count.py` | 上游 zh **562 == 本地 562** |
| `check_citation_links.py` | **75/75 全 200**（含全部 15 个目录页），404 = 0 |
| `check_retrieval_chain.py` | **真静默降级 0**；md 全部可定位 |
| `check_url_to_index_key.py` | **93/93** 命中；静默降级 0；全文命中 40 / 4000 上限 53 |
| `check_token_consistency.py` | 两个 KB 均 **0 不一致**（inexbot 562/562、inexbot-open 832/832） |
| `check_short_snippet_class.py` | **132 条全是「伺服报错」占位页，空壳页 0**，md 定位 0 失败 |
| `check_proxy_env.py --units` | 5 个变量三处 sha12 **逐项一致**（exit 0） |
| `check_reload_timer.py` | **存活**；tid=2089395，上次触发 08:06:34，下次 13:06:34；内存/磁盘同步 |
| `check_url_forms.py` | **两个 KB 都是 DUAL（两套并存）** ⇒ **不改代码**，保留 `url_suffix` 兼容层 |
| `check_shared_pitfalls_structure.py` | 两个真实文件均 **PASS**（48 sections / 2647 lines） |
| `test_shared_pitfalls_structure.py` | 回归测试 **exit 0**：完好文件 → exit 0；末尾孤儿体 → exit 1（`DUPLICATE_BLOCK`） |
| `verify_kb.py` | `[inexbot]` **全 PASS**；4 项 FAIL **全属 `[inexbot-open]`** |
| journal（按 PID 2016323 启动时间切片） | **0×500、0×502、0×Unknown key name** |
| 端到端（12 次） | **12/12 全 200**，区间 **49.4–97.8s**，0 次 502 |

## 三、本轮的两个动作

### ① 跨 session 泄漏第 12 次复发 —— 开局即补做（§0.7 时戳自检命中）

11-26 那轮 `Last run` = **`ok`**（**根本没被打断**），
但独立复核（§0.9/§0.10：任何一轮的报告结论都要独立核验，不看 `Last run` 是 ok 还是 error）发现：

- 工作树有 **3 文件 175 行未入库**：`SKILL.md`（2.42.0 → **2.43.0**）+ `references/kb-cron-verification-workflow.md`（+20 行）+ **未跟踪** `references/shared-script-sync-direction.md`（152 行）
- 三处 mtime（**11:18:18 / 11:18:24 / 11:18:11**）**全部晚于**最后一次 commit（**11:16:15**）⇒ §0.7 时戳自检命中
- ⭐ 内容是 **11-26 那轮自己 §七 点名的新增物**（§陷阱 48 的配套文档）⇒ **正是 §陷阱 44 描述的形态**：报告点名的「新增物」排在 commit 之后 ⇒ 报告写「已推送」而文件从未入库 ⇒ 下次 `git pull` 静默丢掉
- ⭐ 判据佐证：`git show HEAD:SKILL.md | grep '^version:'` = **2.42.0**，
  工作树 = **2.43.0** ⇒ **两个版本号不一致 ⇒ 上一轮的规则没落地**

处置（**开局第一件事，不等爬虫**）：

```
git add -A                      ← §0.10：不能用 git add -u（不新增未跟踪文件）
git commit -m "docs(skill): add shared-script sync-direction discipline (trap 48 follow-up)"
git push git@github.com:inexbot/inexbot-knowledge-base.git main:main
```

- commit `87f64e1`（3 files changed, **175 insertions**）
- **SSH push 一次成功**：`efd6d9f..87f64e1  main -> main`
- §0.9 复核：`merge-base --is-ancestor` = **YES**；`rev-parse HEAD` 与 `refs/remotes/sshcheck/main` **同为 `87f64e1`**
- `git update-ref refs/remotes/origin/main <remote sha>` 同步了陈旧的本地跟踪 ref ⇒ `git status -sb` 恢复为无 ahead（避免下轮再被「假 ahead」误导）

> 💡 **本轮再次验证 §0.10 的核心命题**：`Last run = ok` **完全不能**作为
> 「上一轮成果已入库」的证据。**唯一判据是工作树此刻是否干净。**

### ② 「共享脚本同步方向」文档：两侧内容等价 ⇒ 无需合并

11-26 新增的 `references/shared-script-sync-direction.md` 两侧 sha1 不同
（本方 `b2137614e8d7…` vs 姊妹 `c1c38f8ed57c…`），
按 §陷阱 45 / 新文档的**五步纪律**做了逐层核对：

| 核对维度 | 本方 | 姊妹 | 判定 |
|---|---|---|---|
| 标题数 | 23 | 23 | 一致 |
| 表格行数 | 25 | 25 | 一致 |
| 围栏代码块数 | 1 | 1 | 一致 |
| 命令行集合 | — | — | **完全一致**（0 条独有） |
| 标题差异 | 仅 1 条 | 仅 1 条 | **视角措辞差异**（「我方踩坑全过程」vs「姊妹 KB 侧踩坑全过程」） |

⇒ **两侧是同一份内容的「各自视角」写法，不是内容分歧** ⇒ **不合并、不覆盖**
（覆盖会破坏姊妹文件里指向她自己脚本的路径语境）。
姊妹侧该文件已 commit（`3f3118c`）。

> ⚠️ **本轮踩到的判据细节**：
> 「集合差集」判据在**视角措辞不同**时会给出 16 行 / 15 行差异，
> **看起来像内容分歧，实际只是视角镜像** ⇒
> **必须再叠加一层「结构比对」（标题数 / 表格行数 / 代码块 / 命令集合）**才能定性。
> ⚠️ 这一点与新文档「五步纪律」是**互补**关系，不是替代关系。

## 四、上游「URL 形态」：仍是「两套并存」⇒ 不改代码

`check_url_forms.py`（URL 全部从 `index.json` 真实条目取，强制并入全部目录页）：

| KB | bare | `.html` | `/index.html` | 硬失败 | VERDICT |
|---|---|---|---|---|---|
| **inexbot**（42 条抽样） | **42/42** | **27/27** | **15/15** | 0 | **DUAL** |
| **inexbot-open**（30 条抽样） | 22/30 | 18/30 | — | 20 | **DUAL** |

⇒ 上游形态**未收紧**，处置原则 = **不改代码**，保留 `url_suffix` 兼容层（§陷阱 43）。

> ⚠️ 姊妹 KB 的 20 条「硬失败」是**该 KB 自身的旧页面下线**（`url_suffix` 分布为 `(none)`），
> 与**本 KB** 无关；本 KB **0 硬失败**。

## 五、待办 / 遗留

**无。** 下一轮需注意：

1. **跨 session 泄漏已是第 12 次** —— 根因始终是**时序**（commit/push 排在写报告之后）。
   本轮已把「改 → commit → push → 核验远端 → 写报告」固化为执行顺序。
2. 姊妹 KB `inexbot-open` 本轮**索引从 832 涨到 944**（其自身爬取），
   `verify_kb.py` 的 4 项 FAIL（md/raw 2077 vs index 944、34 条零长度 snippet）
   **仍属姊妹 KB 的重建中间态**，**非本 KB 回归**；本 KB `[inexbot]` 分组**全 PASS**。
3. `references/shared-script-sync-direction.md` 的**视角措辞差异**是设计如此，
   不要被「集合差集非零」误判成需要合并（见 §三 ②）。
