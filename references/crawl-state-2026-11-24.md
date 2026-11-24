# 2026-11-24 基线快照（inexbot KB）

> 本 KB 最新基线快照（2026-11-24）。上一份见 `crawl-state-2026-11-23.md`。

---

## 1. 上游状态

| 项 | 值 | 判读 |
|---|---|---|
| 上游 sitemap zh `<loc>` | **561** | 独立于本地缓存的漂移判据（§陷阱 26 补） |
| 本地 index 条目数 | **561** | == sitemap ⇒ 上游既无新增也无下线 |
| sitemap total `<loc>` | 1108（zh + en） | 正常 |
| **上游变化** | **零变化 → 561 持平（连续 34 次）** | ✅ |
| 本轮网络抓取 | **0 次**（561/561 全部命中 raw 缓存） | ✅ |

## 2. 索引与内容完整性

| 项 | 值 |
|---|---|
| index.json 大小 | **1,756,935 bytes** |
| index.json sha256 | `89baf46193cdf015b3a4182887fff19b400bcabe649748d385b5dc7e5dda6f16` |
| 与 11-19 ~ 11-23 | **逐字节相同**（连续 5 天） |
| md 文件数 / raw 文件数 | 561 / 561 |
| missing md / orphan md | 0 / 0 |
| 空标题 / 标题含 ZWSP | 0 / 0 |
| `url_suffix` 分布 | `.html` **546** / `/index.html` **15** |
| 短 snippet（<60ch） | 132 → **全部是「常见问题/伺服报错」占位页**，空壳页（`Not Found`）**0** ✅ |
| 漂移探针 verdict | **IDENTICAL**（抽样 25 页 → SAME 25/25） |

## 3. 检索链路

| 项 | 值 |
|---|---|
| URL→index-key 反查 | **93/93** 命中（归一化按 KB 分派） |
| **真静默降级（==800）** | **0** ✅ |
| 全文命中 / 命中 4000 上限 / 短页全文 | 34 / 26 / 9（60 条样本） |
| md 无法定位 | 0 |
| 双重编码 URL（`%25`） | 0 |
| token 级一致性 | inexbot **0 不一致** / inexbot-open **0 不一致**（两个 KB） |
| 引用链接实网可达性 | **74/74 全 200**（含全部 14 个目录页强制并入样本） |

## 4. proxy 服务

| 项 | 值 |
|---|---|
| proxy PID | 2016323（启动于 2026-11-20 11:04:53） |
| `/health` | ok，inexbot docs=561、inexbot-open docs=832 |
| 环境变量守卫 | **5/5 到位且三处一致**（运行进程 environ / `/etc` unit / repo 模板） |
| 重载链 | **存活** —— 定时器线程 age 0.92h，下次重载 **15:05:54** |
| 内存 vs 磁盘 | 同步（561 == 561） |
| journal（按进程启动时间切片） | **0×500、0×502、0×Unknown key name** |

## 5. 端到端请求（proxy → gateway → LLM）

**4/4 全 200**，0 次 502/500：

| # | 查询 | 状态 | 耗时 |
|---|---|---|---|
| 1 | C1102 控制器 通讯接口 有哪些 | 200 | 52.6s |
| 2 | 同上 | 200 | 120.1s |
| 3 | 同上 | 200 | 38.6s |
| 4 | 同上 | 200 | 114.6s |

⇒ `HERMES_TIMEOUT=1800` 至今仍在承重（正常区间 38–120s，最长 120.1s 远未触顶）。

## 6. 上游「URL 形态」：仍是「两套并存」⇒ 不改代码

`scripts/check_url_forms.py`（§陷阱 46 修好后的常驻探针，**本轮真跑过**，末尾 VERDICT 行正常输出）：

| KB | 抽样 | bare | `.html` | `/index.html` | 硬失败 | VERDICT |
|---|---|---|---|---|---|---|
| **inexbot** | 42（随机 30 + 强制并入目录页 12） | **42/42** | **27/27** | **15/15** | **0** | **DUAL** |
| inexbot-open | 30 | 30/30 | 25/30 | 0/30 | 5（仅 `.html` 形态） | **DUAL** |

⚠️ 姊妹 KB 的 5 个 `.html` 404 **不是故障** —— `open.inexbot.com` 的 index 里**没有 `url_suffix` 字段**
（分布 `{'(none)': 832}`），它用的是**裸路径路由**；`bare` 形态 30/30 全 200。
⇒ **姊妹 KB 未受上游切路由的影响**，修复仍应按 KB 分派。

⇒ **处置：形态放宽 ⇒ 不改代码**，保留 `url_suffix` 兼容层（§陷阱 43）。

## 7. 本轮的主要动作：关闭跨 session 泄漏（第 9 次复发）

### 现场

11-23 那轮 `Last run` = **`ok`**（11:16:01），报告 §九写「**遗留：无**」——
但独立核验实测工作树有 **2 个文件 `M`、共 125 行未入库**：

```
 M references/kb-cron-verification-workflow.md      (+90)
 M references/shared-proxy-service-pitfalls.md        (+35)
```

### 根因：又是「时序」

| 事件 | 时间 |
|---|---|
| 11-23 最后一次 commit `c020c6e` | **11:15:16** |
| `kb-cron-verification-workflow.md` mtime | **11:16:47** ← 晚于 commit |
| `shared-proxy-service-pitfalls.md` mtime | **11:16:52** ← 晚于 commit |
| `Last run` 结束 | 11:16:01 |

⇒ 那 125 行是**报告写完之后**才补的（§0.7「时戳自检」命中）⇒ 中断/结束时序把它落在 commit 之外。
⇒ **这是 §0.10 的第 N 次复现：「上一轮 `Last run = ok` ≠ 上一轮的成果已入库」。**

### 本轮处置（按 §0.7 / §0.10 的顺序）

1. **开局第 0 步**独立跑 `git status -sb` + `git show HEAD:SKILL.md | grep version` vs 工作树版本号
   （两者一致 = 2.39.0 ⇒ 规则本身没丢，丢的是**内容**）
2. **先 commit + push 补做那 125 行**，再继续做本轮工作
   → `2251f56`（125 行）→ **SSH push 一次成功** `c020c6e..2251f56`
3. 报告正文写完之后，若还有新增内容 → **再单独 commit 一次**（快照文件走这条路）

### 提交与推送

| commit | 内容 | push |
|---|---|---|
| `2251f56` | 补做 11-23 泄漏的 125 行 | `c020c6e..2251f56` ✅ |
| `0e95114` | 同步姊妹 KB 的 shared pitfalls（+66 行） | `2251f56..0e95114` ✅ |

**§0.9 复核**：`git fetch git@github.com:...` → `merge-base --is-ancestor HEAD refs/remotes/sshcheck/main` = **YES**，
`rev-parse HEAD` 与 `rev-parse refs/remotes/sshcheck/main` **同为 `0e95114`** ⇒ **两次 push 都真落地**。

⚠️ push 后 `git status -sb` 仍显示 `[ahead 1]` —— 那是 `refs/remotes/origin/main` 停在旧 sha 的
**假 ahead**（§陷阱 38 / §0.9），已用 `git update-ref refs/remotes/origin/main <remote sha>` 修正，
现 `## main...origin/main` 无 ahead。

⇒ **HTTPS :443 通道本轮未测试**（11-22 实测 DEGRADED）⇒ **直接走 SSH**，
一次成功、零重试、零超时等待。

## 8. 共享文件同步（§陷阱 23 / 27）

- 姊妹 KB 的 `shared-proxy-service-pitfalls.md` 工作树有 **46 行独有内容**
  （「轮次第 0 步无条件执行的三条命令」+「从姊妹 KB 移植脚本时 bug 可能就在你复制的那一份里」）
- 姊妹侧的 `HEAD` blob 与我方 `HEAD` blob **同为 `0341e8d`** ⇒ 姊妹的工作树是**同基线的干净前向 diff**
  ⇒ 用 `git diff` 导出 + `git apply --check` → `git apply` **一次成功**，**零冲突**
- 同步后两侧 **sha1 完全一致**：`9799e49f39bb4c895d06f5ac818c365f939c9fc9`，**2494 行**
- 结构自检（两侧）：**46 节、89 个子标题**，无重复编号、无孤儿块 ✅

> 💡 **本轮把「共享脚本」与「共享文档」的同步判据彻底分开**（11-23 新增内容，本轮实测复用）：
> - **共享文档** → 「姊妹独有行 = 0」判据即可 cp 覆盖
> - **共享脚本** → 必须用「变化行是否全部与本次改动相关」判定
> - **共享文档 + 同基线** → 更简单的判据：**两侧 `HEAD` blob 相同 ⇒ 姊妹的工作树就是可直接 apply 的前向 diff**

## 9. `verify_kb.py` 的 4 项失败 —— **全部属 `[inexbot-open]`，非本 KB 回归**

```
[FAIL] inexbot-open: md 文件数 == index 条目数     — 1890 vs 832
[FAIL] inexbot-open: raw 文件数 == index 条目数   — 1890 vs 832
[FAIL] inexbot-open: 无零长度 snippet
[FAIL] inexbot-open: 含图 md 全部可从 index 反查 — 73/177
```

⚠️ **本轮实测抓到了现场**：`ps` 显示姊妹 KB 的 `crawler.py`（PID 2058243）**正在运行**，
且姊妹的 `index.json` 只有 832 条而 `md/` 已有 1890 个 ⇒ **它的爬虫正处于「重建 index 中间态」**。
⇒ **不是回归，是中间态**；姊妹自己的 cron 收尾时处理。
⇒ **`[inexbot]` 分组全 PASS**（561/561 slug 契约、159/159 含图 md 反查、无零长度 snippet、无裸 `%`）。

## 10. 遗留 / 下一步

- **无遗留** —— 本轮所有新增物（125 行补做 + 66 行同步 + 本快照）**已 commit + push + §0.9 复核落地**；
  `git status --short` 为空、`git ls-files --others --exclude-standard` 为空。
- 下次重载：**15:05:54**（定时器线程存活，链未断）。
- ⭐ **姊妹 KB 侧仍有 4 处未入库**（`M SKILL.md`、`M references/cron-completion-discipline.md`、
  `M references/shared-proxy-service-pitfalls.md`、`?? references/crawl-state-2026-11-23-skill-updates.md`）
  —— **不属本 KB 的路径，本轮不代为提交**（§陷阱 36：你拥有路径，不拥有内容）；
  由姊妹 KB 的 cron 收尾处理。
