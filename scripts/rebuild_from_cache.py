#!/usr/bin/env python3
"""
从本地缓存的 raw/*.html 重建 md/*.md 与 index.json —— 不联网。

用途：crawler.py 的清洗逻辑（零宽字符、标题兜底、slug 规则）改动后，
不必跑 --force 全量重爬（那会 shutil.rmtree 掉全部 raw 缓存，代价是重新抓 558 页），
只需用已缓存的 HTML 重新抽取即可。
"""
import json
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

ZWSP = ""


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