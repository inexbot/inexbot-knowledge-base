#!/usr/bin/env python3
"""
纳博特知识库检索脚本
用法：
  python3 retrieve.py "<用户问题>" [top_k]
示例：
  python3 retrieve.py "工具手标定有几种方法" 3
"""

import sys
import json
import re
import urllib.parse
from pathlib import Path

import jieba

# ── 配置 ────────────────────────────────────────────────────────────────────

KB_ROOT = Path.home() / ".hermes" / "kb" / "inexbot"
INDEX_F = KB_ROOT / "index.json"
BASE_URL = "https://doc.inexbot.com"

# ── 检索逻辑 ─────────────────────────────────────────────────────────────────

def load_index() -> dict:
    if not INDEX_F.exists():
        print(f"错误：索引文件不存在，请先运行爬虫", file=sys.stderr)
        sys.exit(1)
    with open(INDEX_F, encoding="utf-8") as f:
        return json.load(f)

def search_index(index: dict, query: str, top_k: int = 3) -> list:
    """
    在索引中检索相关页面。
    策略：查询词在标题中权重×4，描述中权重×2，正文中权重×1
    返回 top_k 条结果
    """
    query_words = set(jieba.cut(query))
    query_words = {w for w in query_words if len(w) >= 2}  # 过滤单字
    scores = {}

    for path, item in index.items():
        score = 0
        title_words = set(jieba.cut(item.get("title", "")))
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
    return [index[path] for path, _ in ranked]


def slugify_path(path: str) -> str:
    """把 URL path 转为 md 文件名（/ → -）"""
    return path.lstrip("/").replace("/", "-")


def md_candidates(path: str) -> list:
    """
    列出可能命中的 md 文件名候选（按优先级）。

    ⚠️ index.json 的 key 是 **percent 编码**的（/zh/%E4%BA%A7...），
    而 crawler 的 slugify() 会先 unquote 再把 / 换成 -，
    所以真实文件名是「解码后 + /→-」，不是原始编码态。
    旧实现只试了原始态和 quote() 态 → 绝大多数页面找不到 md，
    导致 extract_images_from_md() 永远返回 []（附图全部丢失）。
    """
    raw = path.lstrip("/")
    cands = [
        raw.replace("/", "-"),
        urllib.parse.unquote(raw).replace("/", "-"),
        urllib.parse.quote(raw, safe=""),
    ]
    out = []
    for c in cands:
        if c not in out:
            out.append(c)
    return out


def extract_images_from_md(path: str) -> list:
    """从本地 Markdown 文件中提取图片 URL"""
    md_path = None
    for cand in md_candidates(path):
        p = KB_ROOT / "md" / f"{cand}.md"
        try:
            if p.exists():
                md_path = p
                break
        except OSError:
            continue
    if md_path is None:
        return []

    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    # 匹配 ![alt](url) 格式
    imgs = re.findall(r'!\[([^\]]*)\]\((https?://[^\)]+)\)', content)
    return imgs[:5]  # 最多返回5张图片

def format_result(item: dict, rank: int) -> str:
    """格式化单条检索结果"""
    path = item["path"]
    url = BASE_URL + path
    title = item.get("title", "")
    desc = item.get("description", "")
    snippet = item.get("content_snippet", "")

    # 提取图片
    images = extract_images_from_md(path)

    lines = []
    lines.append(f"[{rank}] {title}")
    lines.append(f"    链接：{url}")

    if desc:
        lines.append(f"    简介：{desc}")

    if snippet:
        lines.append(f"    摘要：{snippet[:500]}")

    if images:
        lines.append(f"    图片：")
        for alt, img_url in images:
            lines.append(f"      - [{alt}] {img_url}")

    return "\n".join(lines)

# ── 入口 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python3 retrieve.py <用户问题> [top_k]")
        sys.exit(1)

    query = sys.argv[1]
    top_k = int(sys.argv[2]) if len(sys.argv) >= 3 else 3

    index = load_index()
    results = search_index(index, query, top_k)

    if not results:
        print("未找到相关结果", file=sys.stderr)
        sys.exit(1)

    print(f"=== 检索到 {len(results)} 条相关结果 ===\n")
    for i, item in enumerate(results, 1):
        print(format_result(item, i))
        print()
