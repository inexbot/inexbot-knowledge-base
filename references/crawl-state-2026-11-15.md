# 2026-11-15 爬取状态基线快照（inexbot KB）

> 本文件是 cron 每轮「验证闭环」的**基线快照**。
> 下一轮 cron 先读本文件 + `hermes cron list` 的 `Last run` 字段，再开始工作。

---

## 0. 本轮的「上一轮待办」处理（跨 session 泄漏第 7 次复发，已闭环）

`hermes cron list` 显示**两个 KB 的上一轮（11-14）都以 `error: HTTP 429` 收尾**
（`Last run: 2026-11-14T11:18:02 error: RuntimeError: HTTP 429: 已达到 Token Plan 用量上限`）。
⇒ 按 §0.6，**11-14 报告正文里的「已提交 / 已推送」结论一律作废**，本轮独立复核。

**复核结果（形态 A —— 改动没进 commit，真·跨 session 泄漏）**：

| 判据 | 实测 |
|---|---|
| `git status -sb` | `## main...origin/main` + **` M references/stamping-process-manuals.md`** |
| 泄漏内容 | 6 增 2 删 —— 冲压工艺手册版本归属的 2026-11-14 二次复核、正文自述与侧边栏不一致、「工艺切换入口」澄清 |
| HEAD 版本号 vs 工作树版本号 | `2.29.0` == `2.29.0` ⇒ §0.7 的「规则落地」检查通过 |

⇒ 11-14 那轮的成果**确实没进版本库**（第 7 次复发）。本轮已补做：

- `git commit` → `563ba6e`（`docs(stamping): record 2026-11-14 recheck of stamping manual version attribution`）
- `git push` → **`d97bf7c..563ba6e  main -> main`**（**一次成功，未触发 §陷阱 30 的 130s 超时**）
- **§0.9 直查远端确认**：SSH fetch 后 `merge-base --is-ancestor HEAD refs/remotes/sshcheck/main` = **YES**，
  `git rev-parse HEAD` 与 `git rev-parse refs/remotes/sshcheck/main` **同为 `563ba6e`** ⇒ **push 真的落地**
- 本轮收尾时 `git status -sb` = `## main...origin/main`（**无 ahead、无 M**）⇒ 工作树干净

> 💡 **本轮再次验证 §0.7/§0.8 的时序规则有效**：把 commit + push 放在**报告正文之前**，
> 本轮虽被 429 打断过一次（11-14），但本轮完全没有再被打断 ⇒ 规则本身是对的，
> 上一轮只是**没执行**（规则在 HEAD 里，但执行顺序没落实）。

---

## 1. 上游与索引状态

| 项 | 值 | 与 11-14 对比 |
|---|---|---|
| 页面总数 | **560** | 持平（**连续 26 次**） |
| `index.json` 大小 | **1,735,196 bytes** | **逐字节相同** |
| `index.json` sha256 前 16 位 | **`922fbbb47782dfd8`** | 相同（与 11-07 至 11-14 同值，**连续 8 天**） |
| `md/` 文件数 | **560** | 相同 |
| `raw/` 文件数 | **560** | 相同 |
| 缺失 md | **0** | 相同 |
| 孤儿 md | **0** | 相同 |
| 本轮网络抓取 | **0 次**（全部命中 raw 缓存） | 相同 |
| 空标题 / 标题含 U+200B | **0 / 0** | 相同 |

**结论：上游 doc.inexbot.com 零变化**（drift probe verdict = `IDENTICAL`，抽样 25 页 = **25/25 SAME**，本轮连 IMG_ONLY 都没有）。
上游 sitemap 独立佐证：**1107 loc / 560 zh / 560 unique** == 本地 index 560 ⇒ 上游既无新增也无下线。

---

## 2. 验证闭环（7 步全过）

| 步骤 | 结果 |
|---|---|
| ① 爬虫 | **560/560 成功，0 失败**，耗时 3 分 20 秒（本轮 0 次网络抓取，全部命中 raw 缓存） |
| ② 漂移探针 | **IDENTICAL**（25 页抽样 **25 SAME**），orphan md 0，missing md 0，health OK |
| ②' sitemap 对账 | **PASS** — 560 zh == 560 local（独立于本地缓存的漂移佐证） |
| ③ 索引完整性 | **全 PASS** — 无零长度 snippet / 无 `description=='Not Found'` / 无空标题 / 无裸 `%` / 标题描述无零宽字符 / **所有 index key 都能定位到 md 文件（560/560）** |
| ④ 检索链路 | **真静默降级 0**（反查守卫 93/93：41 全文命中 + 52 命中 4000 上限）；检索链路独立脚本：**md 全部可定位**，短 snippet 全部是「页面本身短」的全文命中 |
| ⑤ 引用链接 | **60/60 HTTP 200**，0 个 404/410，0 网络错误（CJK 池 559） |
| ⑤b 端到端 | **12/12 全 200**，**0 次 502**（详见 §4） |
| ⑥ 收尾 | commit + push **在写报告正文之前完成** ✅（见 §0） |

### 短 snippet 分类（独立核查，132 条）

`check_crawl_state.py` 报 `snippet<60ch: 132` —— 本轮用**独立脚本**分类确认：

| 项 | 值 |
|---|---|
| 短 snippet 总数 | **132** |
| `description == 'Not Found'` | **0** |
| `content_snippet` 为空 | **0** |
| md 正文含 `Not Found` | **0** |
| **404 空壳页（真 BUG）** | **0** |
| **合法占位页** | **132** —— **全部**落在 `常见问题` 分类下（伺服报错系列，正文就一行） |

⇒ 与 11-14 的分类结论一致：**短 snippet 不是故障**。

---

## 3. Proxy 运行时状态

| 项 | 值 |
|---|---|
| proxy PID | 1954151（起于 2026-11-14 11:17:37） |
| 磁盘 index.json | inexbot = **560** |
| proxy 内存索引 | inexbot = **560** / inexbot-open = 817 ⇒ **内存 == 磁盘** |
| 重载链 | **存活** —— 定时器线程 tid=1959345，上次触发 2026-11-15 07:17:55，下次 12:17:55（77 分钟后） |
| 环境变量 | **5 个全部到位且三处一致**（运行进程 environ / `/etc` unit / repo 模板，sha12 逐项相同） |
| `HERMES_TIMEOUT` | **1800**（sha12 `e49ec846db75`，四处一致） |
| 端口占用 | 只有 **8643**（proxy）+ **8642**（gateway）⇒ 无遗留压测进程 |
| nginx :80 | 不参与本链路（无 `proxy_pass`） |
| token 级比对 | 磁盘 560 vs 内存 560，**0 不一致**、0 missing |

### `verify_kb.py` 的 4 项 FAIL —— **全部是 `[inexbot-open]` 分组，本 KB 0 回归**

| FAIL 项 | 归属 | 判读 |
|---|---|---|
| md 文件数 == index 条目数（1873 vs 817） | `[inexbot-open]` | 姊妹 KB 的**历史死缓存**（孤儿 md），与本 KB 无关 |
| raw 文件数 == index 条目数（1873 vs 817） | `[inexbot-open]` | 同上 |
| 无零长度 snippet | `[inexbot-open]` | 姊妹 KB 侧问题 |
| 含图 md 全部可从 index 反查（73/177） | `[inexbot-open]` | 姊妹 KB 侧问题 |

⇒ **按 skill 的分组判读规则，`[inexbot]` 分组下 0 项 FAIL。**
⚠️ 本轮已确认**姊妹 KB 没有在跑修复脚本**（`ps` 只有两个 `check_e2e_request.py`），
⇒ 这 4 项**不是「修复中间态」**，是姊妹 KB 的真实待办，**应由姊妹 KB 的 cron 负责**。
⇒ 但按 skill「2026-10-29 更正」：**不要**再当成「已知的无害遗留」放过 —— 姊妹 KB 需自行闭环。

---

## 4. 端到端探针（唯一能抓到 timeout 类故障的检查）

`scripts/check_e2e_request.py` —— 3 个查询 × 4 次 = **12 次真实请求**（proxy → gateway → LLM）：

| 查询 | 次数 | 结果 | 耗时区间 |
|---|---|---|---|
| `C1102 控制器 通讯接口 有哪些` | 4 | **4/4 HTTP 200** | 35.7s – 55.4s |
| `冲压工艺 手册 参数设置` | 4 | **4/4 HTTP 200** | 50.3s – 103.6s |
| `示教器 操作手册 功能说明` | 4 | **4/4 HTTP 200** | 57.7s – 115.8s |

**SUMMARY: 12/12 succeeded，0 次 502。**

- 姊妹 KB 的独立探针**同时段**也在跑（`/tmp/e2e-2026-11-15.log`）→ **两侧同时 0 次 502** ⇒ 无共享链路异常
- proxy journal 在 10:50 之后 **502/500 计数 = 0**
- ⚠️ 按 skill 的提醒：**「本轮全绿」≠「timeout 类故障已修复」** —— 502 是随机事件，
  唯一可靠的归因判据仍是「elapsed 是否精确等于当前 `HERMES_TIMEOUT`（1800s）」+ gateway 侧 start-time 戳。
  本轮无 502 ⇒ 无需归因。

> 💡 **本轮探针编排经验**：把 e2e 探针放在**轮次一开始**用 `background=true, notify_on_complete=true`
> 起跑，再并行做 2/3/4/5 步，最后收结果 —— 12 次请求耗时约 **10 分 40 秒**（35.7s–115.8s），
> 串行放最后会撞工具调用上限（§5b 编排铁律，本轮严格执行）。

---

## 5. 本轮「无变化」判定

- 上游 **560 页持平（连续 26 次）**，`index.json` **连续 8 天逐字节相同**
- drift verdict **IDENTICAL**（25/25 SAME）
- **不需要** `refresh_drift.py`、**不需要** 重启 proxy、**不需要** `--force` 重爬

---

## 6. 本轮新增的观察（供下轮参考）

1. **`scan_kb_topic.py` 是 AND 语义**（多词查询要求**全部**词都出现在 title/description 里）：
   - `scan_kb_topic.py "冲压工艺 手册"` → **0 命中**
   - `scan_kb_topic.py "冲压"` → **3 命中**（冲压工艺2.0手册 / 冲压工艺3.0手册 / 冲压工艺常见问题）
   - `scan_kb_topic.py "示教器"` → **23 命中**
   ⇒ **查主题时应先用「单个核心词」枚举，再用标题人工筛选** ——
   直接塞一串词会得到假 0 命中，**极易误判成「KB 没有这个主题」**。

2. **`process(wait)` 的 timeout 会被 clamp 到 60s**（§陷阱 19 实测复现）⇒
   长任务一律 `background=true` + `notify_on_complete=true`，收尾用 `poll`。

3. **用相对路径 grep `ps` 会漏判**（本轮一度以为 e2e 探针已退出，实际是 `ps` 模式写成绝对路径不匹配）：
   ⇒ **判「探针是否还在跑」要 grep 脚本名（`check_e2e_request.py`），不要 grep 含目录的完整路径。**

---

## 7. 基线速查（本轮实测值，下轮对比用）

```
pages               = 560        (持平 26 次)
index_bytes         = 1735196
index_sha12         = 922fbbb47782dfd8
md_files            = 560
raw_files           = 560
orphan_md           = 0
missing_md          = 0
snippet_lt_60       = 132       (全部为合法伺服报错占位页，404 空壳 0)
empty_titles        = 0
zwsp_in_title       = 0
slug_contract       = 560/560
silent_degrade_800  = 0
citation_links_200  = 60/60
reverse_lookup      = 93/93
token_mismatch      = 0
proxy_docs_memory   = 560  (== disk)
reload_timer_age    = 3.72h      (链存活，下次重载 12:17:55)
e2e                 = 12/12 HTTP 200, 0 x 502
proxy_env_vars      = 5/5 三处一致
```

---

*生成于 2026-11-15 11:00–11:20（Asia/Shanghai）。下一轮 cron 请先读本文件。*
