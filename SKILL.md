---
name: inexbot-knowledge-base
description: "纳博特科技知识库 RAG：每天定时爬取 doc.inexbot.com，用户问到纳博特/机器人相关问题时从本地知识库检索答案。包含爬虫脚本、定时任务和检索流程。"
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [knowledge-base, rag, inexbot, robot, crawler]
    category: productivity
    related_skills: []
---

# 纳博特科技知识库（RAG）

当用户问到与纳博特科技、工业机器人、运动控制相关的问题时，使用本技能从本地知识库检索答案，而非凭记忆回答。

## 知识库信息

| 项目 | 值 |
|------|-----|
| 源站 | https://doc.inexbot.com |
| 内容 | 纳博特控制器/示教器/工艺/通讯等技术文档 |
| 页面总数 | ~126 篇 |
| 分类 | 产品资料（18）、技术资料（5）、操作手册（103）、行业方案（2） |
| 存储路径 | `~/.hermes/kb/inexbot/` |
| 索引文件 | `~/.hermes/kb/inexbot/index.json` |
| Markdown | `~/.hermes/kb/inexbot/md/` |
| BASE_URL | `https://doc.inexbot.com` |
| 爬虫脚本 | `~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/crawler.py` |

## 技能激活条件

当用户问到以下类型的问题时激活本技能：
- 纳博特控制器的功能、操作、配置
- 机器人（焊接、码垛、切割、喷涂等）工艺参数
- 工具手标定、用户坐标标定方法
- 通讯协议（Modbus/TCP/OPC-UA/Ethernet/IP）
- 运动指令、变量体系、条件控制指令
- 传感器、视觉、传送带跟踪
- 常见故障、报错代码
- 产品型号（T30/T31/C1102/C1200/C1201 等）规格

## 工作流程

### 第 1 步：理解用户问题

解析用户问题，提取核心关键词（2-5 个），例如：
- "焊接工艺的起弧渐变怎么设置" → 提取「焊接工艺」「起弧渐变」
- "工具手标定有几种方法" → 提取「工具手标定」「方法」

### 第 2 步：本地检索（优先使用 retrieve.py）

使用官方检索脚本（推荐方式，调用 jieba 分词 + 多字段加权检索）：

```bash
python3 ~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/retrieve.py "<用户问题>" [top_k]
```

**输出格式**：stdout 输出最相关的 1 条检索结果（标题 + 链接 + 正文摘要，最多 1000 字），无结果时退出码 1。

**调用示例**：
```bash
python3 ~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/retrieve.py "工具手标定有几种方法" 3
```

**退出码**：0 = 有结果，1 = 无结果或出错。

> ⚠️ **不要在 Hermes Agent 对话中直接说"我来查知识库"然后调用 search_files**。如果需要让 LLM 使用检索结果回答（而不是 LLM 自己再调用工具搜索），应将检索结果通过 system prompt 注入，并明确告知 LLM 不要调用搜索工具。

### 第 3 步：注入 RAG 上下文（让 LLM 直接使用，而非再次搜索）

将检索结果注入 system prompt 时，**必须明确禁止 LLM 调用搜索工具**，否则 LLM 会忽略注入的上下文而自行调用 `search_files` / `read_file`，导致工具调用循环和回答偏离注入内容。

注入格式示例：
```
以下是从官方知识库检索到的相关内容，请直接基于这些内容回答用户问题（不要重复调用搜索工具）：

标题：xxx
链接：https://doc.inexbot.com/xxx
简介：xxx

<检索到的正文内容>

---
回答要求：
1. 直接用上面的知识库内容回答，不要调用任何搜索或读取文件的工具
2. 如果知识库内容不足，则基于你自己的知识补充说明
3. 适当使用 Markdown 格式来组织回答
```

**判断标准**：检索结果丰富且直接相关时 → 用上述强约束格式；检索结果贫乏或无关时 → 降级为普通问答，不注入上下文。

### 第 4 步：综合回答（Humanizer 风格）

从检索到的内容中提取答案，用自己的语言重新组织表达，不要生硬地堆砌原文。保持自然、流畅、有条理的口吻，符合纳博特技术文档的专业性。

格式：
```
{用自己的话整理的答案}

📄 原文：{标题} | {BASE_URL}{path}
```

示例（对比）：

❌ 生硬原文堆砌：
> 根据纳博特知识库「工具手标定手册」：
> 工具手标定有6点法、7点法、12点法、15点法、20点法四种方法...

✅ 自然语言重组：
> 工具手标定支持多种精度方案：
> - **6点法**：适合6轴标准机器人，精度最好
> - **7点法**：适合A/B轴机器人，轴向精度更优
> - **12/15/20点法**：用于校准零点，适用于特殊机型
>
> 标定时会用到TOOL_NUM指令选择对应方法，具体操作在示教器「工具手标定」界面完成。

📄 原文：工具手标定手册 | https://doc.inexbot.com/操作手册/24.03版本/工具手标定手册

## 爬虫说明

### 手动触发爬取

```bash
python3 ~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/crawler.py
```

### 强制重爬（忽略本地缓存）

```bash
python3 ~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/crawler.py --force
```

### 爬取策略

VitePress 站点采用特殊爬取策略（无需抓 sitemap）：
1. 访问 `/.vitepress/config.js`，在 404 页面 HTML 中解析内嵌的 `__VP_HASH_MAP__` 和 `__VP_SITE_DATA__`，获取完整站点结构和所有页面链接
2. 直接访问每页的静态 HTML 端点
3. 用 BeautifulSoup 提取 `<article>` 主体，转换为 Markdown
4. 用 jieba 中文分词构建倒排索引

### 爬取输出

```
~/.hermes/kb/inexbot/
├── raw/           # 原始 HTML（126 个 .html 文件）
├── md/            # 提取的 Markdown（126 个 .md 文件）
├── index.json     # 全量搜索索引（含标题/描述/摘要/关键词）
└── meta.yaml      # 爬取元数据（时间、版本、失败记录）
```

## 定时任务

每天上午 11:00 自动爬取，详见 cronjob 配置：

```bash
# 查看定时任务
cronjob action=list

# 手动运行一次（测试用）
cronjob action=run job_id=<你的job_id>
```

定时任务使用 `notify_on_complete`，爬取完成后发送通知。

## 注意事项

- 知识库为增量爬取，已存在的页面不会重复下载（除非加 `--force`）
- 爬取间隔约 0.3~0.8 秒/页，126 页约需 1 分钟
- 搜索用 jieba 中文分词，关键词最短长度 2 字符
- 如检索结果不相关，扩大 top_k 或更换关键词重试
- 知识库版本标记为爬取日期（YYYYMMDD 格式，存于 `meta.yaml`）

## 常见陷阱

### 1. LLM 忽略 RAG 上下文，自行调用搜索工具

**现象**：检索到的内容已经注入 system prompt，但 LLM 仍然调用 `search_files` / `read_file` 自行搜索，导致工具调用循环、回答偏离注入内容、响应极慢。

**根因**：Hermes 的 system prompt 没有明确禁止调用工具；LLM 倾向于使用可用工具而非信任给定的上下文。

**解法**：在 system prompt 中明确指令"不要调用任何搜索或读取文件的工具"，示例见第 3 步。

### 2. 多文档输出格式导致 LLM 无法直接使用

**现象**：检索结果以 Markdown 多文档格式（`### 标题` + `---` 分隔）输出时，LLM 将其视为参考资料而非直接答案，仍倾向自行搜索。

**解法**：只取最相关的 1 条结果，格式改为"标题 / 链接 / 正文"纯文本三段式，正文在前，降低 LLM 的"参考资料"心智模型。

### 3. retrieve.py 调用失败阻塞主流程

**现象**：Python 脚本超时或出错时，如果用 `await` 同步等待，会阻断 HTTP 请求处理。

**解法**：`retrieve.py` 设计为失败时不阻塞——超时或无结果时退出码 1，调用方捕获后继续不带 RAG 上下文的普通问答。
