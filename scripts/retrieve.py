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

def extract_images_from_md(path: str) -> list:
    """从本地 Markdown 文件中提取图片 URL"""
    # 尝试原始 path
    md_path = KB_ROOT / "md" / f"{path.lstrip('/')}.md"
    if not md_path.exists():
        # 尝试 slugify 后的文件名（/ 替换为 -）
        md_path = KB_ROOT / "md" / f"{slugify_path(path)}.md"
    if not md_path.exists():
        md_path = KB_ROOT / "md" / f"{urllib.parse.quote(path.lstrip('/'))}.md"
    if not md_path.exists():
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
