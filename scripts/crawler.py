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
ZH_URL   = f"{BASE_URL}/zh/"  # 直接访问中文站，避开根路径的 client-side 语言跳转
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"  # 站点总 sitemap（含全部 zh/en 页面 URL）
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

def slugify(text: str, max_len: int = 200) -> str:
    """
    把任意文本转成安全文件名（保留中文）。

    Linux 文件名长度限制 255 字节。doc.inexbot.com 常见问题页 URL 可能很长
    （含 URL 编码 + 中文 + 括号 + 后缀），需要：
    2. 把 URL 编码转回中文（%XX → 原字符），再 slugify，可大幅缩短
    3. 仍超长则用 MD5 截断到 max_len，确保唯一且不会超限
    """
    from urllib.parse import unquote
    text = unquote(text)
    text = text.strip().replace("/", "-").replace("\\", "-")
    text = re.sub(r'[<>:"\|?*]', '', text)
    if len(text.encode("utf-8")) > max_len:
        # 保留前 max_len - 16 字符 + MD5 后缀，保证唯一
        head = text.encode("utf-8")[:max_len - 16].decode("utf-8", errors="ignore")
        text = f"{head}-{md5_text(text)}"
    return text

def md5_text(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:8]

def save_json(obj, path: Path):
    """
    原子写入 JSON。

    ⚠️ 必须先写临时文件再 os.replace()：hermes-skill-proxy 每 5 小时读一次
    index.json，直接 open(path,"w") 会先把文件截断成空，再慢慢写入 ——
    这期间 proxy 若正好读到，会 json.load() 抛错。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

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
    页面发现（按优先级）：
    1. /sitemap.xml —— 最稳定，包含全部 zh/en 页面 URL
    2. 首页 /zh/ 的 __VP_HASH_MAP__（备用，确认站点是否变动）
    """
    log("正在获取 VitePress 站点配置...")
    client = httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)

    # 1. sitemap
    links = []
    try:
        resp = client.get(SITEMAP_URL)
        resp.raise_for_status()
        xml = resp.text
        # 提取 <loc>…</loc>
        # ⚠ 必须 html.unescape()：sitemap 里的 URL 是 XML 转义过的，
        # 例如「通讯协议&地址码」写作 `通讯协议&amp;地址码`。
        # 不还原就按字面 `&amp;` 去请求 → 404 → 该页永远是 "Not Found" 空壳
        # （2026-10-24 实测：1/558 页中招，正文 2609 字符全丢）。
        from html import unescape
        all_locs = [unescape(u) for u in re.findall(r'<loc>([^<]+)</loc>', xml)]
        # 只保留中文页（/zh/...），避免重复索引英文版本
        links = [u for u in all_locs if "/zh/" in u]
        log(f"  sitemap 发现 {len(all_locs)} 个 URL（中文 {len(links)} 个）")
    except Exception as e:
        log(f"  ⚠ sitemap 获取失败: {e}")

    # 2. 备用：访问 /zh/ 拿 hash_map 用于后续验证（但不做 sidebar 解析——VP v2 alpha
    #    把 sidebar 拆到了外部 JS chunk，site_data 里只有 i18nRouting+search）
    html = ""
    hash_map = {}
    try:
        resp = client.get(ZH_URL)
        resp.raise_for_status()
        html = resp.text
        hm_match = re.search(
            r'window\.__VP_HASH_MAP__\s*=\s*JSON\.parse\("((?:[^"\\]|\\.)*)"',
            html, re.DOTALL
        )
        if hm_match:
            raw = hm_match.group(1).replace('\\"', '"').replace('\\\\', '\\')
            hash_map = json.loads(raw)
        log(f"  hash_map 共 {len(hash_map)} 个文件 hash")
    except Exception as e:
        log(f"  ⚠ /zh/ 获取失败: {e}")

    client.close()

    # 把 URL 转成相对路径（/zh/...），作为本地文件名 + 索引 key
    rel_links = []
    for u in links:
        m = re.search(r'(/zh/.*?)(?:\.html)?/?$', u)
        if m:
            rel_links.append(m.group(1))

    # 去重保持顺序
    seen, unique = set(), []
    for l in rel_links:
        if l not in seen:
            seen.add(l)
            unique.append(l)

    log(f"  最终页面列表: {len(unique)} 条")
    return {"links": unique, "hash_map": hash_map, "html": html}


# ── 第2步：提取页面正文 ───────────────────────────────────────────────────────

def clean_text(s: str) -> str:
    """
    清洗文本：去掉零宽字符（U+200B 等）和行尾空白。

    doc.inexbot.com 的 <h1> 普遍带一个 U+200B 零宽空格（VitePress 编辑器残留），
    例如 'T30 示教器\\u200b'。不去掉的话：
      1. 每个注入给 LLM 的标题末尾都挂一个不可见字符，引用链接显示时带怪字符；
      2. 标题分词时可能把 '示教器\\u200b' 当成一个整体 token，影响精确匹配。
    实测 jieba 会把 U+200B 单独切出来（len<2 被过滤），对检索命中影响有限，
    但对展示和精确匹配仍有干扰 —— 统一清掉更干净。

    注意：只去零宽字符 + 行尾空白，**不压缩内部空格/制表符** ——
    正文含代码块，压缩缩进会破坏代码内容。
    """
    if not s:
        return ""
    # 零宽字符（U+200B/200C/200D）+ BOM：直接删除（不是替换成空格，避免把词切开）
    s = re.sub(r"[​‌‍﻿]", "", s)
    # NBSP 不换行空格 → 普通空格（中文正文里常出现）
    s = s.replace("\xa0", " ")
    # 行尾空白
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    return s.strip()


def extract_content(html: str, url: str) -> dict:
    """
    从 VitePress 预渲染的 HTML 页面中提取：
    - title（<h1>）
    - content（<article class="page"> 或 <main> 或 <h1> 后所有内容）
    - 描述（description meta）

    适配 doc.inexbot.com 使用的 VitePress v2 alpha：
    - 没有 <article class="page">，没有 <main> 包裹
    - h1/h2/h3 + p + table 直接渲染在 body 中
    """
    soup = BeautifulSoup(html, "html.parser")

    # 标题
    h1 = soup.find("h1")
    title = clean_text(h1.get_text(strip=True)) if h1 else ""

    # 标题兜底：部分页面没有 <h1>（如「行业方案/医疗器械人」「冲压工艺2.0手册」这类
    # 以内容直接开头的页），此时依次回退 og:title → URL 末段 → description。
    # 兜底很重要：proxy 检索对标题给 ×4 权重，标题为空等于丢掉 4 倍权重。
    if not title:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            title = clean_text(og["content"])

    if not title:
        # URL 末段就是文档真实名称（如 '冲压工艺2.0手册'），比 description 更贴题
        from urllib.parse import unquote
        from html import unescape
        seg = unquote(url.rstrip("/").split("/")[-1]) if url.rstrip("/") else ""
        seg = unescape(seg)          # &amp; → &
        seg = clean_text(seg)
        # 去掉 .html 后缀和明显的 slug 噪声
        seg = re.sub(r"\.html?$", "", seg).strip()
        if seg and not seg.lower().startswith(("readme", "index")):
            title = seg[:120]

    if not title:
        desc_tag_tmp = soup.find("meta", attrs={"name": "description"})
        if desc_tag_tmp and desc_tag_tmp.get("content"):
            cand = clean_text(desc_tag_tmp["content"])[:120]
            # 通用描述（如 '纳博特科技官方知识库'）当标题没有信息量，跳过
            if cand and cand != "纳博特科技官方知识库" and cand.lower() != "not found":
                title = cand

    # 描述
    desc_tag = soup.find("meta", attrs={"name": "description"})
    description = clean_text(desc_tag["content"]) if desc_tag and desc_tag.get("content") else ""

    # 正文区域（按优先级寻找）
    article = soup.find("article", class_="page")
    if not article:
        article = soup.find("main")
    if not article:
        # VP v2 alpha: 取 <h1> 的父级（通常是 body 或 VPDoc 容器）
        if h1:
            # 往上找到 class 含 VPDoc 的 div，作为正文根
            parent = h1.parent
            while parent and parent.name not in ("body", "html"):
                cls = parent.get("class", []) or []
                if any("Doc" in c or "doc" in c for c in cls) or parent.name == "main":
                    break
                parent = parent.parent
            article = parent or h1.parent

    content_md = ""
    keywords_set = set()

    if article:
        # 深度清理：移除导航、侧边栏、脚本、样式等干扰元素
        for tag in article.find_all(["nav", "script", "style", "footer",
                                      "aside", "button", "input"]):
            tag.decompose()
        # 移除 header-anchor 链接（VP 在每个标题后插的「#」锚点）
        for tag in article.find_all("a", class_="header-anchor"):
            tag.decompose()

        # 进一步：只取 <h1> 之后的内容（VP v2 alpha 中 article 可能含 sidebar/VPNav）
        h1_in_article = article.find("h1")
        if h1_in_article:
            # 收集从 h1 开始的所有后续兄弟元素
            captured = [h1_in_article]
            for sib in h1_in_article.find_next_siblings():
                captured.append(sib)
                # 停止条件：碰到 VPDocFooter / pager（翻页栏）就停
                cls = " ".join(sib.get("class", []) or [])
                if "VPDocFooter" in cls or sib.name in ("script", "style"):
                    captured.pop()  # 不含 footer
                    break
            # 临时包一层供 _element_to_md 处理
            from bs4 import Tag
            wrapper = Tag(name="div")
            for el in captured:
                wrapper.append(el.extract() if el.parent else el)
            content_md, keywords_set = _element_to_md(wrapper, base_url=url)
        else:
            content_md, keywords_set = _element_to_md(article, base_url=url)

    return {
        "title": title,
        "description": description,
        "content_md": clean_text(content_md),
        "url": url,
        "keywords": sorted(keywords_set),
    }


def _element_to_md(element, depth=0, base_url="") -> tuple:
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
            inner_md, inner_kw = _element_to_md(child, depth + 1, base_url)
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
                abs_src = urljoin(base_url, src) if base_url else src
                lines.append(f"![{alt}]({abs_src})")

        # 其他：递归处理
        else:
            inner_md, inner_kw = _element_to_md(child, depth + 1, base_url)
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
        content = page.get("content_md", "")[:1000]  # 前1000字作摘要，给 LLM 更多上下文

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
            "content_snippet": content[:800],
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
        # link 是相对路径（如 /zh/产品资料/控制系统/T30示教器）；拼成绝对 URL
        url = urljoin(BASE_URL, link) if not link.startswith("http") else link
        slug = slugify(link.lstrip("/").rstrip(".html"))
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
            # 1. 直接试 link 本身
            resp = client.get(url, follow_redirects=True)
            # 2. 404 或 SPA fallback 时，尝试 /zh/xxx/index.html 或 /zh/xxx.html
            if resp.status_code == 404 or len(resp.text) == 147235 and "<title>404" in resp.text:
                for alt in (link.rstrip("/") + ".html",
                            link.rstrip("/") + "/index.html",
                            link.rstrip("/") + ".md"):
                    alt_url = urljoin(BASE_URL, alt) if not alt.startswith("http") else alt
                    r2 = client.get(alt_url, follow_redirects=True)
                    if r2.status_code == 200 and len(r2.text) > 1000 and "<title>404" not in r2.text:
                        resp = r2
                        break

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
