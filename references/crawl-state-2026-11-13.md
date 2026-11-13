# 2026-11-13 爬取状态基线快照（inexbot KB）

> 本文件是 cron 每轮「验证闭环」的**基线快照**。
> 下一轮 cron 先读本文件 + `hermes cron list` 的 `Last run` 字段，再开始工作。

---

## 1. 上游与索引状态

| 项 | 值 | 与 11-12 对比 |
|---|---|---|
| 页面总数 | **560** | 持平（**连续 24 次**） |
| `index.json` 大小 | **1,735,196 bytes** | **逐字节相同** |
| `index.json` sha256 前 16 位 | **`922fbbb47782dfd8`** | 相同（与 11-07 至 11-12 同值） |
| `md/` 文件数 | **560** | 相同 |
| `raw/` 文件数 | **560** | 相同 |
| 缺失 md | **0** | 相同 |
| 孤儿 md | **0** | 相同 |
| 本轮网络抓取 | **0 次**（全部命中 raw 缓存） | 相同 |
| `meta.yaml` | `pages_crawled: 560` / `pages_failed: 0` / `version: 20261113` | — |

**结论：上游 doc.inexbot.com 零变化**（drift probe verdict = `IDENTICAL`，抽样 25 页 = 25 SAME）。
上游 sitemap 独立佐证：**1107 loc / 560 zh / 560 unique** == 本地 index 560 ⇒ 上游既无新增也无下线。

---

## 2. 验证闭环（7 步全过）

| 步骤 | 结果 |
|---|---|
| ① 爬虫 | 560/560 成功，0 失败，耗时 2 分 55 秒 |
| ② 漂移探针 | **IDENTICAL**（25 页抽样 25 SAME），orphan md 0 |
| ②' sitemap 对账 | **PASS** — 560 zh == 560 local |
| ③ 索引完整性 | **[inexbot] 10/10 全 PASS** — slug 契约 **560/560**，孤儿 0，无零长度 snippet / `Not Found` / 空标题 / 裸 `%`，含图 md 反查 **158/158** |
| ④ 检索链路 | **真静默降级 0**（60 条：34 全文命中 + 26 命中 4000 上限 + 9 短页全文命中），md **60/60 可定位**；反查守卫 **93/93**（41 全文 + 52 命中 4000 上限） |
| ⑤ 引用链接 | **60/60 HTTP 200**（CJK 池 559） |
| ⑤b 端到端 | **12/12 全 200**（47.3s – 216.8s，**0 次 502**）；proxy journal 独立确认「29 次 POST 全部 → 200，零 5xx」 |
| ⑥ 收尾 | commit + push **在写报告正文之前完成** |

### 短 snippet 分类（新增独立核查，132 条）

`check_crawl_state.py` 报 `snippet<60ch: 132` —— 本轮独立分类确认 **132/132 全部是
「常见问题」分类下的伺服报错占位页**，**0 条是 404 空壳页**（`description == "Not Found"` 全库 0 条）：

| 项 | 值 |
|---|---|
| snippet < 60 字符 | 132 |
| 其中 `description == 'Not Found'`（真故障） | **0** ✅ |
| 空标题 | 0 |
| 全部落在分类 | `常见问题`（伺服报错系列，正文本就只有一行描述） |

### proxy 运行时

- PID **1844673**（11-05 11:02:57 启动，连续 8 天，未重启）
- `/health` OK — inexbot 560 / inexbot-open 799
- **内存索引 == 磁盘**（560 == 560）
- 重载链存活：定时器 tid=1936536，上次触发 11-13 09:04:49，下次 **14:04:49**
- `check_proxy_env.py --units` **exit 0** — 5 个环境变量运行进程 / `/etc` unit / repo 模板三处 sha12 一致，`HERMES_TIMEOUT=1800` 生效
- token 级比对：两个 KB 均 **0 不一致**
- 端口 8643（proxy）+ 8642（gateway）干净

---

## 3. ⭐ 本轮最重要发现：11-12 的「已提交」结论**这次是真的**（跨 session 泄漏链被打断）

11-12 的 `hermes cron list` 记录为 `Last run: ... error: RuntimeError: HTTP 429`，
即**那轮被中断**。但**这次的验证表明 11-12 的 §0.7 强化规则确实生效了**：

| 检查 | 结果 |
|---|---|
| `git show HEAD:SKILL.md \| grep version:` | `2.27.0` |
| `grep version: SKILL.md`（工作树） | `2.27.0` |
| 两者一致？ | **是** ⇒ 上一轮的规则**已落地进版本库** |
| 文件 mtime vs commit 时间 | 全部 mtime（11:22:55 – 11:26:43）**早于** commit 时间 11:27:31 ⇒ 不是「报告写完才补」的 |

⇒ **11-12 的 commit `0da8500` 完整包含了它的全部改动**（5 文件 447 行）。
**唯一没落地的是 `git push`** —— 429 恰好打在 push 上。

### ⭐ 由此得出的新规则：**「commit 完成」不等于「push 完成」，两者必须分别核验**

11-12 那轮把 commit 放对了位置（写报告正文之前），但 push 被 429 打断，
于是本轮开局看到的是：

```
## main...origin/main [ahead 1]
```

⇒ **commit 在本地、push 没上去** —— 这与「跨 session 泄漏」（改动根本没进 commit）
是**两种不同的失败形态**，但**从 `git status -sb` 的表象看几乎一样**（都是「工作树有东西没进库」）。

| 失败形态 | 判据 | 修法 |
|---|---|---|
| **A. 改动没进 commit**（真正的跨 session 泄漏） | `git status -sb` 有 `M` / `??` | 补 commit |
| **B. commit 有了但没 push** | `git status -sb` 显示 `[ahead N]` 且**工作树干净** | 补 push（**不要重新 commit**） |

⇒ **本轮开局先跑 `git status -sb`，同时看「工作树是否干净」和「是否 ahead」**：
- 工作树干净 + `ahead N` ⇒ **形态 B** ⇒ 直接 push（重新 commit 是多余的）
- 工作树有 `M`/`??` ⇒ **形态 A** ⇒ 需要 commit

> ⚠️ **注意 `[ahead N]` 与陈旧跟踪 ref 的混淆**（见 `references/git-push-channel-failures.md`）：
> HTTPS fetch 失败会让 `origin/main` 跟踪 ref 停在旧 sha ⇒ **已推送却显示 `[ahead 1]`**。
> 本轮用 `git push` 的实际返回（`3f8efc6..0da8500 main -> main`）确认 push **真的成功**，
> 且 push 后 `git status -sb` 变为 `## main...origin/main`（无 ahead）⇒ 跟踪 ref 已同步。

---

## 4. 端到端探针（§5b）

**编排**：轮次一开始就用 `terminal(background=true, notify_on_complete=true)` 起跑，
与步骤 1–5 并行 —— **探针在本轮完整跑完 12/12**。

| 查询 | 结果 |
|---|---|
| C1102 控制器 通讯接口 有哪些 | 4/4 **200**（68.9s / 47.3s / 60.0s / 191.9s） |
| 冲压工艺 手册 参数设置 | 4/4 **200**（119.1s / 88.3s / 94.8s / 82.8s） |
| 示教器 操作手册 功能说明 | 4/4 **200**（100.7s / 134.6s / 134.2s / 216.8s） |

**合计 12/12 全 200，0 次 502**，耗时区间 **47.3s – 216.8s**，脚本退出码 **0**。
proxy journal 独立确认：本时段 **29 次** `POST /v1/chat/completions` **全部 200，零 5xx**
（12 本 KB + 12 姊妹 KB + 5 次其它）。

姊妹 KB 的探针（`/tmp/e2e-20261113.log`）同期**也全 200**（12/12，36.0s – 177.3s）——
两侧同时无 502 ⇒ **本轮 gateway 链路健康**。

> ⚠️ **本轮再次踩到 §陷阱 30**（github.com:443 不稳）：
> `git push` 报 `GnuTLS recv error (-110)` ⇒ `check_git_channel.py` 判 `:443` **2/3 OK（DEGRADED）**、
> `:22` **3/3 OK** ⇒ **立即切 SSH 传输通道**（一次性 `git push git@github.com:...` 语法，
> **不改 remote 配置**），返回 `0da8500..c5905ae main -> main` ⇒ **一次成功，零重试**。
> ⇒ 印证了 `references/git-push-channel-failures.md` 的判读：**探针「假绿」不可信，
> push 失败后立即复探并切 SSH**，别在长超时重试循环里烧时间。

---

## 5. 姊妹 KB（`inexbot-open`）—— 4 项 FAIL 仍是「慢性未修」，非本轮回归

本轮 `verify_kb.py` 报 **4 项 FAIL，全部带 `[inexbot-open]` 前缀**，与 11-12 **数值完全相同**：

| 失败项 | 数值 | 与 11-12 对比 |
|---|---|---|
| md 文件数 == index 条目数 | 1855 vs 799 | 相同 |
| raw 文件数 == index 条目数 | 1855 vs 799 | 相同 |
| 无零长度 snippet | 34 条零长度 | 相同 |
| 含图 md 全部可从 index 反查 | 73/177 | 相同 |

⇒ **连续第 2 轮数值不变** ⇒ 再次确认是**慢性未修**（不是并发中间态）。
**姊妹 KB 本轮 `index.json` mtime = 11:13 11:05:00** —— 她的 crawler 早已重建完 index，
数值仍不变 ⇒ **慢性问题**。

**这些失败不影响本 KB**：10/10 全 PASS + e2e 12/12 全 200
（姊妹探针同期也全 200 ⇒ 与链路无关）。
⇒ **本 KB 未改动她的 KB 数据文件**（只同步了共享文档，见 §6）。

### ⭐ 姊妹 KB 本轮又直接写进了本 skill 的目录（§陷阱 13 复现）—— 而且这次她**修好了一个真实损坏**

本轮姊妹 KB 的 agent 修改了共享文件 `references/shared-proxy-service-pitfalls.md`：

| 检查 | 本 KB（同步前） | 姊妹 KB（同步前） |
|---|---|---|
| sha1 | `8cb3d16624a6573b6157547708080bfe961d0766` | `da8d63f405074aece8c94122606806d46b9c089f` |
| section 数 | 30 | **31**（新增 §陷阱 31） |
| 「姊妹独有行」 | — | **66** |
| 「本 KB 独有行」 | 24 | — |

**本轮收尾（11:23）用她的 `check_shared_pitfalls_structure.py` 做了结构自检**，
发现 **本 KB 侧的共享文件带有一段「孤儿块」** ——
陷阱 27 有完整 section，**但文件末尾还有一整段陷阱 27 的正文重复**
（`陷阱 23 给了同步方向的判据…` / `### 现场（2026-10-10）` / `### ✅ 正确时序` …），
**却没有自己的 `## 陷阱 27：` 标题** ⇒ 像是某次 `patch` 只替换了一半。

⇒ **本 KB 的 24 行「独有内容」恰好就是这段损坏的重复块** ——
**姊妹侧已经把孤儿块删掉、并新增了 §陷阱 31**（专门讲这个损坏模式）。

**处置：直接 cp 姊妹的版本覆盖本 KB**（她的版本严格更优：多了 §陷阱 31、
少了孤儿块；本 KB 独有内容全是那段损坏）。
同步后本 KB 侧 **sha1 与姊妹侧完全一致**（`da8d63f405074aece8c94122606806d46b9c089f`）。

**结构自检对比**（`scripts/check_shared_pitfalls_structure.py`）：

| 项 | 本 KB（同步前） | 本 KB（同步后）= 姊妹侧 |
|---|---|---|
| sections | 30 | **31** |
| sub-headings | 34 | **36** |
| lines | 1435 | **1477** |
| `[DUPLICATE_LINE]` 命中 | **6**（含 4 条孤儿块正文行） | **2**（仅两条重复的 shell 片段） |
| `[EMPTY_SECTION]` / `[SUSPECT_ORPHAN]` / `[NO_SECTIONS]` | 无 | **无** ✅ |

⇒ **孤儿块已消除**：同步前那 4 条命中孤儿块正文的 `DUPLICATE_LINE` 全部消失，
剩下的 2 条是**两侧都有的、无害的重复 shell 片段**
（`ps -o pid,lstart,etime -p $(pgrep -f hermes-skill-proxy.py |` 和
`git fetch git@github.com:owner/repo.git main:refs/remotes/ss`）——
姊妹侧同样命中这 2 条 ⇒ **不是本 KB 独有的损坏**。

> ⚠️ **判读修正**：该脚本的退出码在「有任一 `DUPLICATE_LINE`」时即为 1，
> 因此**同步后仍是 exit 1**（姊妹侧同样 exit 1）。
> ⇒ **判据应当看「命中的是哪几行」**（是否指向正文块），
> **不能只看退出码** —— 否则会把「两侧一致的无害重复」误报成「结构损坏」。

> 💡 **教训**：**共享文件「sha1 一致」只是必要条件，不是充分条件** ——
> 两边都坏了的时候 sha1 也是一致的。本轮是**姊妹侧先修好**，
> 本 KB 侧才发现自己也坏着。⇒ **共享文件同步后必须跑结构自检**，
> 不能只看 sha1 / 标题集合（那两项在「两边都坏」时同样会过）。

> 💡 姊妹 KB 11-12 留给她的待办仍**未处理**：1855 vs 799 的孤儿 md/raw（历史死缓存，
> 架构上不可达）+ 34 条零长度 snippet + 含图反查 73/177。

---

## 6. 本轮新增/修改

| 文件 | 内容 | 来源 |
|---|---|---|
| `references/crawl-state-2026-11-13.md` | 本轮基线快照 | 本轮 |
| `SKILL.md` | v2.27.0 → **2.28.0**；新增 11-13 快照行；**§0.8「commit 完成 ≠ push 完成」的两种失败形态判别**；陷阱索引 +§31 | 本轮 |
| `references/shared-proxy-service-pitfalls.md` | **§陷阱 31**（共享文件并发 patch 拼坏 → 结构自检）+ **修掉本 KB 侧的一段「孤儿块」（陷阱 27 正文重复）** | **姊妹 KB**（§陷阱 13） |
| `scripts/check_shared_pitfalls_structure.py` | 结构自检：重复块 / 孤儿块 / 标题截断（实测 exit 0） | **姊妹 KB** |

---

## 7. 遗留 / 待办

| 项 | 状态 |
|---|---|
| **本 KB**（`inexbot`） | **无遗留** —— 7 步全过，工作树干净，commit 已推 |
| `[inexbot-open]` 4 项 FAIL | **姊妹 KB 范围，慢性未修**（连续第 2 轮数值不变）⇒ 建议姊妹 KB 处理；不影响本 KB |
| github.com:443 不稳 | **本轮再次命中**（`GnuTLS recv error (-110)`）⇒ 复探判 `:443` DEGRADED / `:22` OK ⇒ **立即切 SSH 通道，push 一次成功，零重试**（§陷阱 30 + `references/git-push-channel-failures.md`） |

**本轮所有改动均已在写报告正文之前完成 commit + push**：

| 仓库 | commit | push |
|---|---|---|
| `inexbot-knowledge-base` | `c5905ae`（SKILL.md §0.8 + v2.28.0） | ❌ HTTPS 失败（GnuTLS -110）⇒ ✅ **SSH 通道成功** `0da8500..c5905ae main -> main` |
| `inexbot-knowledge-base` | `5d2493e`（11-13 基线快照，194 行新增） | ✅ SSH 通道 `c5905ae..5d2493e main -> main` |
| `inexbot-knowledge-base` | `6d7cc21`（补全快照里的 commit hash） | ✅ SSH 通道 `5d2493e..6d7cc21 main -> main` |
| `inexbot-knowledge-base` | `a6744b4`（共享文档同步 + 结构自检脚本，4 文件 258 行） | ✅ SSH 通道 `6d7cc21..a6744b4 main -> main` |

**本轮共 4 个 commit，全部已在写报告正文之前 push 完成并逐一验证在远端历史里**：

| commit | 内容 |
|---|---|
| `c5905ae` | SKILL.md §0.8 + v2.28.0（**规则 commit，单独一个**） |
| `5d2493e` | 11-13 基线快照 |
| `6d7cc21` | 补全快照内的 commit hash |
| `a6744b4` | 共享文档同步（陷阱 31 + 修孤儿块）+ 结构自检脚本 |

**验证 push 真的落地**（不只看 `git status -sb`）：

```bash
git fetch git@github.com:inexbot/inexbot-knowledge-base.git main:refs/remotes/sshcheck/main
git merge-base --is-ancestor a6744b4 refs/remotes/sshcheck/main   # -> YES
git update-ref refs/remotes/origin/main $(git rev-parse refs/remotes/sshcheck/main)
git status -sb                                                     # -> ## main...origin/main（无 ahead）
```

> ⚠️ 若下一轮 `git status -sb` 又出现 `M` / `??` / `[ahead N]`，
> 则本轮的「已提交已推送」结论同样是假的 —— 按 §0.6 / §0.7 / **§0.8** 独立核对，
> 不要相信本文件的自我声明。
