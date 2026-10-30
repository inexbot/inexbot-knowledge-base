# KB cron 的真正交付物：验证闭环，不只是「爬虫跑过了」

2026-10-25 沉淀。适用于 `inexbot-knowledge-base` / `inexbot-open-knowledge-base` 的每日 cron。

## 核心认知

**「crawler 报 558/558 成功」不是交付物，是起点。**

增量爬虫的「成功」只意味着「raw/ 和 md/ 已存在 → 跳过 → 没报错」。
它对以下三类故障**完全无感**，而这些故障的共同特征是：
**所有表层健康检查全绿，但用户拿到的是坏结果**。

| 故障 | 表层检查表现 | 用户实际体验 |
|---|---|---|
| 上游正文被改 | 558/558 成功 | 检索命中旧内容 |
| 引用链接双重编码 | `/health` 全绿 | **回答里每个链接都 404** |
| md slug 解析失败 | `/health` 全绿 | 正文静默降级成 800 字摘要，附图全丢 |
| sitemap `&amp;` 未转义 | 558/558 成功 | 该页正文永久为空 |

**所以 cron 的交付物应该是「验证闭环」**——爬取 → 漂移探针 → 检索链路实测 →
链接可达性 → 修复 → 部署 → 回归。历史上两个 KB 的 cron 都在「爬取成功」就结束了，
把上面那三个 bug 留了几周才被发现。

## 标准 cron 流程（6 步）

### 0. 先读上一轮的待办（2026-10-28 新增，最容易被漏掉的一步）

`hermes cron list` 的 `Last run` 字段包含**上一轮报告的全文**，包括它的「待办」清单。

```bash
hermes cron list 2>&1 | grep -A 60 "Last run"
```

2026-10-28 现场：10-27 那轮列了 4 条「待办（本次工具额度用尽，未完成）」——
「部署 proxy 补丁」「提交并推送两处改动」「清理测试进程」「补写 skill 文档」——
**全部跨 session 泄漏了一整天**，直到 10-28 的 cron 扫到 `Last run` 才补做。

**规则**：
- 上一轮有「待办 / 未完成 / TODO」→ 那些就是本次的**前置任务**，先清
- 清不掉 → 报告里**不要**声称相关项「已修复」
- 有新增待办 → 同样要留下可追踪的证据（新 PID / commit hash）

> 💡 这条为什么重要：上一轮 agent 可能**只改了磁盘没部署**，
> 「已修复」的措辞会让下一轮直接跳过 → 补丁永远悬在半路。
> 详见 `references/proxy-runtime-freshness.md` §陷阱 4。

### 1. 爬取

```bash
python3 ~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/crawler.py
```

### 2. 漂移探针（增量爬虫的必要配套）

```bash
python3 ~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/check_crawl_state.py
```

verdict 三态：`IDENTICAL`（真稳态）/ `CONTENT-DRIFT`（需 `--force` 或 `refresh_drift.py`）/
`CHANGED: N -> M`。**只有 IDENTICAL 才算「无变化」**。

> ⚠️ **`orphan md > 0`（md/raw 数 > index 条目数，但 index 条目数没变）
> = 上游把页面搬了目录**（改了 URL 路径），不是内容变更。
> `crawler.py` 增量爬虫**不会**清理旧 slug → 补跑 `refresh_drift.py`
> （**唯一会清孤儿的脚本**），**且必须重启 proxy**。
> 完整流程见 `references/upstream-url-migration.md`。

### 3. 索引完整性对账（廉价、高价值）

一次 `execute_code` 跑完这几条断言（任一失败都说明有隐藏故障）：

```python
# 零长度 snippet = 抓到 404 空壳页的信号
# description == "Not Found" = 同上
# 空标题 = 丢掉标题 ×4 权重
# key 里含裸 % = 双重编码 / 链接必 404
# index key → md 文件是否可解析（slug 契约）
```

#### ⚠️ 修 bug 前先看姊妹 KB 是否已修（2026-10-29 立规）

两个 KB 是**姊妹关系**（同一套 crawler 逻辑、只换目标站点），
且**姊妹 KB 经常比本 KB 先修好同类问题** —— 2026-10-29 现场：
姊妹 KB 的 `crawler.py` 早已有 `clean_text()`（去 U+200B 零宽字符）和标题兜底链，
而 `inexbot-open` 一直漏着，导致它的 index 卫生指标全面落后：

| 指标 | `inexbot`（姊妹） | `inexbot-open`（修复前） | 修复后 |
|---|---|---|---|
| 含 U+200B 的条目 | 0 | **764** | 0 |
| 空标题条目 | 0 | **39** | 0 |

**规则：动手改 `crawler.py` 之前，先 grep 姊妹 KB 的同名脚本**：

```bash
grep -n "def clean_text\|og:title\|200B" \
  ~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/crawler.py
```

姊妹 KB 有现成实现 → **直接移植**（连注释一起），不要从零重写。

#### ⚠️ 字面零宽字符写进源码会被静默吞掉（2026-10-29 踩坑）

用编辑工具把 U+200B **字面量**写进 Python 源码的字符集时，它**被无声地丢掉了** ——
写完检查发现字符集里只剩 `U+200C U+200D U+FEFF`，`U+200B` 不见了。
不检查就上线，`clean_text()` 会**漏掉最常见的那个零宽字符**，且没有任何报错。

**对策：字符集用显式 codepoint 构造，绝不写字面量。**

```python
_ZERO_WIDTH = "[" + "".join(chr(c) for c in (0x200B, 0x200C, 0x200D, 0xFEFF)) + "]"
```

**写完立刻验证字符集没被吞**：

```python
for i, ln in enumerate(src.splitlines(), 1):
    if "_ZERO_WIDTH" in ln:
        print(i, repr(ln), [hex(ord(c)) for c in ln if ord(c) > 127])
```

#### ⚠️ 改完抽取逻辑 → 离线重建 + 内容完整性核对（零网络）

```bash
python3 scripts/regenerate_from_cache.py --check   # 先看会改哪些
python3 scripts/regenerate_from_cache.py             # 再写盘
python3 scripts/regenerate_from_cache.py --check   # 必须报 rewritten=0 unchanged=N
```

> ⚠️ **`rewritten=0` 只证明「抽取确定性」，不证明「没改坏内容」。**
> 改 `clean_text()` 这类会影响正文的函数时，必须额外做**内容完整性核对**：
> 用新旧两个 extractor 分别抽**未截断**的全文，比对 token 集合（旧 ⊆ 新，丢失数必须为 0）。
> ⚠️ **别用 `content_snippet` 比对** —— 它是截断后的窗口，
> 去掉一个 ZWSP 字符会让 800 字窗口**边界移动** → 长度变化是窗口效应，不是内容丢失。
> 2026-10-29 实测（open KB）：全量 799 页中 774 条完全一致、25 条仅空白差异、
> **分词级 token 丢失数 = 0** ✅

#### ⚠️ `diagnose_byte_change.py` 报 "MIXED" 可能是探针顺序假象（2026-10-29）

`regenerate_from_cache.py` 写盘时会**刷新** `references/.index-snapshot.json`，
于是该脚本拿到的「上次快照」已经是**修复后**的尺寸，
再拿修复前的 `OLD 重建` 去比 → 必然不等 → 报 `MIXED`。

**判读优先级：抓取次数 + `raw/` mtime > 脚本的 VERDICT 措辞。**
只要「crawl log 里 0 次抓取」且「`raw/` 最新 mtime 早于爬取开始」，
上游就不可能动过 —— 那就是纯本地变更。
2026-10-29 实测：`OLD 重建 = 2,453,407` = **恰好等于修复前的 index 尺寸** → 铁证。

#### ⚠️ 手写 slug 契约检查会崩在 `OSError [Errno 36]`（2026-10-29 现场）

自己拼候选文件名时，如果用 `quote(path, safe="")` 作为候选，
**超长中文路径会超过 Linux 255 字节文件名上限** → `Path.exists()` 抛
`OSError: [Errno 36] File name too long` → 检查脚本当场崩掉。

proxy 自己是用 try/except 兜住的（`read_full_content()` 里 `except OSError: continue`），
所以线上不会挂 —— 但**你的检查脚本会挂**。

✅ **最佳做法：直接复用 proxy 的候选生成函数**，别自己复刻：

```python
spec = importlib.util.spec_from_file_location("hsp", "/home/ecs-user/hermes-skill-proxy/hermes-skill-proxy.py")
mod = importlib.util.module_from_spec(spec); sys.modules["hsp"] = mod
spec.loader.exec_module(mod)

for k, v in idx.items():
    path = v.get("path") or k
    for slug in mod._md_slug_candidates(path):     # ← 复用 proxy 的实现
        cand = md_root / f"{slug}.md"
        try:
            if cand.exists():
                hit = cand; break
        except OSError:                              # ← Errno 36 必须兜住
            continue
```

2026-10-29 实测：复用 `_md_slug_candidates()` 后 **558/558 全部解析成功，
`OSError` 吞掉 0 次**（因为第一个候选就命中，根本走不到超长的 `quote()` 候选）。

> 💡 三个 slug 契约副本（proxy / `retrieve.py` / `check_crawl_state.py`）
> 必须保持一致 —— 这正是「复用而不是复刻」的价值。

### 4. 检索链路实测（snippet 长度判据）

用 `scripts/check_retrieval_chain.py`（open skill 自带）跑两个 KB：

- `content_snippet` **> 800** = 正文命中
- **== 800** = 静默降级成 index 摘要 → **BUG**
- **< 200** = 上游本来就是占位页（如伺服报错一行）→ 正常，用 md 实际字节数确认

#### ⚠️ `verify_kb.py` 的「短 snippet」note 要再判一层（2026-10-29 现场）

`verify_kb.py` 会输出：

```
note: 短 snippet  247  inexbot / 示教器 操作手册 / 操作手册  ← 疑似静默降级
```

**这个 note 并不等于「有 BUG」** —— 它只是「长度 < 800」的粗筛。
真正的判别要看 **md 文件的实际字节数**：

| `snippet_len` | md 实际字节数 | 结论 |
|---|---|---|
| `== 800` | — | **静默降级**（index 摘要兜底）→ BUG |
| `< 800` | `== snippet_len` | **正文已完整读取**，只是这一页本身就很短 → 正常 |
| `< 800` | `> snippet_len` | 部分读取 → 查 slug 契约 |

2026-10-29 实测：5 条「短 snippet」note 全部满足 `md_bytes == snippet_len`
（247 / 277 / 418 / 440 / 468 字节），即**磁盘正文被完整取出**，
这些是「示教器无法开机」「伺服错误」这类本身就两三行的 FAQ 页 → **无 BUG**。

核验脚本：

```python
for r in mod.search_single_kb("inexbot", q, 30):
    if len(r.get("content_snippet","")) < 800:
        for slug in mod._md_slug_candidates(r.get("path") or ""):
            c = md_root / f"{slug}.md"
            try:
                if c.exists(): hit = c; break
            except OSError: continue
        disk_len = len(hit.read_text(encoding="utf-8")) if hit else -1
        print(r["title"], len(r["content_snippet"]), disk_len)
```

### 5. 引用链接可达性（本次新增的盲区）

**`/health` 绿灯 + 检索命中 ≠ 用户点得到链接。**
必须实网 curl 注入的 URL，断言全部 HTTP 200。

```python
# 判据：url 里 %25 数量 == 0，且逐条 curl 返回 200
```

### 6. 回归 + 部署

改动 proxy 代码后：`sudo systemctl restart hermes-skill-proxy`，
**分两条独立命令**（restart 和 curl 不要链在同一条 `&&` 里，见姊妹 skill 的
「同一条命令里会假性失败」章节），再跑完整回归。

> ⚠️ 这是**系统级** unit，必须 `sudo -n`（本机免密可用）。
> 不带 sudo 会报 `Interactive authentication required`。
> `systemctl --user cat hermes-skill-proxy.service` **返回不了任何东西**
> —— 它不是 user unit，配置在 `/etc/systemd/system/hermes-skill-proxy.service`。
> ⚠️ 仓库里的 `hermes-skill-proxy.service` 副本是**旧的**
> （`User=inexbot`、`WorkingDirectory=/home/inexbot`，该目录根本不存在）——
> **以 `/etc/systemd/system/` 下的为准**。

#### ⚠️ systemd `Environment=` 块写错 → 4 个环境变量被静默忽略（2026-10-29 修复）

**两个 KB 共用同一个 proxy unit，所以这条对两边都成立。**

unit 里若写成：

```ini
Environment=
  PROXY_PORT=8643
  HERMES_URL=http://localhost:8642
  HERMES_API_KEY=hermes-website-search
  SKILL_NAME=inexbot-knowledge-base
```

**systemd 不支持 `Environment=` 后跟缩进续行** —— 它把 `PROXY_PORT=8643` 当成一个
未知名的 directive key，于是**这 4 个变量全部被丢弃**。
`Environment=` 后接续行是 shell `.env` 的写法，systemd 不认。

**症状**（`journalctl -u hermes-skill-proxy` 反复出现）：

```
hermes-skill-proxy.service:11: Unknown key name 'PROXY_PORT' in section 'Service', ignoring.
hermes-skill-proxy.service:12: Unknown key name 'HERMES_URL' in section 'Service', ignoring.
hermes-skill-proxy.service:13: Unknown key name 'HERMES_API_KEY' in section 'Service', ignoring.
hermes-skill-proxy.service:14: Unknown key name 'SKILL_NAME' in section 'Service', ignoring.
```

`systemctl show hermes-skill-proxy -p Environment` → 输出 `Environment=`（空）。

**正确写法（每行一个 `Environment=`）**：

```ini
Environment="PROXY_PORT=8643"
Environment="HERMES_URL=http://localhost:8642"
Environment="HERMES_API_KEY=hermes-website-search"
Environment="SKILL_NAME=inexbot-knowledge-base"
```

**复现 / 验证（不改线上文件）**：

```bash
systemd-analyze verify /tmp/probe-fixed.service 2>&1 | grep probe-fixed
```

旧写法 → 每行一条 `Unknown key name ... ignoring.`；新写法 → 对该 unit 零告警。

> ⚠️ **`systemd-analyze verify` 要求文件名以 `.service` 结尾**。
> 用 `.fixed` / `.txt` 会报 `Failed to prepare filename ...: Invalid argument`，
> 看起来像「修复无效」其实是文件名问题 —— 先 `cp` 成 `xxx.service` 再验。

> ⚠️ **改 `HERMES_API_KEY` 前先比对**：`/etc` 部署版里曾是被截断的占位符
> `hermes...arch`（len=13），与代码默认值 `hermes-website-search`（len=21）**不同**。
> 因为原块被忽略，线上一直用代码默认值；**修 unit 时要显式写代码默认值**，
> 否则 proxy 会改用一个错误的 key 去转发 gateway。
> 比对时用 sha 摘要，别把 key 明文打进日志。

> ⚠️ 这个 unit 在 **proxy repo 模板 + `/etc/systemd/system/` 部署版各有一份**，
> **两份都要改**，否则下次 `setup.sh` 重装会把旧写法写回去。

> ⚠️ `/etc/systemd/system/` 下的文件普通用户**不可写**（`PermissionError`）。
> 流程是：读原文件 → 在 `/tmp` 生成修正版 → `sudo -n cp` 覆盖 → `sudo -n systemctl daemon-reload`。
> 覆盖后用 `systemctl show ... -p Environment` 确认 4 个变量都在。

### 6b. 什么时候**必须**重启 proxy（不能只等 5h 自动重载）

| 情况 | 要重启？ |
|---|---|
| 只是正文改了，URL 路径没变 | 不必须 |
| **上游改了 URL 路径**（旧 md 被删） | **必须** —— 旧内存索引指向已删文件 → 404 引用链接 |
| 改了 proxy 代码 | **必须** |
| 改了 `slugify()` / 清洗逻辑 | **必须** —— md 文件名变了 |

判据：`index.json` 的 mtime **晚于** proxy 启动时间 → 内存索引已过期。

```bash
ls -la ~/.hermes/kb/inexbot/index.json
ps -o pid,lstart -p $(pgrep -f hermes-skill-proxy.py | head -1)
```

细节见 `references/proxy-runtime-freshness.md`。

## ⚠️ 两个 KB 的 cron 会并发改同一个 proxy 文件

**这是真实的互相覆盖风险，不是理论问题。**

2026-10-25 现场：改 `hermes-skill-proxy.py` 时，姊妹 KB 的 cron 正在
`git fetch` / `git pull` 同一个 repo。`skill_manage` / `patch` 返回了：

```
_warning: hermes-skill-proxy.py was modified by sibling subagent
          'f2fb7174-...' but this agent never read it
```

**对策**：
1. 动手前 `ps aux | grep -E 'git (pull|push|fetch|merge)|crawler.py'` 看有没有并发作业
2. **patch 之后、commit 之前**必须 `git diff` 复核，确认对方的改动还在
   （本次正是靠 `git diff --stat` 发现 sibling 的 `_md_slug_candidates()` 修复没被覆盖）
3. commit 前再 grep 一次关键函数名，两个 KB 的修复都要在
4. 姊妹 KB 的 SKILL.md 里有同样的警告，**两边都要遵守**

## ⚠️ 工作树里可能有长期未提交的重要改动

2026-10-25 发现：`crawler.py` 的 VitePress v2 alpha 迁移（sitemap 发现 +
`slugify()` unquote + MD5 截断 + `html.unescape()`）**一直在工作树里没进版本库**。
任何人 `git pull` 到旧版都会退回 `config.js` 发现逻辑——那条路在 v2 alpha 上
**已经失效**（sidebar 整个被拆到外部 JS chunk）。

**cron 收尾时应该顺手检查**：

```bash
cd <skill repo> && git status -sb
```

看到 `M scripts/crawler.py` 或一批 `?? references/` / `?? scripts/*.py`，
说明有重要改动没进版本库 → **提交并推送**，否则下次 pull 会静默回退。

#### ⚠️ 上一轮报告说「已完成」但工作树其实没提交（2026-10-29 现场）

**上一轮的 `Last run` 报告里写着「已提交并推送 `c7bbf5e`」，**
但本轮 `git status` 仍显示 3 个文件 `M`（`SKILL.md` /
`references/kb-cron-verification-workflow.md` / `references/proxy-runtime-freshness.md`，
共 217 行新增）—— 也就是说**上一轮提交的是另一个 commit，
本轮这些改动根本没进版本库**。

规律：**报告里的 commit hash 只证明「那个 commit 在库里」，
不证明「工作树此刻是干净的」。** 第 ② 项检查（`git status -sb`）
必须**每轮都独立跑**，不能因为上一轮报告说了「已提交」就跳过。

本次已补做：`a87aa82` → push 首次即成功。

#### ⚠️ 无人值守 cron 下的删除操作会被卡住（2026-10-29 现场）

清理 `/tmp` 下的压测残留时：

```
rm -f /tmp/proxy_chain_test.py /tmp/proxy_reload_test.py ...
→ ⚠️ delete in root path. Asking the user for approval.
```

`/tmp` 属于「root path」，删除需要**用户审批**。cron 场景**没有人能批**
→ 这次清理做不成。

✅ 正确做法：
- **优先清进程**（`kill <PID>`）而不是清文件 —— 进程才是占端口/吃资源的实体，
  残留的 `.py`/`.log` 文件不占端口、不影响服务
- 确需删文件时，**在报告里写明残留清单 + 理由**（如「均为无进程占用的死文件，
  不影响服务，清理需审批故保留」），把决定权交回给用户

> 💡 压测残留**最该盯的是进程和端口**，不是文件。
> 2026-10-29 检查：`ss -ltnp | grep -E "864[0-9]"` 只有 8643 + 8642 →
> 端口干净 → `/tmp` 里的 `.py` 残留**不影响交付**，可以放着。

## 报告该怎么写

用户要的是「知识库更新了没有 + 有什么值得注意的」，不是爬虫日志转录。

好的报告包含：
1. **爬取结果表**（页数/耗时/index 大小/漂移 verdict）
2. **发现并修复的问题**（如果有）——这是最有价值的部分
3. **部署状态**（proxy 是否已重启、健康检查结果）
4. **提醒**（比如「工作树里有未提交的改动，已一并提交」）

坏的报告：把 60 行「跳过（已存在）」日志贴出来。

### ⚠️ 报告里的「已修复」必须附证据（2026-10-28 新增）

**只写「已修复」会被下一个 session 当成「已收尾」而跳过** —— 补丁就永远悬在半路。

写「已修复」时必须同时给出：

| 声称 | 必须附的证据 |
|---|---|
| proxy 补丁已部署 | 新 PID + `ActiveEnterTimestamp`（晚于补丁 mtime）+ 补丁特征 `grep` 结果 |
| 定时器链健在 | `ls /proc/<PID>/task \| wc -l` = **2**（main + timer；=1 说明链断了） |
| 代码已入库 | commit hash + push 成功输出 |
| 链接可用 | 抽样 URL 的 HTTP 状态码数量（如 `20/20 全部 200`） |

2026-10-28 的报告因为给出了「新 PID 1761173 / 启动于 11:08:34 / commit 1b8c523 /
threads=2 / 20 条 URL 全 200」，所以下一轮 cron 能一眼看出状态，不会重复劳动或误判。

## ⚠️ cron 收尾清单（别只跑爬虫就结束）

```bash
# ① 上一轮待办是否已清空（见 §0）
hermes cron list 2>&1 | grep -A 60 "Last run"

# ② 两个 repo 是否有未提交改动
for r in /home/ecs-user/hermes-skill-proxy \
         ~/.hermes/skills/productivity/inexbot-knowledge-base \
         ~/.hermes/skills/productivity/inexbot-open-knowledge-base; do
  echo "--- $r"; git -C $r status -sb | head -5
done

# ③ 遗留压测进程 / 端口占用（应只有 8643 proxy + 8642 gateway）
ss -ltnp | grep -E "864[0-9]"
ps aux | grep -E "proxy_reload|proxy-unbuf" | grep -v grep

# ④ 线上 proxy 是否带最新补丁（补丁 mtime 晚于进程启动 = 没带）
stat -c '%y %n' /home/ecs-user/hermes-skill-proxy/hermes-skill-proxy.py
ps -o pid,lstart,etime -p $(pgrep -f hermes-skill-proxy.py | head -1)
```

> ⚠️ 第 ② 项若看到**姊妹 KB** 的 repo 有未提交改动 —— **不要替它提交**。
> 姊妹 KB 的 cron 正在跑（同一时刻 11:00），它的改动归它自己收尾。
> 只在报告里**指出**即可：「姊妹 KB 工作树有未提交改动，属于其 cron 职责」。
> 2026-10-28 就是这么处理的 —— 姊妹 KB 的 `crawler.py` 工作树版本已含原子写，
> 但未入库；**若它自己的 cron 不提交，下次 `git pull` 会退回非原子写版本**，
> 那正是 proxy 重载链断裂的潜在触发点，值得在报告里点名。

## ⚠️ 结论要区分「已证实的故障」和「我怀疑的故障」

2026-10-27 现场：看到 journal 里 48 小时没有 proxy 重载记录，
一度断定「定时重载链断了，线上 48 小时用的是过期索引」。
深挖后**推翻了** —— systemd 下 stdout 块缓冲，小段输出几十小时不刷进 journal；
加 `PYTHONUNBUFFERED=1` 实测 10s 间隔重载**完全正常**。

**教训**：
- 中途的推测**不要**直接写进报告当结论 —— 先做完证伪实验再落笔
- 补丁本身可以照样打（加固无坏处），但**定性**要改口：
  「已发生 48 小时不重载」→ 「重载链遇异常会断裂，已加固」
- 报告里如果写了未经证实的因果，要明确标注是**推测**还是**实测**

判定某个行为「坏了」之前，先确认**观测手段本身**是否可信
（本次的观测手段 = journal，而 journal 因为缓冲不可信）。
这跟「增量爬虫报成功不代表上游没变」是同一类错误的两个方向：
一个是被假绿灯骗了，一个是**被假红灯骗了**。

## 无变化时也要说点什么

如果确实零变化（IDENTICAL + 全部检查通过），**不要静默**——
cron 的交付物是「已确认无变化，且无隐藏故障」。报告应该短：

> 558/558 成功，漂移探针 IDENTICAL，检索链路与链接可达性 17 项检查全 PASS，无变化。

这比沉默更有价值：它证明**今天没人偷偷把链路搞坏**。
