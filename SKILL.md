---
name: inexbot-knowledge-base
description: "纳博特科技知识库 RAG：每天定时爬取 doc.inexbot.com，由 hermes-skill-proxy 在请求时进行内存检索并注入 system prompt。"
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [knowledge-base, rag, inexbot, robot, crawler]
    category: productivity
    related_skills: []
---

# 纳博特科技知识库（RAG）

## 架构

```
用户问题 → hermes-skill-proxy (8643)
              ↓ 内存检索 index.json（毫秒级）
              ↓ 注入检索结果到 system prompt
              → Hermes Gateway (8642)
                → MiniMax LLM
                  → 流式回答
```

**检索由 proxy 层自动完成，LLM 直接使用注入的检索结果回答，无需自行调用工具。**

## 知识库信息

| 项目 | 值 |
|------|-----|
| 源站 | https://doc.inexbot.com |
| 内容 | 纳博特控制器/示教器/工艺/通讯等技术文档 |
| 页面总数 | ~126 篇 |
| 存储路径 | `~/.hermes/kb/inexbot/` |
| 索引文件 | `~/.hermes/kb/inexbot/index.json` |
| Markdown | `~/.hermes/kb/inexbot/md/` |
| BASE_URL | `https://doc.inexbot.com` |

## Proxy 检索逻辑

hermes-skill-proxy 启动时将 `index.json` 加载到内存，之后每 5 小时自动重载一次。

每次收到用户问题时：
1. 从 messages 中提取最后一条 user 消息
2. 用 jieba 分词后，在内存索引中做加权关键词匹配：
   - 标题命中 ×4
   - 描述命中 ×2
   - 正文词频 ×0.5
3. 取 top-5 结果，格式化为 Markdown 注入 system prompt
4. 附带回答要求：基于检索内容回答、列出引用链接

无检索结果时使用通用 system prompt（不注入知识库内容）。

## 回答格式要求（注入到 system prompt）

```
【知识库检索结果】
以下是从纳博特文档库中检索到的 N 篇相关内容：

--- 文档 1 ---
标题：xxx
链接：https://doc.inexbot.com/xxx
简介：xxx
正文摘要：xxx

【回答要求】
1. 直接基于上面检索到的知识库内容回答，不要凭记忆猜测
2. 如果检索内容足以回答问题，给出完整答案；覆盖不足时说明并给出部分答案
3. 答案末尾必须列出所有引用过的文档链接，格式为：📄 原文：标题 | 链接
4. 使用简洁专业的技术语言，适当使用 Markdown 格式
```

## 爬虫说明

### 定时爬取（cronjob）

每天上午 11:00，Hermes 通过 cronjob 自动运行 `crawler.py`，更新 `index.json` 和 `md/` 目录。
Proxy 下一次 5 小时重载时会自动加载最新索引。

### 手动爬取

```bash
python3 ~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/crawler.py
python3 ~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/crawler.py --force  # 强制重爬
```

## 问题日志

每次收到用户问题时自动记录到 `~/.hermes/kb/inexbot/questions.log`。

```bash
tail -20 ~/.hermes/kb/inexbot/questions.log
```
