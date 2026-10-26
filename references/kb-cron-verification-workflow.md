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

### 3. 索引完整性对账（廉价、高价值）

一次 `execute_code` 跑完这几条断言（任一失败都说明有隐藏故障）：

```python
# 零长度 snippet = 抓到 404 空壳页的信号
# description == "Not Found" = 同上
# 空标题 = 丢掉标题 ×4 权重
# key 里含裸 % = 双重编码 / 链接必 404
# index key → md 文件是否可解析（slug 契约）
```

### 4. 检索链路实测（snippet 长度判据）

用 `scripts/check_retrieval_chain.py`（open skill 自带）跑两个 KB：

- `content_snippet` **> 800** = 正文命中
- **== 800** = 静默降级成 index 摘要 → **BUG**
- **< 200** = 上游本来就是占位页（如伺服报错一行）→ 正常，用 md 实际字节数确认

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

## 报告该怎么写

用户要的是「知识库更新了没有 + 有什么值得注意的」，不是爬虫日志转录。

好的报告包含：
1. **爬取结果表**（页数/耗时/index 大小/漂移 verdict）
2. **发现并修复的问题**（如果有）——这是最有价值的部分
3. **部署状态**（proxy 是否已重启、健康检查结果）
4. **提醒**（比如「工作树里有未提交的改动，已一并提交」）

坏的报告：把 60 行「跳过（已存在）」日志贴出来。

## 无变化时也要说点什么

如果确实零变化（IDENTICAL + 全部检查通过），**不要静默**——
cron 的交付物是「已确认无变化，且无隐藏故障」。报告应该短：

> 558/558 成功，漂移探针 IDENTICAL，检索链路与链接可达性 17 项检查全 PASS，无变化。

这比沉默更有价值：它证明**今天没人偷偷把链路搞坏**。
