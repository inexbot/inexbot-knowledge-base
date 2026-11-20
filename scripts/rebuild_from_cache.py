#!/usr/bin/env python3
"""
从本地缓存的 raw/*.html 重建 md/*.md 与 index.json —— 不联网。

用途：crawler.py 的清洗逻辑（零宽字符、标题兜底、slug 规则）改动后，
不必跑 --force 全量重爬（那会 shutil.rmtree 掉全部 raw 缓存，代价是重新抓 558 页），
只需用已缓存的 HTML 重新抽取即可。

⚠️ 2026-11-19：重建时必须从**上游 sitemap** 重新取一次 URL 形态
（普通页 ".html" / 目录页 "/index.html"），否则重建出来的 index 会丢掉
`url_suffix` 字段 → 引用链接全部 404。
仅当 sitemap 不可用时才退回按 key 推断（见下方 fallback）。
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

SKILL = Path.home() / ".hermes/skills/productivity/inexbot-knowledge-base"
sys.path.insert(0, str(SKILL / "scripts"))

import crawler as C  # noqa: E402

ROOT = Path.home() / ".hermes" / "kb" / "inexbot"
RAW = ROOT / "raw"
MD = ROOT / "md"
INDEX_F = ROOT / "index.json"

# ⚠️ 字面零宽字符写进源码会被工具链静默吞掉（只留空串）⇒
#    `"" in title` 恒为 True ⇒ 报出「ZWSP 条目数 = 全量」的假阳性。
#    必须用 chr() 显式构造（见 shared-proxy-service-pitfalls.md §零宽字符坑）。
ZWSP = chr(0x200B)


def fetch_suffix_map():
    """
    从上游 sitemap 取「key -> url 后缀」映射。

    ⚠️ 2026-11-19：上游 doc.inexbot.com 改成了 .html 后缀路由，
    而 index 的 key 是去掉后缀的相对路径 —— 单靠 key 还原不出正确 URL。
    目录页 vs 普通页的判据是 **sitemap 原始 URL 是否以 '/' 结尾**。
    """
    try:
        meta = C.fetch_vitepress_metadata()
        return meta.get("suffix_map", {})
    except Exception as e:
        print(f"  WARN: sitemap 获取失败（{e}），退回按 key 推断后缀")
        return {}


def infer_suffix(link: str) -> str:
    """
    兜底推断：无法访问 sitemap 时用启发式。

    实测 15 条目录页都是「已知的一级/二级目录」，普通页不以 '/' 结尾。
    但 key 里只有 /zh/ 一条以 '/' 结尾 ⇒ 目录页信息丢失 ⇒ 只能对
    「能从 sitemap 之外的信息判断」的页面用 .html，其余按 .html 处理。
    （真正目录页链接会退化成 404，但普通页 —— 绝大多数 —— 正确。）
    """
    return ".html"


def main():
    if not INDEX_F.exists():
        print("index.json 不存在，请先跑一次 crawler.py")
        return 1
    if not RAW.exists():
        print("raw/ 缓存不存在，请跑 crawler.py --force")
        return 1

    # 用现有 index 的 key 顺序作为 URL 列表（保持条目顺序稳定）
    old = json.loads(INDEX_F.read_text(encoding="utf-8"))
    links = list(old.keys())

    # 取一次 sitemap 拿 URL 形态映射（只 1 次 GET，不重抓正文）
    suffix_map = fetch_suffix_map()
    if suffix_map:
        print(f"sitemap URL 形态映射: {len(suffix_map)} 条 "
              f"(目录页 {sum(1 for v in suffix_map.values() if v == '/index.html')} 条)")

    pages, rebuilt, missing = [], 0, 0
    for link in links:
        slug = C.slugify(link.lstrip("/").rstrip(".html"))
        raw_p = RAW / f"{slug}.html"
        md_p = MD / f"{slug}.md"
        if not raw_p.exists():
            print(f"  MISSING raw: {link}")
            missing += 1
            continue

        html = raw_p.read_text(encoding="utf-8")
        url = urljoin(C.BASE_URL, link)
        d = C.extract_content(html, url)
        d["path"] = link
        d["url_suffix"] = suffix_map.get(link) or infer_suffix(link)

        with open(md_p, "w", encoding="utf-8") as f:
            f.write(f"# {d['title']}\n\n")
            if d["description"]:
                f.write(f">{d['description']}\n\n")
            f.write(d["content_md"])
        pages.append(d)
        rebuilt += 1

    print(f"rebuilt {rebuilt}/{len(links)} pages from raw cache"
          + (f" ({missing} missing raw)" if missing else ""))

    index = C.build_search_index(pages)
    C.save_json(index, INDEX_F)

    new = json.loads(INDEX_F.read_text(encoding="utf-8"))
    zw = sum(1 for v in new.values()
             if ZWSP in (v.get("title") or "") or ZWSP in (v.get("description") or ""))
    empty = sum(1 for v in new.values() if not (v.get("title") or "").strip())
    print(f"entries={len(new)}  ZWSP-in-title/desc={zw}  empty-titles={empty}")
    print(f"index.json: {INDEX_F.stat().st_size:,} bytes")

    # 校验 md ↔ index 对账
    slugs = {C.slugify(k.lstrip("/").rstrip(".html")) for k in new}
    mds = list(MD.glob("*.md"))
    orphans = [p.name for p in mds if p.stem not in slugs]
    print(f"md files={len(mds)}  orphan={len(orphans)}")
    if zw or empty or orphans or missing:
        print("⚠ 有异常项，见上方计数")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())