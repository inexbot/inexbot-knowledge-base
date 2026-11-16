# 2026-11-16 爬取状态基线快照（inexbot KB）

> 本文件是 cron 每轮「验证闭环」的**基线快照**。
> 下一轮 cron 先读本文件 + `hermes cron list` 的 `Last run` 字段，再开始工作。

---

## 0. 本轮的「上一轮待办」处理

`hermes cron list`（11-16 11:00 开局实测）：

| Cron | Last run | 判读 |
|---|---|---|
| `inexbot-knowledge-base daily crawl` | `2026-11-15T11:17:32 ok` | ✅ **本 KB 上一轮正常收尾**（无 `error:`）⇒ 其报告结论可采信 |
| `inexbot-open-knowledge-base daily crawl` | `2026-11-15T11:18:40 error: RuntimeError: HTTP 429` | ⚠️ **姊妹 KB 上一轮被 429 打断** ⇒ 按 §0.6，其「已提交/已推送」结论作废 |

**本 KB 独立复核（形态 A / B 均不存在）**：

| 判据 | 实测 | 结论 |
|---|---|---|
| `git status -sb` | `## main...origin/main`（**无 `M`、无 `??`、无 ahead**） | 工作树干净 |
| `git show HEAD:SKILL.md \| grep '^version:'` | `version: 2.30.0` | — |
| `grep '^version:' SKILL.md` | `version: 2.30.0` | **HEAD == 工作树** ⇒ §0.7 规则已落地 |
| §0.9 直查远端 | `merge-base --is-ancestor HEAD refs/remotes/sshcheck/main` = **YES**；`rev-parse HEAD` 与 `rev-parse refs/remotes/sshcheck/main` **同为 `633a07c8`** | ✅ **push 真的落地**（不是「假 ahead」） |

⇒ **本 KB 连续 2 轮没有发生跨 session 泄漏**（11-15 补做了 11-14 的泄漏，本轮开局复核干净）。

**姊妹 KB 的未提交改动（不是本 KB 的活，但记录在案）**：

```
inexbot-open-knowledge-base:
  M references/.index-snapshot.json
  M references/shared-proxy-service-pitfalls.md      ← +52 行（陷阱 32 / 33）
```

⇒ 姊妹 KB 的 `shared-proxy-service-pitfalls.md` 工作树版本**与本 KB 的工作树版本逐字节相同**
（`diff` = IDENTICAL），**本轮无需同步**（§陷阱 23 的「姊妹独有行 = 0」已满足）。
⇒ 本 KB **不需要**替姊妹 KB 提交；但姊妹 KB 下一轮开局必须自己补 commit + push。

---

## 1. 爬取结果

| 项 | 值 |
|---|---|
| 爬取页面数 | **560**（成功 560 / 失败 0） |
| 网络抓取次数 | **0**（全部命中 `raw/` 缓存，「跳过（已存在）」） |
| 耗时 | 3 分 02 秒 |
| index 条目数 | **560** |
| index 大小 | **1,735,196 bytes** |
| index sha256 | **`922fbbb47782dfd8`** |
| md/ 文件数 | 560 |
| raw/ 文件数 | 560 |
| 孤儿 md | **0** |
| missing md | **0** |

> ⭐ **index 逐字节第 9 天相同**（11-07 → 11-16 连续 9 天 sha 均为 `922fbbb47782dfd8`）。

---

## 2. 漂移判据（双路佐证）

### 2.1 `check_crawl_state.py --sample 25`

```
index.json : 560 entries, 1,735,196 bytes, sha=922fbbb47782dfd8
md/ files  : 560   raw/ files: 560
missing md : 0   orphan md: 0
snippet<60ch: 132   empty titles: 0   ZWSP in title/desc: 0
health     : OK
drift      : 抽样 25 页 -> {'SAME': 25}
verdict    : IDENTICAL
exit code  : 0
```

> ⭐ **本轮连 `IMG_ONLY` 都没有**（25/25 全 `SAME`）—— 11-14 那轮还出现过 1 条 `IMG_ONLY`。

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
| proxy 环境变量 | `check_proxy_env.py --units` | 线上进程 + `/etc` unit + repo 模板 **三处 5 变量 sha12 逐项一致** |
| 重载链 | `check_reload_timer.py` | 定时器 tid=1970700，age **2.79h**，下次重载 13:18:08；内存 560 == 磁盘 560 |
| 共享文件结构 | `check_shared_pitfalls_structure.py` | 两个 KB 各 33 sections / 36 sub-headings / 1529 行，**结构一致**（仅 2 处历史遗留重复行） |
| token 级一致性 | `check_token_consistency.py`（**本轮新增**） | inexbot 0 处不一致、inexbot-open 0 处不一致；key 集合相同 = True |

### 3.1 journal 侧（按进程启动时间切片，§陷阱 12）

proxy PID 1954151，启动于 `2026-11-14 11:17:36`，切片统计：

| 状态码 | 次数 | 说明 |
|---|---|---|
| **200** | 40 | — |
| **500** | **0** | ✅ |
| **502** | **0** | ✅ |
| 404 | 8 | **全部是外部扫描器**：`GET /`、`GET /version`、`GET /server-info`（与 KB 无关） |
| `Unknown key name` | **0** | ✅ systemd `Environment=` 块解析正常 |

---

## 4. ⭐ 本轮新增：短 snippet 的独立分类脚本

**新增** `scripts/check_short_snippet_class.py` —— 把 `snippet<60ch: 132` 这个粗筛计数
**拆成「真故障」和「正常占位页」两类**。

| 分类 | 数量 | 判据 |
|---|---|---|
| **空壳页（真 BUG）** | **0** | md 前 2000 字符含 `Not Found`，或 `description == 'Not Found'` |
| **占位页（正常）** | **132** | 正文本来就短，无 `Not Found` 标记 |
| md 无法定位 | 0 | — |

占位页分布：**132/132 全部在 `常见问题/伺服报错` 路径下**
（伺服报错码页，正文就是「码 - 含义 + 一句说明」）。

抽样正文（确认有实质内容，不是空文件）：

```
[ 59 ch] # 0x0001 - 超速 >纳博特科技官方知识库 # 0x0001 - 超速 伺服电机速度超过设定值（PA23）
[ 64 ch] # 0x0002 - 电流采样偏置值异常 ... 电流采样偏执异常
[ 50 ch] # 0x0003 - 电机振动 ... 电机振动
[ 67 ch] # 0x0004 - 位置超差 位置偏差计数器的数值超过设定值（PA17）
[ 59 ch] # 0x0005 - 平均电流过载 电机平均负载率过高
```

### ⚠️ 本脚本初版踩的坑（已修，值得记住）

初版自己重写了一套 md 定位逻辑（`unquote` → `/`→`-`），
**漏了 crawler 的调用约定 `slugify(link.lstrip("/").rstrip(".html"))** 的
`lstrip("/")` 和 `.html` 剥离两步 ⇒ **132 条全部报「md 无法定位」** ——
一个看起来像「KB 大面积损坏」的**假阳性**。

⇒ **修法：直接 `importlib` 复用 `crawler.py` 里的 `slugify()`**，不要自己重写。
⇒ 这与 **§陷阱 11 / §陷阱 24** 同源：**跨组件的 slug 契约必须复用实现，不能复刻。**
⇒ **写完这类脚本先用「已知健康」的样本自检**（本次是 132 条全找不到 ⇒ 立刻知道是脚本错了）。

---

## 5. ⭐ 本轮新增：token 级一致性脚本

**新增** `scripts/check_token_consistency.py` —— 把
`references/proxy-runtime-freshness.md` 里的 token 级比对方法**固化成可重复执行的脚本**，
一次覆盖两个 KB。

实测：

```
inexbot       : 磁盘 560 / 内存 560, key 集合相同 True, token 级不一致 0
inexbot-open  : 磁盘 817 / 内存 817, key 集合相同 True, token 级不一致 0
=> PASS
```

脚本内已把 **§陷阱 18** 的三个坑写进注释并强制遵守：
① 内存侧用 `_doc_scores`（不是 `_index_data`）；
② 磁盘侧字段名用 `title` / `description` / `content_snippet`（不是 `desc` / `content`）；
③ 两边用同一套 jieba 规则（`len(w) >= 2`）；
④ 先 `mod.load_all_indexes()`。
并且**主动检测「差异数整齐等于条目数」这一取错名的指纹**并给出提示。

---

## 6. 端到端探针（§5b）

按 §5b 的编排铁律，**探针在轮次「一开始」就用 `terminal(background=true, notify_on_complete=true)` 起跑**，
然后并行做 2/3/4/5 步，最后收结果。

**本 KB 结果：12/12 全 HTTP 200，0 次失败**（exit 0）。

| 查询 | 4 次耗时 | 结果 |
|---|---|---|
| `C1102 控制器 通讯接口 有哪些` | 126.1s / 102.5s / 43.9s / 83.6s | ✅ 4/4 = 200 |
| `冲压工艺 手册 参数设置` | 181.0s / 77.7s / 108.7s / 158.4s | ✅ 4/4 = 200 |
| `示教器 操作手册 功能说明` | 183.6s / 121.3s / 135.7s / 70.5s | ✅ 4/4 = 200 |

- 最慢 **183.6s**、最快 **43.9s**、中位约 **122s** —— 远低于 proxy 的 `HERMES_TIMEOUT=1800`
- **0 次 502、0 次 500、0 次客户端 timeout**
- 姊妹 KB 同时段探针（`/tmp/e2e-2026-11-16.log`）**同样 0 次 502 / 500**
  ⇒ 两侧同时段都全绿，**没有共享链路停顿的迹象**

> 📌 探针日志路径：`/tmp/e2e-inexbot-2026-11-16.log`（本 KB）
> 与 `/tmp/e2e-2026-11-16.log`（姊妹 KB 写的）。

---

## 7. git 状态（本轮收尾）

| 项 | 值 |
|---|---|
| commit | **`39498cf`** — `docs(skill): add 2026-11-16 crawl snapshot, short-snippet classifier, token consistency check`（4 files changed, 441 insertions） |
| 变更内容 | `SKILL.md`（版本 2.30.0 → **2.31.0**、新增 2 个脚本说明行、新增本快照表格行、页面总数连续次数 26 → 27）+ `references/crawl-state-2026-11-16.md`（新增）+ `scripts/check_short_snippet_class.py`（新增）+ `scripts/check_token_consistency.py`（新增） |
| push | 第 1 次 **TLS 网络错误**（`GnuTLS recv error (-110)`，§陷阱 30 的 github.com:443 不稳，**不是鉴权失败**）→ 重试第 2 次成功：**`633a07c..39498cf  main -> main`** |
| §0.9 直查远端 | `merge-base --is-ancestor HEAD refs/remotes/sshcheck/main` = **YES**；`rev-parse HEAD` 与 `rev-parse refs/remotes/sshcheck/main` **同为 `39498cf4dbd98839b5a78b2ee3bebda179147344`** ⇒ **push 真的落地** |
| 收尾 `git status -sb` | `## main...origin/main`（**无 ahead、无 `M`、无 `??`**）⇒ 工作树干净 |
| HEAD 版本号 vs 工作树版本号 | `2.31.0` == `2.31.0` ⇒ §0.7 检查通过 |

> ⭐ **本轮收尾严格按 §0.7 的时序**：**改 → commit → push → 写报告正文**。
> 本文件的内容在 push 之后补写（只改本 reference 文件的 e2e 段），
> 补写后**立即单独 commit + push**（见 §7.1）。

### 7.1 收尾后的第二次 commit（补写 e2e 结果）

本文件 §6 的 e2e 数据是探针跑完才拿到的 ⇒ 属于「push 之后才产生的改动」。
按 §0.7 的**时戳自检**，这类改动的 mtime 晚于最后一次 commit ⇒ **最容易被下一轮的中断丢掉**。
⇒ 补写后**立刻单独 commit + push**，并在下一轮开局复核。

---

## 8. 待办 / 遗留

- **本 KB：无遗留**（工作树干净 + push 已用 §0.9 直查远端确认落地）。
- **姊妹 KB `inexbot-open`**：工作树有 2 个未提交文件（`references/.index-snapshot.json`、
  `references/shared-proxy-service-pitfalls.md` +52 行），**由姊妹 KB 的 cron 自己补 commit + push**，
  本 KB 不越界代劳（但已确认共享文件内容与本 KB 一致，无需同步）。
- **本轮无 proxy restart**（上游零变化 ⇒ 内存索引无需刷新；且 restart 会打断姊妹 KB 正在跑的探针）。
