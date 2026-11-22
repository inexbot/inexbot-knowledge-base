# 纳博特知识库（inexbot / doc.inexbot.com）基线快照 — 2026-11-22

> 本轮 cron：2026-11-22 11:00 起跑。上一轮 = 2026-11-21（`Last run: ok`）。
> 结论一句话：**上游零变化，561 持平（连续 32 次）；全链路绿灯；顺手补齐了 11-21 未入库的
> 规则改动（trap 43 文档化 + 共享 pitfalls 同步）并已 push 落地。**

---

## 1. 爬虫（crawler.py）

| 项 | 值 |
|---|---|
| 抓取页面数 | **561** |
| 失败页面数 | **0** |
| 网络抓取次数 | **0**（全部命中 `raw/` 缓存，日志为「跳过（已存在）」） |
| 耗时 | 3 分 19 秒 |
| 索引路径 | `/home/ecs-user/.hermes/kb/inexbot/index.json` |
| Markdown | `/home/ecs-user/.hermes/kb/inexbot/md`（561） |

⚠️ 「561/561 成功」只是**起点**（增量爬虫对上游正文变更无感），下面的漂移/索引/引用链接/
端到端检查才是交付物。

---

## 2. 漂移探针（check_crawl_state.py）

```
index.json : 561 entries, 1,756,935 bytes, sha=89baf46193cdf015
md/ files  : 561   raw/ files: 561
missing md : 0   orphan md: 0
snippet<60ch: 132   empty titles: 0   ZWSP in title/desc: 0
health     : OK
drift      : 抽样 25 页 → {'SAME': 25}
verdict    : IDENTICAL
exit code  : 0
```

**index 与 11-19 / 11-20 / 11-21 逐字节相同**（sha `89baf46193cdf015`，1,756,935 bytes）
⇒ 连续 4 天零字节跳变。

### 独立于本地缓存的佐证（check_sitemap_count.py）

| 项 | 值 |
|---|---|
| sitemap `total <loc>` | 1108 |
| sitemap `zh <loc>` | **561**（unique 561） |
| 本地 index 条目数 | **561** |

⇒ 上游既无新增也无下线。

---

## 3. 索引完整性对账

| 检查 | 结果 |
|---|---|
| index 条目数 | 561 |
| md 文件数 / raw 文件数 | 561 / 561（**孤儿 0、缺失 0**） |
| 零长度 snippet | **0** |
| `description == 'Not Found'` | **0** |
| 空标题 | **0** |
| 标题/描述含零宽字符 | **0** |
| key 含裸 `%` | **0** |
| index key → md 可定位 | **561/561** |
| 含图 md 可反查 | **159/159** |
| `url_suffix` 分布 | `.html` **546** / `/index.html` **15** |
| index 侧 `content_snippet == 800` | 199 条（**正常摘要窗口**，非降级） |

### 短 snippet 独立分类（check_short_snippet_class.py）

```
短 snippet 条目数 : 132
  占位页（正文本来就短，正常）: 132
  空壳页（Not Found，是 BUG）  : 0
  md 无法定位                  : 0
分布：常见问题/伺服报错 132
```
⇒ 132 条全部是「伺服报错」系列占位页，**空壳页 0**。

---

## 4. 检索链路（check_retrieval_chain.py，字符数判据）

| 判据 | 计数 |
|---|---|
| 抽样结果总数 | 60 |
| **真静默降级（== 800）** | **0** |
| 全文命中（chars == md chars） | 34 |
| 命中 4000 字符上限 | 26 |
| 短页全文命中 | 9 |
| md 找不到 | **0** |

⇒ 无静默降级，md 全部可定位。

---

## 5. 反查守卫（check_url_to_index_key.py）

```
total proxy results              : 93
URL->index-key hit (norm)        : 93 / 93
true silent-degradation(==800)   : 0
no-md lookup                     : 0
```
⇒ 归一化按 KB 分派（`inexbot` 只换 `%26`/`%2B`；`inexbot-open` 整体 `unquote`）后 93/93 命中。

### token 级一致性（check_token_consistency.py）

| KB | 磁盘 | 内存 | key 集合 | token 不一致 |
|---|---|---|---|---|
| inexbot | 561 | 561 | 相同 | **0** |
| inexbot-open | 832 | 832 | 相同 | **0** |

⇒ proxy 内存索引 == 磁盘 `index.json`，逐条一致。

---

## 6. 引用链接实网可达性（check_citation_links.py）

```
index entries: 561
forced-in directory pages (url_suffix=/index.html): 14
sampled: 74   (cjk pool: 560)
HTTP 200/3xx : 74
HTTP 404/410 : 0
network err  : 0
=> PASS: 全部引用链接可达
```
⇒ **74/74 全 200**（含全部目录页）。

---

## 7. ⭐ 上游「URL 形态」三形态探测（用 index.json 真实条目，非手拼 URL）

**判别表（陷阱 39 / 43）**：

| 日期 | 裸路径 | `.html` 后缀 | 目录页 `/index.html` | 判定 |
|---|---|---|---|---|
| 2026-11-19 | **404** | 200 | 200 | 上游收紧为「只认后缀」⇒ 当时必须改代码 |
| 2026-11-21 | 200 | 200 | 200 | 放宽为「两套并存」⇒ 不改代码 |
| **2026-11-22（本轮）** | **200** | **200** | **200** | **仍是「两套并存」⇒ 不改代码** |

**本轮实测（42 条真实 index 条目，强制并入全部 15 个目录页）**：

| KB | 形态 | 200/3xx |
|---|---|---|
| inexbot | bare | **42 / 42** |
| inexbot | `+.html` | **27 / 27** |
| inexbot | `+/index.html` | **15 / 15** |
| inexbot-open | bare | **15 / 15**（姊妹 KB 未受影响 ✅） |

⇒ 形态仍为「两套并存」，**非破坏性** ⇒ **本轮不改代码**（保留 `url_suffix` 兼容层：
上游一周内切过两次且方向相反，删掉风险高 —— 陷阱 43）。

⚠️ **探测必须用 `index.json` 的真实条目**：本轮初版脚本对姊妹 KB 用「key 含 `%`」筛 CJK 池
⇒ 姊妹 KB 的 key 是**明文中文**（0 个含 `%`）⇒ 抽样 0 条，差点误判成「姊妹 KB 挂了」。
⇒ **判别方式：先看该 KB 的 key 编码态，再决定池的筛选条件**（同 §陷阱 24/25）。
⚠️ 同理，**明文中文路径必须先 `quote()` 再交给 urllib**（本轮实测：不 quote 会得到
`-1` 网络错误而非 HTTP 状态码 ⇒ 误报成「大批失败」）。

---

## 8. proxy 服务状态

| 项 | 值 |
|---|---|
| proxy PID | **2016323**（启动于 2026-11-20 11:04:53，连续运行 48h） |
| `/health` | `status=ok`，inexbot docs=**561**（== 磁盘 561） |
| 环境变量 | 5 个变量，**运行进程 / `/etc` unit / repo 模板三处 sha12 逐项一致** ✅ |
| `HERMES_TIMEOUT` | 1800s（sha12 `e49ec846db75`） |
| 重载链 | **存活** — 定时器线程 tid=2037359，上次触发 2026-11-22 08:05:26，下次 **13:05:26** |
| journal（按进程启动时间切片） | **0×500、0×502、0×Unknown key name** |

---

## 9. 端到端请求（proxy → gateway → LLM）

探针**起跑于轮次最开始**（§陷阱 28 / 编排铁律），与姊妹 KB 探针并发。

```
runs/query = 4 | client timeout = 1860s | model = definitely-not-a-real-model-xyz
  [C1102 控制器 通讯接口 有哪些]     HTTP 200  50.1s / 32.9s / 78.0s / 69.4s
  [冲压工艺 手册 参数设置]           HTTP 200  38.7s / 43.6s / 58.1s / 77.6s
  [示教器 操作手册 功能说明]         HTTP 200  58.3s / 64.6s / 56.5s / 85.4s

SUMMARY: 12/12 succeeded
```

⇒ **12/12 全 200**，**0 次 502 / 0 次 500**；最慢 **85.4s**，
远低于 `HERMES_TIMEOUT=1800s`（与 11-09 的 1039.8s 长尾同向印证：1800s 至今仍在承重）。
姊妹 KB 同时段也是 **12/12 全 200** ⇒ 共享链路本轮健康（并发压 gateway 未触发上游停顿）。

---

## 10. ⭐ 本轮的文档性改动（补齐 11-21 未入库部分）

### 10.1 上一轮（11-21）的规则改动从未进库 —— §0.7 复发（第 7 次）

11-21 那轮 `Last run` 虽显示 `ok`，但**工作树里的 SKILL.md 改动（v2.36.0 → v2.37.0）
与 `upstream-url-suffix-routing.md` §0 的新增内容从未 commit**：
- 11-21 最后一次 commit 时间：**11:17:27**
- 两处改动的 mtime：**11:18:35 / 11:18:18** ⇒ **均晚于 commit** ⇒ §0.7「时戳自检」命中

⇒ 本轮开局按 §0.7 独立复核发现并补做。

### 10.2 共享 pitfalls 两侧重新对齐

- 集合差集判定（§陷阱 23）：姊妹 KB 侧多出 3 行（陷阱 43 的更完整表述）
  ⇒ **不能直接 cp 覆盖**（会丢内容）⇒ 采用**逆向合并**：把我方那 1 行替换为姊妹侧的 3 行超集。
- 合并后两侧**逐行完全一致**：各 **1577 行**，双向差集 **0 / 0**，
  结构自检 43 节 / 74 个子标题 / 2148 行，**无重复块、无孤儿块**。
- ⚠️ 本轮 `patch` 共享文件时再次收到 **`modified by sibling subagent` 警告**
  ⇒ 按 §陷阱 13/37 处置：**先读对方内容、比对集合差集，再增量合并，绝不整体覆盖**。

---

## 11. 提交与推送（§0.7 / §0.8 / §0.9 全部核验）

| 步骤 | 结果 |
|---|---|
| commit | `d582143` — `docs(skill): add upstream URL-form drift guidance (trap 43), sync shared pitfalls`（3 files, +115 −6） |
| push（HTTPS 第 1 次） | ❌ `GnuTLS recv error (-110)` —— **通道问题，非鉴权失败**（陷阱 35/38） |
| push（HTTPS 第 2 次） | ❌ `Failed to connect to github.com port 443 after 130623 ms` |
| §0.9 直查远端 | `ANCESTOR_NO`（远端仍在 `7568cae`）⇒ **push 确实没落地** |
| push（**改走 SSH**） | ✅ `7568cae..d582143  main -> main` |
| §0.9 复核 | **HEAD == REMOTE == `d582143`**，`merge-base --is-ancestor` = **YES** |
| 跟踪 ref 同步 | `git update-ref refs/remotes/origin/main` → `git status -sb` 恢复无 ahead ✅ |

⭐ **HTTPS 端点连续两次失败后，改走 SSH push 一次成功** —— 这比「重试 HTTPS」更可靠
（绕开 github.com:443 的不稳定，见陷阱 30）。§0.9 直查远端仍是唯一判真伪的判据。

---

## 12. 本轮实测结论

| # | 检查 | 结果 |
|---|---|---|
| 1 | crawler.py | ✅ 561/561，0 失败，0 次网络抓取 |
| 2 | 漂移探针 | ✅ IDENTICAL，25/25 SAME |
| 2b | sitemap 对账 | ✅ 上游 zh 561 == 本地 561 |
| 3 | 索引完整性 | ✅ 全 PASS，孤儿 0、空壳页 0 |
| 4 | 检索链路 | ✅ 真静默降级 0，md 全可定位 |
| 5 | 引用链接 | ✅ **74/74 全 200**（含全部目录页） |
| 5a | URL 三形态 | ✅ 仍「两套并存」⇒ **不改代码**；姊妹 KB 15/15 未受影响 |
| 5b | 端到端 | ✅ **12/12 全 200**（见下） |
| 6 | 反查守卫 / token 级 | ✅ 93/93 / 0 不一致（两个 KB） |
| 7 | proxy 环境 / 重载链 / journal | ✅ 5 变量三处一致 / 存活 / 0×500 0×502 |
| 8 | 收尾 | ✅ commit `d582143` + SSH push + §0.9 复核落地 |

**上游漂移结论：零变化。** 页面数 561 持平（连续 32 次），index 逐字节未变。
