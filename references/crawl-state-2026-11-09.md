# inexbot KB 基线快照 — 2026-11-09

> 本 KB 最新基线快照。上一份：[crawl-state-2026-11-08.md](crawl-state-2026-11-08.md)

## 一句话结论

**上游零变化 → 560 篇持平**（连续 20 次持平）。索引、slug 契约、检索链路、引用链接、
proxy 环境、重载链全部健康。本轮**补做 11-08 被 HTTP 429 打断的提交**，
并**修正了 skill 里一条错误的 URL→index-key 查表规则**（见第三节）。

## 一、爬取

| 项目 | 值 |
|---|---|
| 爬取页数 | **560 / 560 成功，0 失败** |
| 耗时 | **2:48.0** |
| 网络请求 | **0**（全部 560 页命中 `raw/` 缓存 → 全程「跳过（已存在）」） |
| `index.json` | **1,735,196 bytes**，sha256 `922fbbb47782dfd8…`（**与 11-07 / 11-08 逐字节相同**） |
| md / raw | 560 / 560（missing 0，**orphan 0**） |
| 漂移 verdict | **IDENTICAL**（抽样 60 页：**SAME 60 / IMG_ONLY 0**） |

> ⚠️ 本轮**一次网络抓取都没有** → 「560/560 成功」完全不代表上游没变，
> 结论来自 `check_crawl_state.py` 的**字节级 diff + 60 页实网抽样**。
> 本轮连 `IMG_ONLY`（VitePress 资源 hash 重命名）都没有 —— 比 11-08 更干净。

## 二、验证闭环（`[inexbot]` 分组 10/10 PASS）

| 步骤 | 结果 |
|---|---|
| `check_crawl_state.py`（默认 25 页） | **IDENTICAL** / exit 0 / 孤儿 0 / 零宽 0 / 空标题 0 |
| `check_crawl_state.py --sample 60` | **SAME 60 / IMG_ONLY 0**（exit 0） |
| `verify_kb.py` | **`[inexbot]` 10/10 PASS**（560/560/560 / 零长度 snippet 0 / `Not Found` 0 / 空标题 0 / 零宽字符 0 / 裸 `%` 0 / slug 契约 **560/560** / 含图反查 **158/158**） |
| 独立完整性审计 | 零长度 snippet **0** / `Not Found` **0** / 空标题 **0** / 零宽字符 **0** / 裸 `%` **0** / 缺字段 **0** |
| 短 snippet 深判（10 查询 × top-5 = 47 条） | **真静默降级 (`==800`) = 0**；**24 条全文命中**（`snippet chars == md chars`）；**23 条 4000 字符上限截断**（长手册，设计如此）；**snip > md 的异常 = 0** |
| 内存 vs 磁盘 | **token 级 0 不一致**（560↔560，jieba `len>=2` 同规则），**0 单边 key** |
| 引用链接实网 | proxy 生成 **45 条去重 URL → 45/45 全 200**；`%25` 双重编码 **0** |
| proxy 环境 | **5 个变量全部到位**（live process + `/etc` unit + repo 模板 **三处 sha12 逐项一致**），`HERMES_TIMEOUT=1800` ✅（`check_proxy_env.py --units` exit 0） |
| 重载链 | **存活**，定时器 tid=1894538（2026-11-09 10:03:58 出生）→ 下次重载 **15:03:58**；内存 560 == 磁盘 560 ✅ |
| 端到端（proxy→gateway→LLM） | 见第三节末表 |
| 端口 / 遗留进程 | 只有 8643 + 8642；**无遗留压测进程** |

`verify_kb.py` 的 4 项 `[inexbot-open]` FAIL 与 11-03 ~ 11-08 **逐项一致**，
属姊妹 KB 范围（`1855 vs 799` = 姊妹侧历史死缓存 md，非本 KB 回归），非本 KB 回归。

## 三、⭐ 本轮核心发现：skill 里那条「URL→index-key 查表」规则**是错的**

### 症状

11-08 那轮在 skill 里写下了这条规则：

> **用 proxy 返回的 `url` 反查 `index.json` 要先处理 `&` / `%26`**：
> proxy 返回的 url 里 `&` 被编码成 **`%26`**，而 `index.json` 的 key 里是**字面 `&`**。
> **✅ 查表要两步**：先试精确匹配，miss 再 `unquote(path)` 匹配。

本轮实测：**这条规则的第二步 `unquote(path)` 是错的** —— 它会**破坏中文的 `%XX` 编码**，
导致几乎每一次查表都 miss，进而误报「md not found」。

### 真实编码规则（实测 47 条 proxy 结果验证）

| 字符 | `index.json` 的 key | proxy 返回的 url | 归一化动作 |
|---|---|---|---|
| 中文 | **percent-encoded**（`%E6%8A%80…`） | 同左（`%E6%8A%80…`） | **不动** |
| `&` | **字面 `&`** | **`%26`** | `%26` → `&` |
| `+` | **字面 `+`** | **`%2B`** | `%2B` → `+` |

⇒ **正确归一化 = 只替换 `%26`→`&` 和 `%2B`→`+`，绝不做整体 `unquote()`。**

### 实测命中率（10 查询 × top-5 = 47 条 proxy 结果）

| 策略 | 命中 |
|---|---|
| **A：`path.replace("%26","&").replace("%2B","+")`** | **47 / 47** ✅ |
| B（skill 现文档）：先精确匹配，miss 再 `unquote(path)` | **1 / 47** ❌ |
| C（11-08 实测用过）：精确匹配 + `unquote` 兜底 | 46 / 47（`+` 那条漏） |

### 为什么 C 也不是最优

C 在 `&` 那条上靠「精确匹配」救回来了，但 **`+` 那条救不回来**：
- index key：`…%E8%BE%93%E5%85%A5%E8%BE%93%E5%87%BA%E7%B1%BB**+**%E5%AE%9A%E6%97%B6%E5%99%A8…`
- proxy url：`…%E8%BE%93%E5%85%A5%E8%BE%93%E5%87%BA%E7%B1%BB**%2B**%E5%AE%9A%E6%97%B6%E5%99%A8…`

⇒ 唯一正确解就是**只替换这两个字符**，不做整体解码。

### 该条 md 确实存在（排除「内容缺失」）

`zh-操作手册-25.01版本-输入输出类+定时器类+运算类手册.md`（17,916 字节）**在磁盘上存在**，
proxy 也**正确读到了正文**（snippet 4000 字符 = 命中 4000 上限）。
**这 100% 是审计脚本的查表 bug，不是 KB 故障** —— 差点误报成回归。

> 💡 **通则**：反向查表时**只做最小必要的归一化**。
> `unquote()` 是「解码」语义，而 index key 的编码态是**混合的**
> （中文已编码、`&`/`+` 未编码）→ 整体解码必然破坏其中一半。

## 四、端到端实测（proxy → gateway → LLM）

见本轮 cron 报告。判读要点不变：
- 客户端 timeout **1860s** > proxy 的 `HERMES_TIMEOUT=1800` ✅（trap 22）
- timeout 类故障是**随机**的 → **单次 200 不能证明通过，必须连打多次**
- 本轮与姊妹 KB 的 e2e 探针**同时在跑**（11:04 / 11:07 起跑）→ 共 34 次请求压 gateway
- 看到 502 先跑 `scripts/diagnose_502_timeout.py` 做归因，**别只记「随机超时」**

## 五、收尾

| 项目 | 结果 |
|---|---|
| 11-08 遗留提交 | **已补做** —— 11-08 那轮被 HTTP 429（Token Plan 配额）打断在 commit 之前，工作树里躺着 `M SKILL.md` + `M references/shared-proxy-service-pitfalls.md`（63 行）**没进库** |
| 提交 | `2652679 docs: sync shared proxy pitfalls from sister, add trap 21-23 index (11-08 leftovers)` |
| 推送 | ✅ `f81f1b4..2652679` → `origin/main`（一次成功） |
| 共享文件同步 | `references/shared-proxy-service-pitfalls.md` 两份 **sha1 归一**（`fdc364656f990254be31bfaae5c4bed71d1eccf1`）—— 本 KB 是**超集**（多 2 段知识：陷阱 14 第 4 次复发案例 + 560 基线），按 trap 23「姊妹独有行 = 0 → 可 cp 覆盖」反向同步 |
| 工作树 | **干净**（`git status -sb` 仅 `## main...origin/main`） |
