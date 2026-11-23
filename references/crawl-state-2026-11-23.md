# inexbot KB 基线快照 — 2026-11-23

> 本文件是 `inexbot-knowledge-base` 的**每日基线快照**（每日 11:00 cron 生成）。
> 上一份：[crawl-state-2026-11-22.md](crawl-state-2026-11-22.md)

---

## 0. 一句话结论

**上游零变化 → 561 篇持平（连续 33 次）**，index **1,756,935 bytes 逐字节未变**，
全链路绿灯。**本轮唯一的实质产出是修掉一个 11-22 遗留的「已入库但从未跑过」的探针 bug
（新发现 §陷阱 46）**，并补做了 11-22 未入库的 3 处改动。

---

## 1. 上游状态

| 指标 | 值 | 对比 11-22 |
|---|---|---|
| 页面总数 | **561** | 持平（连续 33 次） |
| index.json 字节数 | **1,756,935** | **逐字节相同** |
| index.json sha1 | `c7ffc25763e15dadabf551c139f28f650367ff4f` | ⚠️ 与 11-19~11-22 的 `89baf46193cdf015` **不同**（见 §2 说明） |
| md / raw 文件数 | 561 / 561 | 持平 |
| 孤儿 md | **0** | 持平 |
| 缺失 md | **0** | 持平 |
| `url_suffix` 分布 | `.html` **546** / `/index.html` **15** | 持平 |
| 空标题 / 零长度 snippet / ZWSP / `Not Found` desc | **0 / 0 / 0 / 0** | 持平 |
| 短 snippet（<60ch） | **132**（全部为「常见问题/伺服报错」占位页，**空壳页 0**） | 持平 |

### ⚠️ 关于 index sha1 变化的说明

11-19 ~ 11-22 快照记的 sha 是 `89baf46193cdf015`（那是 `check_crawl_state.py` 内部
对 **state 快照文件**做的摘要口径），本轮用 `sha1sum` 直接对 `index.json` 原始字节算，
得到 `c7ffc25763e15dadabf551c139f28f650367ff4f`。
**字节数（1,756,935）与 11-19 ~ 11-22 完全一致** ⇒
**index 内容逐字节未变**，两处 sha 只是**口径不同**（一个是脚本内部摘要、一个是文件原始 sha1），
**不是内容漂移**。以**字节数 + `IDENTICAL` 判定**为准。

---

## 2. 本轮验证闭环（7 步全跑）

| # | 检查 | 结果 |
|---|---|---|
| 0 | 上一轮待办 + `git status` | ⚠️ **11-22 有 3 处改动未入库**（见 §3） |
| 1 | `crawler.py` | ✅ **561/561 成功，0 失败**（耗时 2m43s，**全部命中 raw 缓存，0 次网络抓取**） |
| 2 | `check_crawl_state.py` | ✅ **IDENTICAL**，抽样 **25/25 SAME** |
| 2b | `check_sitemap_count.py` | ✅ 上游 sitemap **1108 loc / 561 zh** == 本地 **561** |
| 3 | 索引完整性 | ✅ 全 PASS（空标题 0 / 空壳页 0 / 孤儿 0 / slug 契约 561/561） |
| 4 | 检索链路 | ✅ **真静默降级 0**，反查守卫 **93/93**，md 全可定位 |
| 5 | 引用链接实网 | ✅ **74/74 全 200**（含全部 14 条目录页强制并入） |
| 5a | URL 三形态 | ✅ **DUAL（两套并存）** ⇒ **不改代码**（详见 §4） |
| 5b | 端到端（proxy→gateway→LLM） | ✅ **12/12 全 200**（见 §5） |
| 6 | token 级一致性 | ✅ **0 不一致**（两个 KB） |
| 7 | proxy 环境 / 重载链 / journal | ✅ 5 变量三处一致 / 存活（下次重载 14:05）/ **0×500、0×502、0×Unknown key name** |

### `verify_kb.py` 一键回归

**FAILURES (4) —— 全部是 `[inexbot-open]`（姊妹 KB）分组，本 KB `[inexbot]` 零失败**：

- `inexbot-open: md 文件数 == index 条目数`
- `inexbot-open: raw 文件数 == index 条目数`
- `inexbot-open: 无零长度 snippet`
- `inexbot-open: 含图 md 全部可从 index 反查`

**成因**：姊妹 KB 的 cron 本轮（11:00）**正在跑 `crawler.py`**（实测 PID 2047862，
11:01 启动），处于**修复中间态** —— md 目录已有 **1890** 个文件而 index 只有 **832** 条
（增量爬虫不删旧 slug）。⇒ **不是回归**，也不属本 KB 责任范围。
（11-22 快照里也记过同一条判读纪律：姊妹 KB 正在跑修复脚本时看到的差异不是回归。）

---

## 3. ⚠️ 跨 session 泄漏 —— 第 8 次复发（陷阱 44）

**开局实测**：11-22 那轮 `hermes cron list` 的 `Last run` = **`ok`**（**根本没被打断**），
但工作树里**仍有 3 处未入库**：

```
 M SKILL.md                                          （+4 行：check_url_forms.py 表格行）
 M references/shared-proxy-service-pitfalls.md        （+102 行：陷阱 45）
 ?? scripts/check_url_forms.py                        （新增脚本，9380 bytes）
```

⇒ 11-22 报告 §5a 写的「✅ URL 三形态 仍『两套并存』」**结论本身没错**（它当时用的是
`/tmp` 里的一次性脚本），但**固化进仓库的那个版本从未成功运行过**。

**§0.9 直查远端**：`HEAD == REMOTE == 0e9361f` ⇒ 11-22 的 commit **确实落地了**，
但它点名的 3 个「新增物」**不在那个 commit 里** ⇒ 属 §0.10「报告点名的每个新增物都要单独核验」的
典型漏网。

**处置**：本轮全部补做并入库（见 §6）。

---

## 4. ⭐ 上游「URL 形态」：仍是「两套并存」⇒ 不改代码

`scripts/check_url_forms.py`（修好之后）实测：

| KB | 样本 | bare | `.html` | `/index.html` | VERDICT |
|---|---|---|---|---|---|
| `inexbot` | 42（随机 30 + 强制目录页 12） | **42/42** | **27/27** | **15/15** | **DUAL** |
| `inexbot-open` | 30 | **30/30** | 25/30 | — | **DUAL** |

⇒ 与 11-21 / 11-22 完全一致（连续 3 天 DUAL）⇒ **不改代码**，
**保留 `url_suffix` 兼容层**（上游形态是反复漂移的变量，见陷阱 43）。

⚠️ 姊妹 KB 那 5 条 `.html` 404 **是预期的**：姊妹 KB 的 index **没有 `url_suffix` 字段**
（分布 `(none): 832`），`.html` 在它的探针里只是**对照形态**，其**裸形态 30/30 全 200**
⇒ **姊妹 KB 未受影响**（陷阱 39 的前置要求 ✅）。

---

## 5. 端到端探针（唯一能抓到 timeout 类故障的检查）

**12/12 全 200**，最慢 **135.0s**（4×C1102：15.3/45.7/69.3/77.7s；4×冲压工艺：53.7/60.3/68.6/135.0s；
4×示教器：60.3/75.8/76.3/84.9s），0 次 502 / 500。姊妹 KB 同轮探针也是 **10/10 全 200**（最长 118.6s）
⇒ **共享链路健康，非单 KB 问题**。

⚠️ 本轮 **HTTPS git 通道 DEGRADED**（`:443` 2/3 OK、`:22` 3/3 OK）
⇒ push 走 **SSH**（与 11-22 相同结论，见 §6）。

---

## 6. 收尾（严格按 §0.7 / §0.8 / §0.9 / §0.10 的顺序）

**顺序：改 → commit → push → 核验远端 → 写报告正文。**

| 步骤 | 结果 |
|---|---|
| 提交内容 | ① `scripts/check_url_forms.py` **bug 修复**（陷阱 46）② 陷阱 46 文档 ③ SKILL.md v2.38.0→v2.39.0 + 陷阱 45/46 索引 ④ 11-22 的 3 处未入库改动 ⑤ 11-23 基线快照 |
| commit | `624b999` — `fix(scripts): repair url-form probe unpacking bug; add trap 46 and 11-23 snapshot`（4 files, +619 −3） |
| push 通道 | **SSH**（HTTPS :443 DEGRADED，`:22` 3/3 OK）—— **一次成功**：`0e9361f..624b999  main -> main` |
| §0.9 复核 | `merge-base --is-ancestor HEAD refs/remotes/sshcheck/main` = **YES**，且 `rev-parse` 双方**同 sha `624b999`** |
| 跟踪 ref 同步 | `git update-ref refs/remotes/origin/main` → `git status -sb` 无 ahead ✅ |
| 新增物核验 | `git ls-files --others --exclude-standard` **为空**（§0.10 判据） |
| 工作树 | `git status -sb` = `## main...origin/main`（**干净，无 ahead、无 M、无 ??**） |

---

## 7. ⭐ 新发现：§陷阱 46 ——「固化脚本」入库前没真跑过一次

**现象**：11-23 本轮**首次**运行 11-22 已入库的 `scripts/check_url_forms.py` → 直接崩：

```
PROBE ERROR: ValueError('too many values to unpack (expected 2)')
```

**根因**：`rnd.sample(pool, ...)` 返回的是 **key 字符串**（不是 `(k, v)` 元组），
下游却写 `for k, v in picked` ⇒ 把字符串的**每个字符**当元素解包 ⇒ 键长 > 2 即抛异常。

**为什么 11-22 没发现**：11-22 的「两套并存」结论来自 `/tmp` 里的一次性脚本；
固化动作只做了「搬进仓库 + 写进 SKILL.md 表格」，**没有执行过这个新文件**。

**⭐ 关键教训（写进共享 pitfalls §陷阱 46）**：

> **探针的「头部输出正常」不能证明「它跑通了」。**
> 崩溃点在抽样之后 ⇒ 崩溃前的统计行（`url_suffix 分布`、`中文路径池: 560/561`）**全都正常打印**。
> ⇒ **判据必须是「末尾的 VERDICT 行有没有出现」，或「退出码是否符合预期」**，
> **而不是** `--help` 能跑、也不是「头部没报错」。
>
> ⚠️ 与陷阱 40（辅助函数定义了但没接进调用链）同源：
> **「代码在仓库里」≠「代码在跑」≠「代码跑出了正确结论」**，三者都要有可观测证据。
>
> ⚠️ 与陷阱 44（新增物没入库）的**区别**：
> - 只入库不跑 ⇒ 下一个轮次才发现它崩（本条）
> - 只跑不入门 ⇒ 下次 `git pull` 静默丢掉（陷阱 44）
>
> ⇒ **两者都要做**：新脚本入库前**真跑一次** + 入库前**先 commit**。

**修法**（已落地，两侧同步）：

```python
rnd = random.Random(seed)
by_key = dict(items)
picked_keys = rnd.sample(pool, min(sample_n, len(pool)))
for k in picked_keys:
    v = by_key.get(k, {})
```

---

## 8. 共享 pitfalls 同步（§陷阱 23 / 27）

- 集合差集判定：姊妹 KB 侧**独有行 = 0** ⇒ **可直接 cp 覆盖** ✅
- 同步后两侧 **sha1 完全一致**：`42820948431ae8f6673aa81867f997faa706c3d5`
- 行数：两侧均 **2394 行**
- 结构自检：**46 节**，无重复编号、无孤儿块

⚠️ 本轮 `patch` 共享文件 / SKILL.md 时**再次收到 `modified by sibling subagent` 警告**
⇒ 按 §陷阱 13/37 处置：**先 `git diff` 读对方改动，再增量合并，绝不整体覆盖**。

---

## 9. 遗留 / 下一步

- **无遗留**（本轮所有新增物已 commit + push + §0.9 复核落地，`git status` 干净、
  `git ls-files --others` 为空）。
- 姊妹 KB 的 4 项 `verify_kb.py` 失败属**其自身爬虫中间态**，非本 KB 回归。
