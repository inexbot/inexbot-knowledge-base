#!/usr/bin/env python3
"""按关键词扫 KB 的 index.json，列出某主题的全部页面 + 官方链接。

用途：用户问「X 工艺/协议/模块 手册 参数设置」这类主题性问题时，
先一次列全该主题的所有页面（而不是靠 proxy top-5 试错），
再决定读哪些 md 全文。

用法:
    python3 scan_kb_topic.py 冲压                 # 扫 inexbot 主库
    python3 scan_kb_topic.py 冲压 --kb open       # 扫 open 开放平台库
    python3 scan_kb_topic.py Modbus --both        # 两个库都扫
    python3 scan_kb_topic.py 冲压 --links         # 只输出可点击的官方链接

⚠️ 不要用 search_files(pattern="中文关键词", path=<md_root>) 找中文正文内容 ——
   它对中文正文恒返回 0 命中（glob 走文件名才有效）。本脚本走 index.json，绕开该限制。
⚠️ index.json 的 key 已是 percent-encoded URL path → "https://doc.inexbot.com" + key
   直接就是可点击链接，不要自己拼中文路径。

⚠️ md 文件名规则必须与 crawler.py 的 slugify() 保持一致 —— 这里直接 import 复用，
   不要自己复刻（2026-11-08 修复：原先用 `key.lstrip('/').replace('/','-')` 只能解析
   1/560，因为 crawler 是先 unquote 再把 / 换成 -）。
"""
import argparse
import hashlib
import json
import os
import re
import sys
from urllib.parse import unquote

KBs = {
    "inexbot": ("https://doc.inexbot.com", os.path.expanduser("~/.hermes/kb/inexbot")),
    "open": ("https://open.inexbot.com", os.path.expanduser("~/.hermes/kb/inexbot-open")),
}


def _crawler_slugify(text: str, max_len: int = 200) -> str:
    """crawler.py slugify() 的等价实现（保持两份同步；改动请同时改 crawler.py）。

    注意：字面零宽字符不能写进源码（会被静默吞掉），本函数不涉及该字符集。
    """
    text = unquote(text)
    text = text.strip().replace("/", "-").replace("\\", "-")
    text = re.sub(r'[<>:"|?*]', '', text)
    if len(text.encode("utf-8")) > max_len:
        head = text.encode("utf-8")[:max_len - 16].decode("utf-8", errors="ignore")
        text = f"{head}-{hashlib.md5(text.encode()).hexdigest()[:8]}"
    return text


def md_filename(key: str) -> str:
    """给定 index.json 的 key，返回对应的 md 文件名。

    与 crawler.py（line 519: slugify(link.lstrip('/').rstrip('.html'))）一致。
    """
    return _crawler_slugify(key.lstrip("/").rstrip(".html")) + ".md"


def load_index(kb_name):
    base_url, root = KBs[kb_name]
    idx_path = os.path.join(root, "index.json")
    if not os.path.exists(idx_path):
        return base_url, root, None
    with open(idx_path, encoding="utf-8") as f:
        idx = json.load(f)
    return base_url, root, idx


def scan(kb_name: str, keyword: str):
    base_url, root, idx = load_index(kb_name)
    if idx is None:
        print("[SKIP] %s: %s 不存在" % (kb_name, os.path.join(root, "index.json")))
        return []
    hits = []
    for key, val in idx.items():
        title = val.get("title") or ""
        desc = val.get("description") or ""
        if keyword in title or keyword in desc:
            hits.append((key, title, desc, val))
    hits.sort(key=lambda x: x[1])
    print("=== %s (%d 命中 / 共 %d 条) base=%s ===" % (kb_name, len(hits), len(idx), base_url))
    for key, title, desc, val in hits:
        snippet = val.get("content_snippet") or ""
        print("- %s" % title)
        print("  url   : %s" % (base_url + key))
        print("  key   : %s" % key)
        print("  md    : %s/md/%s" % (root, md_filename(key)))
        print("  desc  : %s" % desc[:80])
        print("  snip  : %d 字符%s" % (
            len(snippet),
            "  (空壳页? description=='Not Found')" if desc == "Not Found" else ""))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword", help="关键词（在 title / description 中做子串匹配）")
    ap.add_argument("--kb", default="inexbot", choices=["inexbot", "open", "both"])
    ap.add_argument("--links", action="store_true", help="只输出 Markdown 链接行")
    args = ap.parse_args()

    targets = ["inexbot", "open"] if args.kb == "both" else [args.kb]
    for kb in targets:
        if args.links:
            base_url, root, idx = load_index(kb)
            if idx is None:
                continue
            for key, val in sorted(idx.items(), key=lambda kv: kv[1].get("title") or ""):
                title = val.get("title") or ""
                desc = val.get("description") or ""
                if args.keyword in title or args.keyword in desc:
                    print("[%s](%s)" % (title, base_url + key))
        else:
            scan(kb, args.keyword)


if __name__ == "__main__":
    sys.exit(main())
