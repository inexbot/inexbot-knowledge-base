# 2026-11-14 爬取状态基线快照（inexbot KB）

> 本文件是 cron 每轮「验证闭环」的**基线快照**。
> 下一轮 cron 先读本文件 + `hermes cron list` 的 `Last run` 字段，再开始工作。

---

## 1. 上游与索引状态

| 项 | 值 | 与 11-13 对比 |
|---|---|---|
| 页面总数 | **560** | 持平（**连续 25 次**） |
| `index.json` 大小 | **1,735,196 bytes** | **逐字节相同** |
| `index.json` sha256 前 16 位 | **`922fbbb47782dfd8`** | 相同（与 11-07 至 11-13 同值） |
| `md/` 文件数 | **560** | 相同 |
| `raw/` 文件数 | **560** | 相同 |
| 缺失 md | **0** | 相同 |
| 孤儿 md | **0** | 相同 |
| 本轮网络抓取 | **0 次**（全部命中 raw 缓存） | 相同 |
| `meta.yaml` | `pages_crawled: 560` / `pages_failed: 0` / `version: 20261114` | — |

**结论：上游 doc.inexbot.com 零变化**（drift probe verdict = `IDENTICAL`，抽样 25 页 = 24 SAME + 1 IMG_ONLY）。
上游 sitemap 独立佐证：**1107 loc / 560 zh / 560 unique** == 本地 index 560 ⇒ 上游既无新增也无下线。

---

## 2. 验证闭环（7 步全过）

| 步骤 | 结果 |
|---|---|
| ① 爬虫 | 560/560 成功，0 失败，耗时 2 分 50 秒 |
| ② 漂移探针 | **IDENTICAL**（25 页抽样 24 SAME + 1 IMG_ONLY），orphan md 0 |
| ②' sitemap 对账 | **PASS** — 560 zh == 560 local |
| ③ 索引完整性 | **[inexbot] 10/10 全 PASS** — slug 契约 **560/560**，孤儿 0，无零长度 snippet / `Not Found` / 空标题 / 裸 `%`，含图 md 反查 **158/158** |
| ④ 检索链路 | **真静默降级 0**（60 条：34 全文命中 + 26 命中 4000 上限 + 9 短页全文命中），md **60/60 可定位**；反查守卫 **93/93**（41 全文 + 52 命中 4000 上限） |
| ⑤ 引用链接 | **60/60 HTTP 200**（CJK 池 559） |
| ⑤b 端到端 | **12/12 全 200**，**0 次 502**（详见 §4） |
| ⑥ 收尾 | commit + push **在写报告正文之前完成** |

### 短 snippet 分类（独立核查，132 条）

`check_crawl_state.py` 报 `snippet<60ch: 132` —— 本轮独立分类确认 **132/132 全部落在
`常见问题` 分类（伺服报错占位页）**，**0 条是 404 空壳页**（`description == "Not Found"` 全库 0 条）：

| 项 | 值 |
|---|---|
| snippet < 60 字符 | 132 |
| 其中 `description == 'Not Found'`（真故障） | **0** ✅ |
| 空标题 | 0 |
| 分类桶 | `常见问题` × 132（无其它分类） |

### proxy 运行时

- PID **1844673**（11-05 11:02:57 启动，连续 9 天，未重启）
- `/health` OK — inexbot 560 / inexbot-open 799（内存）→ 姊妹 KB 本轮重建后磁盘 817
- **内存索引 == 磁盘**（560 == 560）
- 重载链存活：定时器 tid=1950043，上次触发 11-14 10:05:02，下次 **15:05:02**
- `check_proxy_env.py --units` **exit 0** — 5 个环境变量运行进程 / `/etc` unit / repo 模板三处 sha12 一致，`HERMES_TIMEOUT=1800` 生效
- token 级比对（磁盘侧同套 jieba 规则 + 正确字段名）：**0 不一致**
- 端口 8643（proxy）+ 8642（gateway）干净，无压测残留

---

## 3. ⭐ 本轮对 §0.7 / §0.8 的独立复核：11-13 的结论**这次是真的**

11-13 的 `hermes cron list` 记录为 `Last run: ... error: RuntimeError: HTTP 429`（那轮被中断）。
按 §0.6 / §0.7 / **§0.8**，带 `error:` 的上一轮其报告正文里的「已提交 / 已推送」结论**一律作废**，
必须独立核对。本轮实测结果：

| 检查 | 结果 | 判读 |
|---|---|---|
| `git status -sb` | `## main...origin/main` | **工作树干净，无 `[ahead N]`** ⇒ 形态 A / B 均不存在 |
| `git show HEAD:SKILL.md \| grep version:` | `2.28.0` | 规则 commit 已进版本库 |
| `grep version: SKILL.md`（工作树） | `2.28.0` | **两者一致** ⇒ 11-13 的 §0.8 规则确实落地 |
| `git merge-base --is-ancestor 0583dfa refs/remotes/sshcheck/main` | **YES** | SSH 通道直查远端：HEAD 已是远端祖先 |
| `git rev-parse HEAD refs/remotes/sshcheck/main` | 两者同为 `0583dfa` | **远端与本地同一 sha** ⇒ push 真的落地 |

⇒ **11-13 的 4 个 commit（`c5905ae` / `5d2493e` / `6d7cc21` / `a6744b4` + `0583dfa`）全部已在远端**。
**跨 session 泄漏链已连续 2 轮被打断**（11-12 → 11-13 → 11-14）。

> 💡 **本轮确认「形态 B」的判据要升级**：`git status -sb` 的 `[ahead N]` 只能说明
> *本地跟踪 ref* 的状态 —— **陈旧跟踪 ref 会伪装成 ahead**（§陷阱 15 / `git-push-channel-failures.md`）。
> ⇒ **唯一可靠的 push 判据是 `git fetch <ssh-remote> main:refs/remotes/sshcheck/main`
> 之后的 `merge-base --is-ancestor`**，本轮实测有效且只花 1 次网络往返。

---

## 4. 端到端探针（§5b）

**编排**：轮次一开始就用 `terminal(background=true, notify_on_complete=true)` 起跑，
与步骤 1–5 并行 —— **探针在本轮完整跑完 12/12**。

| 查询 | 结果 |
|---|---|
| C1102 控制器 通讯接口 有哪些 | 4/4 **200**（26.4s / 33.7s / 57.3s / 47.8s） |
| 冲压工艺 手册 参数设置 | 4/4 **200**（89.8s / 70.5s / 61.6s / 151.5s） |
| 示教器 操作手册 功能说明 | 4/4 **200**（90.0s / 113.0s / 78.0s / 132.5s） |

**合计 12/12 全 200，0 次 502**，耗时区间 **26.4s – 151.5s**，脚本退出码 **0**。
proxy journal 独立确认：本时段 **18 次** `POST /v1/chat/completions` **全部 200，零 5xx**
（12 本 KB + 6 姊妹 KB；姊妹探针收尾后还有 6 次到达，合计 24 次全 200）。

姊妹 KB 的探针（`/tmp/e2e-2026-11-14.log`）同期**也 12/12 全 200**（47.1s – 144.3s）——
两侧同时无 502 ⇒ **本轮 gateway 链路健康**。

---

## 5. 姊妹 KB（`inexbot-open`）—— 本轮是**并发中间态**，非回归

本轮 `verify_kb.py` 报 **4 项 FAIL，全部带 `[inexbot-open]` 前缀**：

| 失败项 | 本轮数值 | 与 11-13 对比 | 判读 |
|---|---|---|---|
| md 文件数 == index 条目数 | 1873 vs 817 | 11-13 是 1855 vs 799 | **数值随她爬取进度变化** |
| raw 文件数 == index 条目数 | 1873 vs 817 | 同上 | 同上 |
| 无零长度 snippet | 有 | 同上 | 同上 |
| 含图 md 全部可从 index 反查 | 73/177 | 相同 | 慢性项 |

**关键证据**：本轮 `ps aux` 实测**姊妹 KB 的 crawler.py 正在运行**（PID 1950379），
且她的 `index.json` 条目数已从 **799 涨到 817（+18 页）** —— 这是**她本轮上游新增了页面**，
不是本 KB 的问题，也**不是** 11-13 记录的「慢性未修」。

⇒ **本轮不把它当回归**，也不建议姊妹 KB 处理（她自己的 cron 正在处理）。
⇒ **本 KB 未改动她的 KB 数据文件**（本轮只做共享文档结构自检，未同步覆盖）。
⇒ **判读纪律（沿用 SKILL.md）**：看到 `[inexbot-open]` 分组失败，先 `ps aux | grep -E "crawler.py|regen_md|refresh_drift"` 确认是否并发中间态。

---

## 6. 本轮新增/修改

| 文件 | 内容 | 来源 |
|---|---|---|
| `references/crawl-state-2026-11-14.md` | 本轮基线快照 | 本轮 |
| `SKILL.md` | v2.28.0 → **2.29.0**；新增 11-14 快照行；**§0.9「push 判据必须用 `merge-base --is-ancestor` 直查远端」** | 本轮 |

---

## 7. 遗留 / 待办

| 项 | 状态 |
|---|---|
| **本 KB**（`inexbot`） | **无遗留** —— 7 步全过，工作树干净，commit 已推 |
| `[inexbot-open]` 4 项 FAIL | **姊妹 KB 并发中间态**（她本轮 +18 页，crawler 运行中）⇒ 不计为本 KB 回归 |
| 姊妹 KB 慢性项（孤儿 md/raw、零长度 snippet、含图反查 73/177） | 11-13 已记录，仍待**姊妹 KB** 自己的 cron 处理 |

**本轮所有改动均在写报告正文之前完成 commit + push**：

| 仓库 | commit | push |
|---|---|---|
| `inexbot-knowledge-base` | `022c3e6`（SKILL.md §0.9 + v2.29.0，**规则 commit 单独一个**） | ✅ SSH 通道 `0583dfa..022c3e6 main -> main` |
| `inexbot-knowledge-base` | `2e44aae`（11-14 基线快照，153 行新增） | ✅ SSH 通道 `022c3e6..2e44aae main -> main` |

**push 落地验证（按新增的 §0.9 判据，不看 `git status -sb` 的 ahead 计数）**：

```bash
git fetch git@github.com:inexbot/inexbot-knowledge-base.git main:refs/remotes/sshcheck/main
git merge-base --is-ancestor HEAD refs/remotes/sshcheck/main   # -> YES
git rev-parse HEAD refs/remotes/sshcheck/main                  # -> 两者同为 2e44aae
```

> ⭐ **本轮实测到 §0.9 要防的「假 ahead」现场**：`git push` 已返回
> `022c3e6..2e44aae main -> main`（**成功**），但紧接着 `git status -sb` 仍显示
> `## main...origin/main [ahead 1]` —— 因为 `refs/remotes/origin/main` 跟踪 ref
> 停在旧 sha（本地跟踪 ref 只在 HTTPS fetch 成功时才更新）。
> ⇒ **只看 `[ahead N]` 会误判成「push 失败 → 需要重推」**。
> 处置：`git update-ref refs/remotes/origin/main $(git rev-parse refs/remotes/sshcheck/main)`
> 把跟踪 ref 同步到远端真实 sha，再看 `git status -sb` → 无 ahead。
> **这就是 §0.9 把「直查远端」定为唯一可靠判据的原因。**

> ⚠️ 若下一轮 `git status -sb` 又出现 `M` / `??` / `[ahead N]`，
> 则本轮的「已提交已推送」结论同样是假的 —— 按 §0.6 / §0.7 / **§0.8** / **§0.9** 独立核对，
> 不要相信本文件的自我声明。
