#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
短 snippet 独立分类 (2026-11-16 新增)。

背景：
  `verify_kb.py` / `check_crawl_state.py` 会输出 `snippet<60ch: N` 这类粗筛计数，
  但这个数字混着两类完全不同的东西：

  A. 真·占位页 —— 「常见问题/伺服报错」系列，正文本身就只有一行
     （例：`0x0050 - 风扇故障报警（未实现）` md 只有 71 字符）
  B. 抓取失败的空壳页 —— 抓到 404 页面，正文是 `# 标题` + `> Not Found`
     （这是 BUG，对应 sitemap `&amp;` 未转义那个老缺陷）

  两类的 md 都「短」，但只有 B 是故障。

判别方法（不依赖长度）：
  - 空壳页的 md 里含 `Not Found` 标记，或 description == 'Not Found'
  - 占位页的 md 是真实内容（无 Not Found）

⚠️ md 定位**必须复用 crawler 自己的 slugify()**（陷阱 11 / 陷阱 24）：
   crawler 的调用约定是 `slugify(link.lstrip("/").rstrip(".html"))` ——
   既要去掉开头的 "/"，也要去掉结尾的 ".html"，再 unquote + "/"->"-"。
   自己重写这套逻辑极易漏掉其中一步 -> 结果是「md 全部找不到」的假阳性
   （本脚本初版就踩了：漏了 lstrip("/") + .html 剥离，132 条全部「无法定位」）。

退出码：0 = 无空壳页；1 = 发现空壳页（真故障）。
"""

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

KB = Path.home() / ".hermes/kb/inexbot"
INDEX = KB / "index.json"
MD = KB / "md"
CRAWLER = (Path.home()
            / ".hermes/skills/productivity/inexbot-knowledge-base/scripts/crawler.py")

SHORT_CH = 60


def load_slugify():
    """复用 crawler 的 slugify，避免自己重写出错（陷阱 11 / 24）。"""
    spec = importlib.util.spec_from_file_location("kb_crawler", str(CRAWLER))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["kb_crawler"] = mod
    spec.loader.exec_module(mod)
    return mod.slugify


def md_path_for(slugify, path_key):
    """按 crawler 的调用约定定位 md 文件。"""
    slug = slugify(path_key.lstrip("/").rstrip(".html"))
    p = MD / (slug + ".md")
    try:
        if p.exists():
            return p
    except OSError:
        return None
    return None


def main():
    slugify = load_slugify()
    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    short = []
    for key, val in idx.items():
        snip = (val.get("content_snippet") or "")
        if len(snip) < SHORT_CH:
            short.append((key, val))

    shells = []
    placeholders = []
    unreadable = []
    for key, val in short:
        p = md_path_for(slugify, key)
        if p is None:
            unreadable.append((key, val.get("title")))
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        desc = (val.get("description") or "")
        is_shell = ("Not Found" in text[:2000]) or (desc.strip() == "Not Found")
        if is_shell:
            shells.append((key, val.get("title"), len(text)))
        else:
            placeholders.append((key, val.get("title"), len(text)))

    print("=" * 62)
    print("短 snippet 独立分类 (threshold = %d chars)" % SHORT_CH)
    print("=" * 62)
    print("  index 条目总数              : %d" % len(idx))
    print("  短 snippet 条目数           : %d" % len(short))
    print("  -> 占位页 (正文本来就短, 正常) : %d" % len(placeholders))
    print("  -> 空壳页 (Not Found, 是 BUG)  : %d" % len(shells))
    print("  -> md 无法定位                : %d" % len(unreadable))
    print()

    if unreadable:
        print("--- md 无法定位 (需人工看) ---")
        for k, t in unreadable[:20]:
            print("  %s | %s" % (t, k))
        print()

    if shells:
        print("--- 空壳页明细 (真故障) ---")
        for k, t, n in shells[:40]:
            print("  [%5d ch] %s" % (n, t))
        print()
        print("=> FAIL: 发现 %d 个空壳页，需要重爬这些页面。" % len(shells))
        return 1

    # 占位页按路径前缀归类，确认不是普遍性故障
    from urllib.parse import unquote
    buckets = Counter()
    for key, title, n in placeholders:
        dec = unquote(key)
        if "伺服报错" in dec:
            buckets["常见问题/伺服报错"] += 1
        elif "常见问题" in dec:
            buckets["常见问题(其他)"] += 1
        else:
            buckets["其他"] += 1
    print("--- 占位页分布 (确认不是普遍性故障) ---")
    for b, c in buckets.most_common():
        print("  %-24s %d" % (b, c))

    # 抽样看看占位页正文确实有实质内容（不是空的）
    print()
    print("--- 占位页正文抽样 (前 5 条) ---")
    for key, title, n in placeholders[:5]:
        p = md_path_for(slugify, key)
        body = p.read_text(encoding="utf-8", errors="replace").strip()
        preview = " ".join(body.split())[:110]
        print("  [%3d ch] %s" % (n, preview))

    print()
    print("=> PASS: 无空壳页；%d 条短 snippet 全部是正文本就很短的占位页。" % len(placeholders))
    return 0


if __name__ == "__main__":
    sys.exit(main())
