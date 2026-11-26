# 纳博特 KB 爬取基线快照（2026-11-26）

## 一、总体状态

| 项 | 值 |
|---|---|
| 页面总数 | **562**（与 11-25 持平，**连续 35 次**） |
| index.json | **1,764,336 bytes**，sha12 `726ba3ba259d`（sha1 `7708bdb8d770…`） |
| md / raw | **562 / 562**，孤儿 0，缺失 0 |
| 爬虫 | **562/562 成功**，失败 0，耗时 **3m19s**（全部命中 raw 缓存，0 次网络抓取） |
| index mtime | 2026-11-26 11:04:14 |
| 漂移 | **IDENTICAL**，抽样 25 页 → **SAME 25/25** |
| sitemap 对账 | 上游 zh **562 == 本地 562**（total loc 1109） |
| url_suffix 分布 | `.html` **547** / `/index.html` **15** |
| proxy | PID **2016323**（自 11-20 未变），11:06:20 自动重载 → 内存 **562** == 磁盘 562 |
| 下线页面 | **0** |

## 二、逐项验证结果（全部通过）

| 检查 | 结果 |
|---|---|
| `crawler.py` | 562/562 成功，失败 0 |
| `check_crawl_state.py --sample 25` | **IDENTICAL**；抽样 **25/25 SAME**；空标题 0、ZWSP 0 |
| `check_sitemap_count.py` | 上游 zh **562 == 本地 562** |
| `check_citation_links.py` | **75/75 全 200**（含全部 15 个目录页），404 = 0 |
| `check_retrieval_chain.py` | **真静默降级 0**；md 全部可定位 |
| `check_url_to_index_key.py` | **93/93** 命中；静默降级 0；全文命中 40 / 4000 上限 53 |
| `check_token_consistency.py` | 两个 KB 均 **0 不一致**（inexbot 562/562、inexbot-open 832/832） |
| `check_short_snippet_class.py` | **132 条全是「伺服报错」占位页，空壳页 0**，md 定位 0 失败 |
| `check_proxy_env.py --units` | 5 个变量三处 sha12 **逐项一致**（exit 0） |
| `check_reload_timer.py` | **存活**；tid=2079554，上次触发 07:06:20，下次 12:06:20；内存/磁盘同步 |
| `check_url_forms.py` | **两个 KB 都是 DUAL（两套并存）** ⇒ **不改代码**，保留 `url_suffix` 兼容层 |
| `check_shared_pitfalls_structure.py` | 两个真实文件均 **PASS**（48 sections / 2647 lines） |
| `verify_kb.py` | `[inexbot]` **10/10 全 PASS**；4 项 FAIL **全属 `[inexbot-open]`** |
| journal（按 PID 2016323 启动时间切片） | **0×500、0×502、0×Unknown key name** |

## 三、本轮的两个动作

### ① 跨 session 泄漏第 11 次复发 —— 开局即补做

11-25 那轮 `Last run` 带 **`error: RuntimeError:`**（§0.6 ⇒ 其报告正文里的「已提交/已推送」结论一律作废）。
独立复核发现：

- 工作树有 **2 文件 20 行未入库**（`SKILL.md` + `references/crawl-state-2026-11-25.md`）
- 两处 mtime（**11:18:54** / **11:16:36**）**晚于**最后一次 commit（**11:12:15**）⇒ §0.7 时戳自检命中
- `git status -sb` 显示 `[ahead 2]` —— 但 §0.9 直查远端证实 **HEAD == REMOTE == `05163c7`** ⇒ 那是**假 ahead**（HTTPS fetch 失败导致本地跟踪 ref 停在旧 sha），**不是**「有 commit 没 push」
- ⭐ **`HEAD:SKILL.md` 里查不到「第 0.11 步」** ⇒ 11-25 写下的那条规则**自己也没进版本库** ⇒ 这正是 §0.7 说的「写规则 ≠ 规则被执行」

处置：`git add -A` → commit `c439ab4` → **SSH push 一次成功**（`05163c7..c439ab4`）→
§0.9 复核 `merge-base --is-ancestor` = **YES**、`rev-parse HEAD` 与 `refs/remotes/sshcheck/main` **同为 `c439ab4`**。

### ② ⭐ 修正「共享 pitfalls 结构自检」脚本 —— 统一方向取错了

**发现**：姊妹 KB 于 11-25 独立发现并写入 **§陷阱 48**（「移植别人的『重写版』审计脚本 = 可能丢判据」），
并把 `check_shared_pitfalls_structure.py` 重写为**带 `SIG_LINES = 8` 固定长度前缀签名**的版本。
而 11-25 我方那轮的「重写版」**丢掉了「末尾孤儿体」检测**。

**实证（构造「把最后一节正文抄一份追加到 EOF」的损坏文件）**：

| 脚本 | 结果 | 判读 |
|---|---|---|
| 我方 11-25 重写版 | **exit 0** | ❌ **假绿！漏报真损坏** |
| 姊妹版（带 `SIG_LINES`） | **exit 1**（报 `DUPLICATE_BLOCK`） | ✅ 正确抓到 |

⇒ **「新版」不等于「更好」** —— 姊妹版才是正确的那个（它保留了「固定长度前缀签名」判据，
而「整段正文 sha256」无法替代：最后一节正文延伸到 EOF，孤块若是它的复制体会被吸进自己 ⇒ 签名改变 ⇒ 真损坏反而漏掉）。

**处置**：
- 共享文档 `references/shared-proxy-service-pitfalls.md` + 脚本 `scripts/check_shared_pitfalls_structure.py`
  **同步为姊妹版**（sha1 两侧逐项一致）
- 新增 `scripts/test_shared_pitfalls_structure.py`（姊妹版的回归测试）→ 在我方 repo 实跑 **exit 0**
  （case1 完好文件 → exit 0；case2 末尾孤儿体 → exit 1）
- SKILL.md 版本 **2.41.0 → 2.42.0**，脚本表格行补记「统一方向取错」的实证
- commit `8449319` → SSH push 一次成功 → §0.9 复核 HEAD == REMOTE == `8449319`

## 四、姊妹 KB（`inexbot-open`）状态 —— 非本 KB 回归

`verify_kb.py` 的 4 项 FAIL **全部带 `[inexbot-open]` 前缀**：

| FAIL 项 | 实测 |
|---|---|
| md 文件数 == index 条目数 | **1890 vs 832** |
| raw 文件数 == index 条目数 | **1890 vs 832** |
| 无零长度 snippet | **34 条**（全是 `/zh/06.控制器/01.文档/`、`/zh/07.示教器/01.文档/` 一类**目录/分类索引页**，不是 404 空壳页） |
| 含图 md 全部可从 index 反查 | **73/177** |

⇒ 独立核实：**姊妹 KB 的爬虫本轮确实在跑**（其 `references/.index-snapshot.json` mtime 更新为
`2026-11-26 11:05:15`，且 `ps` 抓到其 `check_e2e_request.py` PID 2080801 于 11:01 起跑）
⇒ 属**姊妹 KB 自身的索引重建中间态**，**不是本 KB 的回归**。
（姊妹 KB 的 34 条零长度 snippet 与 11-06~11-25 期间的历史遗留同源：目录页本身就是索引页，无正文。）

## 五、端到端（proxy → gateway → LLM）

见下方「端到端结果」小节。

## 六、提交与推送

| 仓库 | commit | push | 复核 |
|---|---|---|---|
| `inexbot-knowledge-base` | `c439ab4`（补泄漏）→ `8449319`（脚本统一 + SKILL.md v2.42.0） | **SSH 两次均一次成功** | `merge-base --is-ancestor` = **YES**，`HEAD == REMOTE == 844931951e9f8aaab42fee832a264bdbdbe5a4bf` |

> ⚠️ 本轮 push **全程走 SSH**：HTTPS 端点在本机历史上多次 130s 连接超时（§陷阱 30），
> 不值得在 HTTPS 上连等超时。

## 七、遗留

- **本 KB 无遗留**：工作树干净、无未跟踪文件、`HEAD == REMOTE`。
- **姊妹 KB 有 1 处未入库**：`inexbot-open` 的 `references/.index-snapshot.json`（mtime 刷新，属其自身轮次范围，不在本 repo 路径下）。
