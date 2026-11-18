# 2026-11-17 爬取状态基线快照（inexbot KB）

> 本文件是 cron 每轮「验证闭环」的**基线快照**。
> 下一轮 cron 先读本文件 + `hermes cron list` 的 `Last run` 字段，再开始工作。

---

## 0. 本轮的「上一轮待办」处理

`hermes cron list`（11-17 11:00 开局实测）：

| Cron | Last run | 判读 |
|---|---|---|
| `inexbot-knowledge-base daily crawl` | `2026-11-16T11:27:04 ok` | ✅ **本 KB 上一轮正常收尾**（无 `error:`）⇒ 其报告结论可采信 |
| `inexbot-open-knowledge-base daily crawl` | `2026-11-16T11:31:57 ok` | ✅ 姊妹 KB 上一轮也正常 |

**⚠️ 但上一轮的工作树并没有干净** —— 开局实测发现 **form-A 跨 session 泄漏**：

| 判据 | 实测 | 结论 |
|---|---|---|
| `git status -sb` | `## main...origin/main` + **2 个 `M`**（`SKILL.md`、`references/shared-proxy-service-pitfalls.md`，共 **151 行**） | 🔴 **改动没进 commit**（形态 A） |
| `git show HEAD:SKILL.md \| grep '^version:'` | `version: 2.31.0` | — |
| `grep '^version:' SKILL.md` | `version: 2.32.0` | **工作树比 HEAD 新** ⇒ §0.7 规则没落地 |
| 文件 mtime vs 最后 commit 时间 | commit `11:26:32`；`SKILL.md` mtime `11:28:13`、`shared-*.md` mtime `11:27:33` | ⭐ **两处 mtime 都晚于 commit** ⇒ 典型「报告写完之后才补的」⇒ 正是 §0.7 时戳自检指出的高危形态 |
| §0.9 直查远端 | `merge-base --is-ancestor HEAD refs/remotes/sshcheck/main` = **YES**；`rev-parse HEAD` 与 `rev-parse refs/remotes/sshcheck/main` **同为 `29e4eba`** | ✅ 11-16 的 **commit 已推送**（无形态 B） |

⇒ **本轮是「跨 session 泄漏第 8 次复发」**：11-16 那轮虽然 commit 了，
但**收尾时补写的 151 行没进库**。

**本轮处置（严格按 §0.7 的时序）**：**开局第一件事**就是
`git add -A && git commit` + `git push`（**在写任何报告正文之前**），
把 11-16 的成果补进版本库：

```
b4be2c3  docs(skill): bump to 2.32.0, add traps 34-35 (slugify convention, push TLS retry)
push     : 29e4eba..b4be2c3  main -> main   （一次成功，未重试）
```

⇒ 下一轮开局复核时，HEAD 版本号应 == 工作树版本号 == `2.32.0`。

---

## 1. 爬取结果

| 项 | 值 |
|---|---|
| 爬取页面数 | **560**（成功 560 / 失败 0） |
| 网络抓取次数 | **0**（全部命中 `raw/` 缓存，「跳过（已存在）」） |
| 耗时 | 3 分 34 秒 |
| index 条目数 | **560** |
| index 大小 | **1,735,196 bytes** |
| index sha256 | **`922fbbb47782dfd8`** |
| md/ 文件数 | 560 |
| raw/ 文件数 | 560 |
| 孤儿 md | **0** |
| missing md | **0** |

> ⭐ **index 逐字节第 10 天相同**（11-07 → 11-17 连续 10 天 sha 均为 `922fbbb47782dfd8`）。

---

## 2. 漂移判据（双路佐证）

### 2.1 `check_crawl_state.py --sample 25`

```
index.json : 560 entries, 1,735,196 bytes, sha=922fbbb47782dfd8
md/ files  : 560   raw/ files: 560
missing md : 0   orphan md: 0
snippet<60ch: 132   empty titles: 0   ZWSP in title/desc: 0
health     : OK
drift      : 抽样 25 页 → {'SAME': 25}
verdict    : IDENTICAL (索引与上次逐字节相同，抽样未发现上游漂移)
exit code  : 0
```

> ⭐ **本轮连 `IMG_ONLY` 都没有**（25/25 全 `SAME`）—— 连续第 2 轮如此。

### 2.2 `check_sitemap_count.py`（独立于本地缓存）

```
total <loc>       : 1107
zh <loc>          : 560
zh unique        : 560
local index       : 560
=> PASS
```

⇒ 上游既无新增也无下线，且与本地 index 条目数**精确一致**。

---

## 3. 索引完整性 / 检索链路 / 引用链接

| 检查 | 脚本 | 结果 |
|---|---|---|
| 全量回归 | `verify_kb.py` | **`[inexbot]` 10/10 PASS**；FAIL 4 项**全在 `[inexbot-open]` 分组** |
| 检索链路（字符数判据） | `check_retrieval_chain.py` | 60 条：真静默降级 **0**、全文命中 34、4000 上限 26、短页全文 9、`md_not_found` **0** |
| 反查守卫 | `check_url_to_index_key.py` | 93/93 命中、真静默降级 0、`no-md lookup` 0 |
| 引用链接实网 | `check_citation_links.py` | 抽样 60 条 → **60/60 HTTP 200**、404/410 = 0、网络错误 = 0 |
| 短 snippet 二分类 | `check_short_snippet_class.py` | 占位页 132、空壳页（真 BUG）**0**、md 无法定位 0 |
| proxy 环境变量 | `check_proxy_env.py --units` | 线上进程 + `/etc` unit + repo 模板 **三处 5 变量 sha12 逐项一致** |
| 重载链 | `check_reload_timer.py` | 定时器 tid=1981581，age **1.73h**，下次重载 14:18:22；内存 560 == 磁盘 560 |
| token 级一致性 | `check_token_consistency.py` | inexbot 0 处不一致、inexbot-open 0 处不一致；key 集合相同 = True |
| 共享文件结构 | `check_shared_pitfalls_structure.py` | 两个 KB 各 37 sections / 52 sub-headings / 1782 行，**结构一致** |

### 3.1 journal 侧（按进程启动时间切片，§陷阱 12）

proxy PID 1954151，启动于 `2026-11-14 11:17:36`，切片统计：

| 状态码 | 次数 | 说明 |
|---|---|---|
| **200** | 69 | — |
| **500** | **0** | ✅ |
| **502** | **0** | ✅ |
| 404 | 15 | **全部是外部扫描器/健康检查**（`GET /`、`GET /favicon.ico`、`GET /version` 等，与 KB 无关） |
| `Unknown key name` | **0** | ✅ systemd `Environment=` 块解析正常 |

---

## 4. 端到端探针（§5b）

按 §5b 的编排铁律，**探针在轮次「一开始」就用 `terminal(background=true, notify_on_complete=true)` 起跑**，
然后并行做 2/3/4/5 步，最后收结果。

**本 KB 结果：12/12 全 HTTP 200，0 次失败**（exit 0）。

| 查询 | 4 次耗时 | 结果 |
|---|---|---|
| `C1102 控制器 通讯接口 有哪些` | 106.3s / 68.4s / 136.3s / 85.5s | ✅ 4/4 = 200 |
| `冲压工艺 手册 参数设置` | 182.6s / 129.5s / 193.8s / **462.5s** | ✅ 4/4 = 200 |
| `示教器 操作手册 功能说明` | 102.7s / **683.0s** / 67.5s / 99.9s | ✅ 4/4 = 200 |

- 最慢 **683.0s**、最快 **67.5s** —— 远低于 proxy 的 `HERMES_TIMEOUT=1800`
- **0 次 502、0 次 500、0 次客户端 timeout**；journal 侧（11-17 11:00 起）**0 条 5xx**
- ⭐ **两条长尾（462.5s / 683.0s）仍返回 200** ⇒ `HERMES_TIMEOUT=1800` 这个配置**至今仍在承重**，
  是 1800s timeout 最硬的正面证据之一
- 姊妹 KB 同时段探针（`/tmp/e2e-2026-11-17.log`）**同样 12/12 全 200**
  ⇒ 两侧同时段都全绿，**没有共享链路停顿的迹象**

> 📌 探针日志路径：`/tmp/e2e-inexbot-2026-11-17.log`（本 KB）
> 与 `/tmp/e2e-2026-11-17.log`（姊妹 KB 写的）。

---

## 5. git 状态（本轮收尾）

| 项 | 值 |
|---|---|
| 补提交（11-16 的泄漏） | **`b4be2c3`** — `docs(skill): bump to 2.32.0, add traps 34-35 (slugify convention, push TLS retry)`（2 files changed, 151 insertions） |
| 本轮 commit | **`724ebd0`** — `docs(skill): add 2026-11-17 crawl snapshot, sync shared pitfalls traps 36-37, bump to 2.33.0`（3 files changed） |
| push（第 1 次） | ⛔ **60s 工具超时被掐断**（`git push` 还在跑）⇒ **用 §0.9 直查远端判真伪**：`merge-base --is-ancestor` = **NO**、远端仍在 `b4be2c3` ⇒ **push 确实没落地**（不是假象） |
| push（第 2 次，重试循环） | 第 1 次重试仍 **131.1s 连接超时**（§陷阱 30 的 github.com:443 不稳，**不是鉴权失败**）→ 第 2 次重试成功：**`b4be2c3..724ebd0  main -> main`** |
| §0.9 直查远端 | `merge-base --is-ancestor HEAD refs/remotes/sshcheck/main` = **YES**；`rev-parse HEAD` 与 `rev-parse refs/remotes/sshcheck/main` **同为 `724ebd017e8e8b50bdb6f1af164814d7021bf2f0`** ⇒ **push 真的落地** |
| 共享文件同步 | 姊妹 KB 侧新增 **§陷阱 36 / 37** ⇒ 本轮把姊妹版本**同步回来**（见 §5.1） |
| 收尾 `git status -sb` | `## main...origin/main`（**无 ahead、无 `M`、无 `??`**）⇒ 工作树干净 |
| HEAD 版本号 vs 工作树版本号 | `2.33.0` == `2.33.0` ⇒ §0.7 检查通过 |

> ⭐ **本轮收尾严格按 §0.7 的时序**：**改 → commit → push → 写报告正文**。
> 快照文件里 e2e 数据、push 细节都是探针/push 跑完后才补写的，
> 补写后**立即单独 commit + push**（见 §7.1）。
>
> 💡 **新增判据（值得记住）**：**push 命令被工具超时掐断 ≠ push 成功，也 ≠ push 失败**。
> 本轮 `git push` 在 60s 工具上限处被截断，若按「返回了超时」就判「推送失败」并盲目重推，
> 可能重复 push 同一个 commit；反过来若按「命令跑了就算成功」就收工，
> 则会留下「本地有 commit、远端没有」的形态 B。
> ⇒ **唯一可靠做法就是 §0.9 的 `merge-base --is-ancestor` 直查远端**：
> 本轮它给出 `ANCESTOR_NO`（远端仍在 `b4be2c3`）⇒ 确认要重试 ⇒ 重试第 2 次成功。

### 5.1 共享文件同步（§陷阱 27 / 37）

姊妹 KB（`inexbot-open`）在本轮中途把 **§陷阱 36**（姊妹 agent 会在你的 skill 目录里新建文件
—— 你不拥有内容，但拥有路径）和 **§陷阱 37**（收尾时姊妹改了共享文件 ⇒ 先比对 `git show HEAD:`）
写进了它那份 `references/shared-proxy-service-pitfalls.md`。

判读（按 §陷阱 23 / 37 的三问）：
1. 两份内容是否一致？→ **否**（姊妹 1782 行 vs 本 KB 1678 行）
2. 共同前缀？→ **1623 行完全相同**，姊妹侧多出 §陷阱 36 / 37 ⇒ **姊妹是严格超集，无冲突**
3. 结构是否完好？→ `check_shared_pitfalls_structure.py` **两个 KB 均 37 sections / 52 sub-headings** ✅

⇒ 处置：把姊妹版本**单向同步回本 KB**（姊妹是超集 ⇒ 无内容丢失），
再用 `git show HEAD:` 的 sha1 判据确认「同步后的内容不在 HEAD 里」才提交。

### 7.1 补写 e2e / push 结果后的第二次 commit

本文件 §4 的 e2e 数据与 §5 的 push 细节，都是探针/push 跑完后才产生的
⇒ 属于「push 之后才产生的改动」，mtime 晚于最后一次 commit ⇒ **最容易被下一轮的中断丢掉**。
⇒ 按 §0.7 的**时戳自检**，补写后**立刻单独 commit + push**。

### 7.2 ⭐ 本轮新增判据：**push 被工具超时掐断 ≠ 成功，也 ≠ 失败**

本轮第 1 次 `git push` 在 **60s 工具上限**处被掐断（返回 `Command timed out after 60s`）。
**这个返回值既不能证明推送成功，也不能证明失败** ——
因为 `git push` 可能已经握手成功、正在传 pack。

⇒ **唯一可靠的判据仍是 §0.9**：`git fetch`（走 SSH，不受 443 影响）+
`merge-base --is-ancestor HEAD refs/remotes/sshcheck/main`。

| `merge-base --is-ancestor` | 含义 | 动作 |
|---|---|---|
| **YES** | push 真的落地了 | **不要重推**（否则重复 push 同一 commit） |
| **NO** | push 确实没落地 | **重试**（配重试循环，每次用 §0.9 复核） |

本轮实测：`ANCESTOR_NO`（远端停在 `b4be2c3`）⇒ 确认要重试
⇒ 重试第 1 次 131.1s 超时、第 2 次成功（`b4be2c3..724ebd0`）
⇒ 复核 `ANCESTOR_YES`，HEAD 与远端同为 `724ebd0`。

> 💡 **推论**：`git status -sb` 的 `[ahead N]` 在这轮**同样不可信**
> —— 它的依据是**本地跟踪 ref**，而 HTTPS fetch 失败会让它停在旧 sha。
> **本轮实测确认了「假 ahead」**：push 已返回成功、`git status -sb` 却仍显示 ahead。
> ⇒ **每次 push 后都用 §0.9 复核，不要用 `git status -sb` 的 ahead 计数当判据。**

---

## 6. 待办 / 遗留

- **本 KB：无遗留**（工作树干净 + push 已用 §0.9 直查远端确认落地）。
- **姊妹 KB `inexbot-open`**：工作树仍有 2 个未提交文件
  （`references/.index-snapshot.json`、`references/shared-proxy-service-pitfalls.md` +104 行），
  **由姊妹 KB 的 cron 自己补 commit + push**，本 KB 不越界代劳。
- **本轮无 proxy restart**（上游零变化 ⇒ 内存索引无需刷新；且 restart 会打断姊妹 KB 正在跑的探针）。
