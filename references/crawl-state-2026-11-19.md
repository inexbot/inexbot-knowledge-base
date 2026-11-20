# 2026-11-19 爬取快照 —— ⭐ 上游改「URL 形态」（`.html` 后缀路由）

> ⚠️ **本轮的核心事件不是页面数变化，而是上游改了 URL 路由形态。**
> 完整诊断与修复流程见 `references/upstream-url-suffix-routing.md`。

---

## 一、核心发现

**上游 `doc.inexbot.com` 从「裸路径路由」改成「`.html` 后缀路由」**：

| 页面类型 | 旧（≤11-18） | 新（11-19 起） |
|---|---|---|
| 普通页 | `/zh/xxx` → 200 | `/zh/xxx` → **404**；`/zh/xxx.html` → 200 |
| 目录页 | `/zh/xxx/` → 200 | `/zh/xxx/` → **404**；`/zh/xxx/index.html` → 200 |

⇒ **引用链接 60/60 全 404**（前一天 60/60 全 200），
而 crawler 报 561/561 成功、`/health` 绿灯、检索链路 PASS、索引完整性全 PASS。
**这类故障的特征就是「表层全绿但用户拿到坏链接」。**

**姊妹 KB `open.inexbot.com` 未受影响**（抽样 15/15 裸路径仍 200）
⇒ 修复**按 KB 分派**，未做全局改动。

---

## 二、本轮数据

| 项 | 值 |
|---|---|
| 页面总数 | 560 → **561**（上游新增 1 页） |
| 新页 | `激光切割操作手册`（`/zh/操作手册/dev-daji/激光切割操作手册`，64,851 bytes） |
| sitemap | 1108 loc / **561 zh** == 本地 561 ✅ |
| index.json | 1,735,196 → **1,756,935 bytes**（新增 `url_suffix` 字段 + 新页） |
| md / raw | 561 / 561，缺失 0、孤儿 0 |
| `url_suffix` 分布 | `.html` **546** / `/index.html` **15** |
| 空标题 / ZWSP | 0 / 0 |
| 引用链接（修复后） | **74/74 全 200**（60 抽样 + 强制并入 14 条目录页） |
| 检索链路 | 无真静默降级，md 全部可定位 |
| 端到端 | **12/12 全 200**（0 次 500/502），姊妹 KB 同时段亦全 200 |

---

## 三、已实施的修复

| 组件 | 改动 |
|---|---|
| `crawler.py` | `fetch_vitepress_metadata()` 返回 `suffix_map`（从 sitemap 原始形态取判据）；`build_search_index()` 写入 `url_suffix`（默认 `.html`）；`crawl()` 三个分支都设 `page["url_suffix"]` |
| proxy `hermes-skill-proxy.py` | `_kb_url(base_url, path, suffix)` 支持后缀；`search_single_kb()` 传 `item.get("url_suffix", "")`；`KB_CONFIGS` 加 `url_suffix_mode`（inexbot=`html` / open=`none`） |
| `rebuild_from_cache.py` | 重建时重新取一次 sitemap 拿 `suffix_map`；**并修掉 `ZWSP = ""` 假阳性**（字面零宽被吞 ⇒ 报「561 条含 ZWSP」，实测真实为 0） |
| `check_citation_links.py` | 链接带 `url_suffix`；**强制并入全部目录页** |
| `check_crawl_state.py` | 抽样 URL 加后缀（否则 100% HTTP404） |
| `check_retrieval_chain.py` | url→key 归一化先剥后缀 |
| `check_url_to_index_key.py` | 同上 + 目录页试「带/不带尾斜杠」两种 key |
| `scan_kb_topic.py` | 新增 `official_url()`，不再裸拼 `base_url + key` |
| `retrieve.py` | `format_result()` 按 `url_suffix` 拼链接 |

---

## 四、⚠️ 本轮未完成项（下轮必须先做）

> **本轮因工具调用次数上限被中断 —— 修复处于「已写盘、未部署、未提交」状态。**

| # | 待办 | 优先级 |
|---|---|---|
| 1 | 验证 `check_url_to_index_key.py` 应达 **93/93**（此前 92/93，漏的是根目录页 `/zh/` vs `/zh`） | 高 |
| 2 | 跑 `verify_kb.py` 全量回归 | 高 |
| 3 | **确认姊妹 e2e 探针已结束** → `sudo -n systemctl restart hermes-skill-proxy.service` → 带重试健康检查 → 核对 `/proc/<pid>/environ` | 🔴 **最高**（不重启 ⇒ 用户仍拿 404 链接） |
| 4 | 重跑 `check_citation_links.py` + 一次真实 e2e，确认线上返回带 `.html` 的链接 | 高 |
| 5 | **commit + push 两个仓库**（commit message 纯 ASCII），用 §0.9 的 `merge-base --is-ancestor` 直查远端确认 | 🔴 高 |
| 6 | 把 `references/upstream-url-suffix-routing.md` 同步到姊妹 KB 的 shared pitfalls | 中 |

> ⚠️ **本轮 report 写了「已修复」但实际未部署未提交** —— 与 §0.6/§0.7 描述的
> 跨 session 泄漏形态完全一致。**下轮读到本文件时，第 3、5 项是硬前置。**

---

## 五、教训

1. **「表层全绿」不能证明用户拿到好结果** —— 引用链接实网检查是唯一能抓到
   「上游改 URL 形态」的检查。其它检查（索引完整性 / 检索链路 / `/health`）
   对这类故障**完全无感**。

2. **上游 vs 探针自错的分诊**（三问）：
   1. 是我自己写错了归一化吗？（陷阱 24/25 —— 最常见）
   2. 是我自己漏了调用约定吗？（陷阱 34）
   3. 是上游改了吗？（本轮 —— 用**三形态探测**验证）

   **三形态探测只要 3 次 GET，改任何代码前先做。**

3. **改 URL 规则时务必先确认姊妹 KB** —— 本轮姊妹未受影响，
   若做成全局规则 ⇒ 姊妹侧全量 404（陷阱 25 的上游侧版本）。

4. **「改了磁盘上的文件」≠「用户拿到的是好结果」** ——
   proxy 未重启 = 补丁没上线。
