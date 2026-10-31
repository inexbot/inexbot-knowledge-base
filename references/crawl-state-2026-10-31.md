# inexbot KB 爬取状态快照 — 2026-10-31

> 本文件记录 `inexbot`（doc.inexbot.com）知识库每日爬取的**基线与判读结论**。
> 姊妹 KB `inexbot-open` 的快照在
> `inexbot-open-knowledge-base/references/crawl-state-2026-*.md`。

## 一、本轮结果

| 项目 | 值 |
|---|---|
| 爬取页数 | **558 / 558**（0 失败） |
| 耗时 | **2:43** |
| 网络请求 | **0**（全部命中 `raw/` 缓存，日志全「跳过（已存在）」） |
| index.json | **1,722,769 bytes**，sha 前 16 位 `d565c39c433370c3` |
| index mtime | 2026-10-31 11:03:13 |
| md / raw 文件数 | 558 / 558（missing 0，orphan 0） |
| 漂移 verdict | **IDENTICAL** —— 抽样 25 页全部 `SAME` |
| proxy 进程 | PID **1779868**，启动于 2026-10-30 11:16:36（23:53 elapsed） |
| 代理健康 | `/health` → `{"status":"ok","inexbot":{"docs":558},"inexbot-open":{"docs":799}}` |

> ✅ index.json 逐字节与 2026-10-30 相同（sha `d565c39c…`）→ **558 篇连续多日零新增**。
> ✅ index.json mtime（11:03）**晚于** proxy 启动时间（10-30 11:16）→ **不需要 restart proxy**。

## 二、验证闭环（`verify_kb.py` 全量回归）

`[inexbot]` **11/11 全 PASS**：

```
[PASS] index 条目数 > 0 — 558
[PASS] md 文件数 == index 条目数 — 558 vs 558
[PASS] raw 文件数 == index 条目数 — 558 vs 558
[PASS] 无零长度 snippet（= 抓到 404 空壳页）
[PASS] 无 description=='Not Found'
[PASS] 无空标题
[PASS] 标题/描述无零宽字符 U+200B
[PASS] key 里无裸 %（否则引用链接必 404）
[PASS] 所有 index key 都能定位到 md 文件 — 558/558
[PASS] 含图 md 全部可从 index 反查 — 156/156
[PASS] 引用链接实网抽样全部 HTTP 200 — 12/12
```

补充实测（脚本化，非目测）：

| 检查 | 方法 | 结果 |
|---|---|---|
| 零长度 snippet | `index.json` 全量遍历 | **0** |
| `description == 'Not Found'` | 同上 | **0** |
| 空标题 | 同上 | **0** |
| 裸 `%`（非法 percent 编码） | 正则 `%(?![0-9A-Fa-f]{2})` | **0** |
| 标题/描述含零宽字符 | U+200B/200C/200D/FEFF | **0** |
| md slug 契约 | 复用 proxy 的 `_md_slug_candidates()` | **558/558 解析成功**，OSError 0 次 |
| proxy 内存 vs 磁盘 | **token 级**比对（与 proxy 同一套 jieba 规则） | key 集合相等，**0 处不一致** |
| 检索链路 | 5 组查询 × top-5 | 正文命中 `snippet_len=4000`，**无 800 静默降级** |
| 引用链接 | 15 条实网 curl | **15/15 HTTP 200**，`%25` 计数 **0** |
| 端到端 | `POST /v1/chat/completions` | **HTTP 502** = gateway 超时 → **检索成功**（判读表见共享 pitfalls §陷阱 3） |

### 132 条「短 snippet」逐条核验

`snippet<60ch: 132` 全是伺服报错系列的**一行占位页**（如 `# 0x0001 - 超速`，50–70 字节）。
逐条比对 md 实际字节数：**0 条是 404 空壳页、0 条缺 md 文件**
→ **正常，不是静默降级**。

### proxy 运行时

- 重载链**活着**：主进程 + 定时器线程（tid 1786103，启动于 2026-10-31 07:16:54
  = 进程启动 +20h = 第 4 次 5h 排期）
- `/proc/<pid>/environ` 四变量全部到位（`PROXY_PORT` / `HERMES_URL` / `HERMES_API_KEY` / `SKILL_NAME`）
- `journalctl` 的 `Unknown key name` 计数 = **0**；HTTP 500 计数 = **0**
- 端口仅 **8643**（proxy）+ **8642**（gateway），**无遗留压测进程**

## 三、本轮的实际发现与修正

### 1. 文档里的事实错误：`hermes...arch` 是**输出脱敏**，不是截断占位符 ⚠️

**旧文档（10-29/10-30 写入）称**：「`/etc` 里的 `HERMES_API_KEY` 是被截断的占位符
`hermes...arch`（len=13），与代码默认值 `hermes-website-search`（len=21）不同」。

**2026-10-31 实测推翻**：

| 判据 | 结果 |
|---|---|
| `char codes` | 完整的 `HERMES_API_KEY=hermes-website-search`（36 字符含前缀） |
| sha256 前 12 位 | `23760f4462da` —— 与代码默认值、gateway `config.yaml` **三处一致** |
| 渲染模板 vs `/etc` 部署版 | **逐字节相同**（sha `6ff7986b5024`） |
| gateway `api_server.api_key` | `hermes-website-search`（config.yaml:448） |

**真相**：本工具链（Hermes terminal 输出层）的 **secret redaction**
把疑似密钥替换成中间省略形式 —— **只影响显示，不影响文件内容**。

**危害**：照字面理解会去「修复」一个**根本没坏**的 key → **反而引入真故障**。
已修正 `SKILL.md` 与 `references/kb-cron-verification-workflow.md`，
并在共享权威文件新增 **§陷阱 9**。

### 2. 共享运维坑文件已与姊妹 KB 同步

`references/shared-proxy-service-pitfalls.md`（9,713 B → 本轮扩充后更大）
与姊妹 KB 的副本 **sha1 完全一致**（`1cf6cb5ab123189f…`），
姊妹 KB 的 cron 已于 11:09 把它入库（commit `b0a6fd2`）→ 本轮在本地副本上补了 §陷阱 9。

### 3. 姊妹 KB `inexbot-open` 本轮独立健康（非本 KB 回归）

- index **2,450,869 bytes** —— 与 10-29/10-30 基线**逐字节相同**
- 799 条 index 全部可达（可达数 == index 条目数）
- **1056 个孤儿 md** = 不可达死缓存（878 locale 前缀 + 178 旧版裸名），架构上不影响检索
- 34 条零长度 snippet → md 文件存在但正文本身为空（上游空目录页，46–49 字节）

`verify_kb.py` 因此仍报 `[inexbot-open]` 4 项 FAIL —— **与 10-30 完全一致，非新增回归**。

## 四、遗留事项

- 姊妹 KB 的 1056 个死缓存 md 仍建议清理（需其 `refresh_drift.py` 类脚本）——
  本轮未越界处理（姊妹 KB 的 cron 同时在跑，工作树不干净）
- 姊妹 KB 工作树有未提交改动（`SKILL.md` / `references/crawl-state-2026-10-31.md` /
  `scripts/check_staleness.py` / `?? scripts/check_index_hygiene.py`）→ **属其 cron 职责**
- 本 KB 工作树本轮已全部提交（见 commit hash）
- 两个 KB 的 cron 仍同在 11:00 窗口；本轮实测互不冲突（本 KB 11:03 完，姊妹 KB 11:09 完）
