#!/usr/bin/env python3
"""
纳博特科技知识库爬虫
============================
VitePress 站点，https://doc.inexbot.com

爬取策略（按优先级）：
1. 从 .vitepress/config.js（404页面内嵌）解析：
   - __VP_HASH_MAP__ → 文件名到 hash 的映射
   - __VP_SITE_DATA__ → 完整侧边栏导航树（含所有页面链接）
2. 直接访问每页的 .html 端点（VitePress 预渲染为静态 HTML）
3. 用 BeautifulSoup 提取 <article> 主体内容，转为 Markdown
4. 存储到本地，用 jieba 分词建倒排索引

存储结构：
  KB_ROOT/
  ├── raw/           # 原始 HTML
  ├── md/            # 提取的 Markdown
  ├── index.json     # 全量搜索索引（标题/路径/摘要/关键词）
  └── meta.yaml      # 爬取元数据（时间、版本、页面数）
"""

import os
import re
import json
import time
import hashlib
import datetime
import subprocess
from pathlib import Path
from urllib.parse import urljoin

import httpx
import jieba
import yaml
from bs4 import BeautifulSoup

# ── 配置 ────────────────────────────────────────────────────────────────────

BASE_URL = "https://doc.inexbot.com"
KB_ROOT = Path.home() / ".hermes" / "kb" / "inexbot"
RAW_DIR  = KB_ROOT / "raw"
MD_DIR   = KB_ROOT / "md"
INDEX_F  = KB_ROOT / "index.json"
META_F   = KB_ROOT / "meta.yaml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; HermesBot/1.0; "
        "+https://github.com/nousresearch/hermes-agent)"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

TIMEOUT = 30          # 单页超时（秒）
CONCURRENCY = 8       # 并发请求数
PAUSE_MIN  = 0.3     # 两次请求间最小停顿（秒），防封
PAUSE_MAX  = 0.8

# ── 工具函数 ─────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def slugify(text: str) -> str:
    """把任意文本转成安全文件名（保留中文）"""
    text = text.strip().replace("/", "-").replace("\\", "-")
    return re.sub(r'[<>:"|?*]', '', text)

def md5_text(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:8]

def save_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save_yaml(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, allow_unicode=True, default_flow_style=False)

# ── 第1步：从 VitePress 配置文件提取站点元数据 ──────────────────────────────

def fetch_vitepress_metadata() -> dict:
    """
    VitePress 的 .vitepress/config.js 会返回 404 页面，
    但该 404 页面的 <script id="check-dark-mode"> 之后内嵌了：
      - __VP_HASH_MAP__  →  文件名→hash 映射
      - __VP_SITE_DATA__ →  完整侧边栏配置（含所有页面链接）
    """
    log("正在获取 VitePress 站点配置...")
    resp = httpx.get(urljoin(BASE_URL, "/.vitepress/config.js"),
                     headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    html = resp.text

    # 提取 __VP_HASH_MAP__
    hm_match = re.search(
        r'window\.__VP_HASH_MAP__\s*=\s*JSON\.parse\("((?:[^"\\]|\\.)*)"',
        html, re.DOTALL
    )
    hash_map = {}
    if hm_match:
        raw = hm_match.group(1)
        # 解 JSON 转义
        raw = raw.replace('\\"', '"').replace('\\\\', '\\')
        hash_map = json.loads(raw)

    # 提取 __VP_SITE_DATA__
    sd_match = re.search(
        r'window\.__VP_SITE_DATA__\s*=\s*deserializeFunctions\(JSON\.parse\("((?:[^"\\]|\\.)*)"',
        html, re.DOTALL
    )
    sidebar_links = []
    if sd_match:
        raw = sd_match.group(1)
        raw = raw.replace('\\"', '"').replace('\\\\', '\\')
        site_data = json.loads(raw)
        # 递归收集所有 sidebar 中的 link
        def collect_links(items):
            for item in items:
                if isinstance(item, dict):
                    if item.get("link"):
                        sidebar_links.append(item["link"])
                    if "items" in item:
                        collect_links(item["items"])
        theme_cfg = site_data.get("themeConfig", {})
        for section in theme_cfg.get("sidebar", []):
            collect_links(section.get("items", []))
            # 展开嵌套 items（如 22.07版本 / 24.03版本 的子项）
            for sub in section.get("items", []):
                if "items" in sub:
                    collect_links(sub["items"])
                # 产品资料下还有二级嵌套
                for sub2 in sub.get("items", []):
                    if "items" in sub2:
                        collect_links(sub2["items"])

    # 去重，保持顺序
    seen, unique = set(), []
    for link in sidebar_links:
        if link not in seen:
            seen.add(link)
            unique.append(link)

    log(f"  发现 {len(unique)} 个页面，{len(hash_map)} 个文件 hash")
    return {"links": unique, "hash_map": hash_map, "html": html}


# ── 第2步：提取页面正文 ───────────────────────────────────────────────────────

def extract_content(html: str, url: str) -> dict:
    """
    从 VitePress 预渲染的 HTML 页面中提取：
    - title（<h1>）
    - content（<article class="page"> 或 #content-container）
    - 描述（description meta）
    """
    soup = BeautifulSoup(html, "html.parser")

    # 标题
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    # 描述
    desc_tag = soup.find("meta", attrs={"name": "description"})
    description = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""

    # 正文区域
    article = soup.find("article", class_="page")
    if not article:
        article = soup.find("div", id="content-container")
    if not article:
        article = soup.find("main") or soup.find("div", class_="content")

    content_md = ""
    keywords_set = set()

    if article:
        # 深度清理：移除导航、侧边栏、脚本、样式等干扰元素
        for tag in article.find_all(["nav", "script", "style", "footer",
                                      "aside", "button", "input"]):
            tag.decompose()

        # 处理剩余元素，转为简化 Markdown
        content_md, keywords_set = _element_to_md(article)

    return {
        "title": title,
        "description": description,
        "content_md": content_md.strip(),
        "url": url,
        "keywords": sorted(keywords_set),
    }


def _element_to_md(element, depth=0) -> tuple:
    """递归将 BeautifulSoup 元素转为简化 Markdown，收集关键词。"""
    lines = []
    keywords = set()

    for child in element.children:
        if isinstance(child, str):
            text = child.strip()
            if text:
                lines.append(text)
                keywords.update(jieba.cut(text))
            continue

        tag = child.name or ""
        cls = child.get("class", [])
        tag_cls = f"{tag}.{'.'.join(cls)}" if cls else tag

        # 跳过干扰标签
        if tag in ("script", "style", "svg", "path", "noscript"):
            continue

        # 标题
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            text = child.get_text(strip=True)
            if text:
                lines.append(f"{'#' * level} {text}")
                keywords.update(jieba.cut(text))

        # 表格
        elif tag == "table":
            rows = child.find_all("tr")
            if rows:
                # 表头
                header_cells = rows[0].find_all(["th", "td"])
                header = "| " + " | ".join(
                    c.get_text(strip=True) for c in header_cells) + " |"
                sep    = "| " + " | ".join("-" * 4 for _ in header_cells) + " |"
                lines.append(header)
                lines.append(sep)
                # 数据行
                for row in rows[1:]:
                    cells = row.find_all(["td", "th"])
                    lines.append("| " + " | ".join(
                        c.get_text(strip=True) for c in cells) + " |")
                lines.append("")

        # 代码块
        elif tag == "pre":
            code = child.find("code")
            code_text = code.get_text() if code else child.get_text()
            lang = code.get("class", [""])[0].replace("language-", "") if code else ""
            lines.append(f"```{lang}")
            lines.append(code_text.rstrip())
            lines.append("```")
            lines.append("")

        # 列表
        elif tag in ("ul", "ol"):
            for i, li in enumerate(child.find_all("li", recursive=False), 1):
                prefix = "- " if tag == "ul" else f"{i}. "
                text = li.get_text(strip=True)
                lines.append(prefix + text)
            lines.append("")

        # 分隔线
        elif tag == "hr":
            lines.append("---")
            lines.append("")

        # 引用
        elif tag == "blockquote":
            text = child.get_text(strip=True)
            for ln in text.splitlines():
                lines.append(f"> {ln}")
            lines.append("")

        # 链接和强调
        elif tag in ("p", "div"):
            inner_md, inner_kw = _element_to_md(child, depth + 1)
            if inner_md.strip():
                lines.append(inner_md)
                keywords.update(inner_kw)
            elif tag == "p":
                text = child.get_text(strip=True)
                if text:
                    lines.append(text)
                    keywords.update(jieba.cut(text))

        # 图片
        elif tag == "img":
            src = child.get("src", "")
            alt = child.get("alt", "")
            if src:
                lines.append(f"![{alt}]({src})")

        # 其他：递归处理
        else:
            inner_md, inner_kw = _element_to_md(child, depth + 1)
            if inner_md.strip():
                lines.append(inner_md)
            keywords.update(inner_kw)

    return "\n".join(lines), keywords


# ── 第3步：构建搜索索引 ───────────────────────────────────────────────────────

def build_search_index(pages: list) -> dict:
    """
    为所有页面构建轻量级搜索索引。
    每个条目包含：title, path, description, keywords, content_snippet
    """
    log("正在构建搜索索引...")
    index = {}
    for page in pages:
        path = page["path"]
        title = page.get("title", "")
        desc  = page.get("description", "")
        content = page.get("content_md", "")[:500]  # 截取前500字作摘要

        # 用 jieba 对标题+描述+内容分词，收集关键词
        full_text = f"{title} {desc} {content}"
        words = [w for w in jieba.cut(full_text) if len(w) >= 2]
        word_counts = {}
        for w in words:
            word_counts[w] = word_counts.get(w, 0) + 1

        index[path] = {
            "title": title,
            "description": desc,
            "path": path,
            "content_snippet": content[:300],
            "keywords": list(word_counts.keys())[:50],  # 保留 top50 关键词
            "word_counts": word_counts,
        }

    log(f"  索引构建完成，共 {len(index)} 条记录")
    return index


def search_index(index: dict, query: str, top_k: int = 5) -> list:
    """
    在索引中检索相关页面。
    策略：查询词在标题中权重×4，描述中权重×2，正文中权重×1
    返回 top_k 条结果
    """
    query_words = set(jieba.cut(query))
    scores = {}

    for path, item in index.items():
        score = 0
        title_words = set(jieba.cut(item["title"]))
        desc_words  = set(jieba.cut(item.get("description", "")))
        kw_words    = set(item.get("keywords", []))
        content_words = set(jieba.cut(item.get("content_snippet", "")))

        for w in query_words:
            if w in title_words:
                score += 4
            if w in desc_words:
                score += 2
            if w in kw_words:
                score += 1
            if w in content_words:
                score += 0.5

        if score > 0:
            scores[path] = score

    ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k]
    return [{"path": p, "score": s, **index[p]} for p, s in ranked]


# ── 第4步：主爬取流程 ────────────────────────────────────────────────────────

def crawl():
    """完整爬取流程"""
    start = datetime.datetime.now()
    log(f"开始爬取知识库 → {KB_ROOT}")

    # ── 0. 初始化目录 ──────────────────────────────────────────────────────
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MD_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. 获取站点元数据 ──────────────────────────────────────────────────
    meta = fetch_vitepress_metadata()
    links = meta["links"]

    # ── 2. 遍历爬取所有页面 ─────────────────────────────────────────────────
    client = httpx.Client(
        headers=HEADERS,
        timeout=TIMEOUT,
        limits=httpx.Limits(max_connections=CONCURRENCY),
    )

    pages = []
    failed = []
    total  = len(links)

    for i, link in enumerate(links, 1):
        url = urljoin(BASE_URL, link)
        slug = slugify(link.lstrip("/"))
        raw_path = RAW_DIR / f"{slug}.html"
        md_path  = MD_DIR  / f"{slug}.md"

        # 增量：已有则跳过（可加 --force 强制重爬）
        if raw_path.exists() and md_path.exists():
            try:
                with open(raw_path, encoding="utf-8") as f:
                    html = f.read()
                page_data = extract_content(html, url)
                page_data["path"] = link
                pages.append(page_data)
                log(f"  [{i}/{total}] 跳过（已存在） {link}")
                continue
            except Exception:
                pass  # 文件损坏，重新爬

        try:
            resp = client.get(url, follow_redirects=True)
            if resp.status_code == 404:
                # VitePress 也可能输出 .md 文件，试试直接访问源
                md_url = urljoin(BASE_URL, link + ".md")
                resp = client.get(md_url, follow_redirects=True)

            html = resp.text
            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(html)

            page_data = extract_content(html, url)
            page_data["path"] = link

            # 保存 Markdown
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(f"# {page_data['title']}\n\n")
                if page_data['description']:
                    f.write(f">{page_data['description']}\n\n")
                f.write(page_data['content_md'])

            pages.append(page_data)
            log(f"  [{i}/{total}] ✓ {link}")

        except Exception as e:
            failed.append((link, str(e)))
            log(f"  [{i}/{total}] ✗ {link}: {e}")

        # 礼貌停顿
        time.sleep(PAUSE_MIN + (PAUSE_MAX - PAUSE_MIN) * (i % 5) / 5)

    client.close()

    # ── 3. 构建索引 ─────────────────────────────────────────────────────────
    index = build_search_index(pages)
    save_json(index, INDEX_F)

    # ── 4. 保存元数据 ───────────────────────────────────────────────────────
    meta_info = {
        "crawled_at": start.isoformat(),
        "finished_at": datetime.datetime.now().isoformat(),
        "total_links": total,
        "pages_crawled": len(pages),
        "pages_failed": len(failed),
        "failed_urls": [{"link": l, "error": e} for l, e in failed],
        "version": start.strftime("%Y%m%d"),
    }
    save_yaml(meta_info, META_F)

    # ── 5. 报告 ─────────────────────────────────────────────────────────────
    elapsed = datetime.datetime.now() - start
    log(f"\n爬取完成！耗时 {elapsed}")
    log(f"  成功: {len(pages)} / {total}")
    if failed:
        log(f"  失败: {len(failed)}")
        for l, e in failed[:5]:
            log(f"    {l}: {e}")

    return pages, index, meta_info


# ── 入口 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    if force:
        # 删除已有文件，强制重爬
        import shutil
        if RAW_DIR.exists():
            shutil.rmtree(RAW_DIR)
        if MD_DIR.exists():
            shutil.rmtree(MD_DIR)
        log("强制重爬模式：已清除本地缓存")

    pages, index, meta = crawl()
    print(f"\n最终结果：")
    print(f"  爬取页面数: {meta['pages_crawled']}")
    print(f"  失败页面数: {meta['pages_failed']}")
    print(f"  索引路径:   {INDEX_F}")
    print(f"  Markdown:  {MD_DIR}")
