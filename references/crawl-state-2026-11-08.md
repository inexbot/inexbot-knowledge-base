# inexbot KB 基线快照 — 2026-11-08

> 本 KB 最新基线快照。上一份：[crawl-state-2026-11-07.md](crawl-state-2026-11-07.md)

## 一句话结论

**上游零变化 → 560 篇持平**（连续 19 次持平）。索引、检索链路、引用链接、proxy 环境全部健康。
本轮**补做 11-07 被 HTTP 429 打断的提交**，并**修掉 `scan_kb_topic.py` 的两个真 bug**
（md 路径解析 1/560 → 560/560；snippet 长度串行串值）。

## 一、爬取

| 项目 | 值 |
|---|---|
| 爬取页数 | **560 / 560 成功，0 失败** |
| 耗时 | **2:46.4** |
| 网络请求 | **0**（全部 560 页命中 `raw/` 缓存 → 全程「跳过（已存在）」） |
| `index.json` | **1,735,196 bytes**，sha256 `922fbbb47782dfd8…`（**与 11-07 逐字节相同**） |
| md / raw | 560 / 560（missing 0，**orphan 0**） |
| 漂移 verdict | **IDENTICAL**（抽样 60 页：**SAME 59 / IMG_ONLY 1**） |

> ⚠️ 本轮**一次网络抓取都没有** → 「560/560 成功」完全不代表上游没变，
> 结论来自 `check_crawl_state.py` 的**字节级 diff + 60 页实网抽样**。
> 唯一差异仍是 VitePress 资源 hash 重命名（`IMG_ONLY`，按设计不算漂移）。

## 二、验证闭环（`[inexbot]` 分组全绿）

| 步骤 | 结果 |
|---|---|
| `check_crawl_state.py` | **IDENTICAL** / exit 0 / 孤儿 0 / 零宽 0 / 空标题 0 |
| `check_crawl_state.py --sample 60` | **SAME 59 / IMG_ONLY 1**（比默认 25 页样本更强） |
| `verify_kb.py` | **`[inexbot]` 10/10 PASS**（560 / 560 / 560 / 零长度 snippet 0 / `Not Found` 0 / 空标题 0 / 零宽字符 0 / 裸 `%` 0 / slug 契约 **560/560** / 含图反查 **158/158**） |
| 独立完整性审计 | 零长度 snippet **0** / `Not Found` **0** / 空标题 **0** / 零宽字符 **0**（显式 codepoint 探测）/ md 缺失 **0** / 孤儿 **0** |
| 短 snippet 深判 | proxy 侧 30 条结果：**真静默降级 (`==800`) = 0**；13 条**全文命中**（`snippet chars == md chars`）；17 条是 **4000 字符上限截断**（长手册，设计如此） |
| 内存 vs 磁盘 | **token 级 0 不一致、0 单边 key**（560↔560，jieba `len>=2` 同规则） |
| 引用链接实网 | proxy 生成 12 条抽样 → **12/12 全 200**；`%25` 双重编码 **0** |
| proxy 环境 | **5 个变量全部到位**（live process + `/etc` unit + repo 模板 **三处 sha12 逐项一致**），`HERMES_TIMEOUT=1800` ✅（`check_proxy_env.py --units` exit 0） |
| 重载链 | **存活**，定时器 tid=1883325（2026-11-08 09:03:46 出生）→ 下次重载 **14:03:46**；内存 560 == 磁盘 560 ✅ |
| 端到端（proxy→gateway→LLM） | **12/12 全 200**，最慢 246.4s，**0 次 502** |
| 端口 / 遗留进程 | 只有 8643 + 8642；**无遗留压测进程** |

`verify_kb.py` 的 4 项 `[inexbot-open]` FAIL 与 11-03 ~ 11-07 **逐项一致**，属姊妹 KB 范围，非本 KB 回归。

## 三、⭐ 本轮核心发现一：`scan_kb_topic.py` 的 md 路径规则**解析率只有 1/560**

11-07 那轮（被 429 打断）新写了 `scripts/scan_kb_topic.py`，用于
「回答主题性问题前一次列全该主题所有页面」。**本轮实测发现两个真 bug**。

### Bug 1：md 文件名规则与 crawler 的 `slugify()` 不一致 → 解析率 1/560

| 规则 | 解析率 |
|---|---|
| 脚本原用 `key.lstrip('/').replace('/', '-')` | **1 / 560** ❌ |
| crawler 实际：`slugify(link.lstrip('/').rstrip('.html'))`，**先 `unquote` 再 `/`→`-`** | **560 / 560** ✅ |

> `index.json` 的 key 是 **percent-encoded**（`/zh/%E6%8A%80...`），
> 而 md 文件名用的是**解码后的中文**（`zh-技术资料-通讯协议&地址码.md`）。
> 不先 `unquote` 就永远对不上。
> 这正是 skill「改了 crawler 的 `slugify()` 仍然必须同步检查三处」警告的**又一实例**。

**修复**：脚本内改为与 crawler 同序的 `unquote → /→- → 去非法字符 → MD5 截断`，
并加 `md_filename()` 单一入口（`crawler.py` line 519 的调用形态）。
**修复后实测 560/560 全部命中。**

### Bug 2：snippet 长度打印的是**上一轮的循环变量**（`val` 泄漏）

```python
for key, title, desc, _ in hits:      # ← 用 _ 丢掉了 value
    snippet = (val.get("content_snippet") or "")   # ← val 是上一次 for 循环的残留
```

→ **每一行打印的都是「上一条命中项」的 snippet 长度**，且首行用的是
「最后一次循环迭代」的残留值 → **长度列全是错的**。
修复：循环元组带上 `val` 并直接使用它。

### Bug 3（本轮新发现）：「短 snippet」note 的正确判据要**比字符数，不是字节数**

`verify_kb.py` 打出 `note: 短 snippet 247 inexbot / …` 后，按 skill 的说法
「md_bytes == snippet_len → 页面本身就很短」，本轮实测**这个判据在中文页面上会误判**：
中文 1 字 = **3 字节**，`0x0050 - 风扇故障报警（未实现）` 的 md 是
**71 字符 / 157 字节**，而 proxy snippet 是 **71 字符** → 其实是**全文命中**，
但按字节比（157 ≠ 71）会被误判成「md 比 snippet 长 → 要查」。

**⇒ 正确判据**：**proxy snippet 的字符数 vs md 的字符数**：

| 判据 | 含义 |
|---|---|
| proxy snippet **== 800** | **真静默降级**（回落到了 index 摘要） |
| proxy snippet **chars == md chars** | **全文命中** ✅ |
| proxy snippet **chars < md chars** | md 本身长 → 命中 4000 字符上限（设计如此） |

本轮按字符数判：**真静默降级 = 0**，全文命中 13 条，4000 上限截断 17 条。

### 附带：probe 自身的假阳性（不是 KB 缺陷）

proxy 返回的 `url` 里 `&` 被编码成 `%26`，而 `index.json` 的 key 里是**字面 `&`**
→ 用 `url.replace(base, "")` 直接查 index 会 miss → 误报「md not found」。
**修法**：查表时先试精确匹配，miss 再 `unquote(path)` 匹配。
（`通讯协议与地址码` 就是这种情况；其 md 文件**确实存在**。）

## 四、⭐ 本轮核心发现二：11-07 的「已提交」结论**又是错的**（第 3 次复发）

`hermes cron list` 显示 11-07 那轮：

```
Last run: 2026-11-07T11:41:05 error: RuntimeError: HTTP 429: 已达到 Token Plan 用量上限 (2056)
```

**带 `error:` ⇒ 上一轮在收尾阶段被中断** ⇒ 报告正文里的「已提交/已推送」一律视为未完成。

**本轮开工实测 `git status`**：

| 文件 | 状态 | 行数 |
|---|---|---|
| `SKILL.md` | `M` | +19 |
| `references/large-family-kb-navigation.md` | `M` | +71 |
| `references/stamping-process-manuals.md` | `??`（新文件） | 287 行 |
| `scripts/scan_kb_topic.py` | `??`（新文件） | 84 行（修后 118 行） |

= **489 行 + 2 个新文件没进版本库**，与 10-28 / 11-01 / 11-02 / 11-06 同一模式（陷阱 14）。

**⇒ 已在本轮补做**：commit **`c8cd84a`**，已 push（`43ef345..c8cd84a`），工作树干净。

**⇒ 战术调整（已生效）**：本轮把 **commit + push 放在生成报告正文之前**执行
（先 commit → 再 push → 再写文档 → 最后才写报告），
这样即便再被 429 打断，**代码与文档成果已经在版本库里**。

## 五、提交与部署状态

| 仓库 | HEAD | 状态 |
|---|---|---|
| `inexbot-knowledge-base` | **`c8cd84a`** | ✅ 已 push（`43ef345..c8cd84a`），0/0 同步，工作树干净 |
| `hermes-skill-proxy` | `abb129c` | 未改动本轮（无 proxy 侧变更），`HERMES_TIMEOUT=1800` 在位 |

## 六、遗留事项

1. ✅ **proxy 内存索引 560 == 磁盘 560**（11-07 遗留的 559≠560 已随 09:03:46 自动重载自愈）。
2. ⚠️ **`verify_kb.py` 的 4 项 `[inexbot-open]` FAIL** —— 姊妹 KB 范围，与前五轮逐项一致。
3. ⚠️ **HTTP 429 配额风险仍在**（11-06 / 11-07 连续两轮因此失败）。
   本轮已把 commit/push 前置，但**报告本身仍可能成为被掐断的最后一环** →
   ⇒ 建议把「基线快照文档」的写入也前置到 push 之后立刻执行。
4. ⚠️ **姊妹 KB 的 e2e 与本 KB 的 e2e 撞在 11:00 同一时段** —— 本轮已错开
   （等姊妹 12/12 跑完才启动本轮），但**没有根治**。
   姊妹 KB 的 cron 也该自己错开（建议它延后 15–30 分钟）。
