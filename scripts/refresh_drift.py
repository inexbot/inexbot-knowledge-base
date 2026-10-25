#!/usr/bin/env python3
"""
安全漂移刷新（safe drift refresh）
=================================

问题：`crawler.py` 默认是增量的（raw/ 和 md/ 已存在就跳过），所以「成功 558/558」
不代表上游没变 —— 页面正文被改也会全部显示「跳过（已存在）」。
`crawler.py --force` 能发现漂移，但它会 `shutil.rmtree` 掉整个 raw/ 和 md/ 缓存
（247MB / 558 页），重抓期间缓存全空，一旦中途网络失败就会丢页面。

本脚本取两者之长：
  1. 重新抓取**全部**页面 → 能发现所有上游漂移（不只是抽样 25 页）
  2. **只在内容真的变了时**才覆盖本地 raw/ + md/ → 缓存始终是完整的
  3. 抓取失败的页面**保留旧缓存**，并计入 failed 列表，不会静默丢页
  4. 最后用 crawler 自己的 build_search_index() 重建 index.json（含新增/下线的页面）
  5. 复用 crawler.extract_content() / slugify()，不复制清洗逻辑（避免契约漂移）

图片 URL 变更（VitePress 资源 hash 重命名）单独归类为 IMG_ONLY，不算正文漂移，
但同样会刷新本地文件（因为图片链接确实变了，旧链接可能已 404）。

用法：
    python3 refresh_drift.py                # 全量刷新
    python3 refresh_drift.py --workers 6    # 指定并发数
    python3 refresh_drift.py --dry-run      # 只报告差异，不写任何文件

退出码：0 = 正常（含纯 IMG_ONLY 变化），1 = 有抓取失败或正文变更需人工确认
"""
import sys
import json
import datetime
import time
import difflib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crawler as C  # noqa: E402  复用其 slugify / extract_content / build_search_index

WORKERS = 6
DRY_RUN = "--dry-run" in sys.argv
for i, a in enumerate(sys.argv):
    if a == "--workers" and i + 1 < len(sys.argv):
        WORKERS = max(1, min(12, int(sys.argv[i + 1])))

KB_ROOT = C.KB_ROOT
RAW_DIR = C.RAW_DIR
MD_DIR = C.MD_DIR
INDEX_F = C.INDEX_F
META_F = C.META_F

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (compatible; HermesBot/1.0; "
                   "+https://github.com/nousresearch/hermes-agent)"),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def build_md(d: dict) -> str:
    """复刻 crawler.py 写 md 的格式（用于比对）。"""
    s = f"# {d['title']}\n\n"
    if d["description"]:
        s += f">{d['description']}\n\n"
    s += d["content_md"]
    return s.strip()


def strip_img(t: str) -> str:
    """把图片 URL 归一化，用于区分「仅图片 hash 变化」与「正文变更」。"""
    import re
    return re.sub(r"!\[[^\]]*\]\([^)]*\)", "![IMG]", t)


def fetch_one(link: str):
    """抓取一个页面并与本地缓存比对。返回 (link, status, detail)。"""
    url = urljoin(C.BASE_URL, link) if not link.startswith("http") else link
    slug = C.slugify(link.lstrip("/").rstrip(".html"))
    raw_path = RAW_DIR / f"{slug}.html"
    md_path = MD_DIR / f"{slug}.md"

    try:
        import httpx
        with httpx.Client(timeout=C.TIMEOUT, follow_redirects=True, headers=HEADERS) as cl:
            r = cl.get(url)
            # 与 crawler.py 一致的 fallback 链：/x.html、/x/index.html、/x.md
            if r.status_code == 404 or "<title>404" in r.text[:20000]:
                for alt in (link.rstrip("/") + ".html",
                            link.rstrip("/") + "/index.html",
                            link.rstrip("/") + ".md"):
                    alt_url = urljoin(C.BASE_URL, alt)
                    r2 = cl.get(alt_url, follow_redirects=True)
                    if r2.status_code == 200 and len(r2.text) > 1000 and "<title>404" not in r2.text:
                        r = r2
                        break
        if r.status_code != 200:
            return link, f"HTTP{r.status_code}", None
        html = r.text
    except Exception as e:
        return link, f"ERR:{type(e).__name__}", None

    try:
        d = C.extract_content(html, url)
        new_md = build_md(d)
    except Exception as e:
        return link, f"PARSE:{type(e).__name__}", None

    old_md = md_path.read_text(encoding="utf-8").strip() if md_path.exists() else None

    if old_md is None:
        status = "NEW"
    elif new_md == old_md:
        status = "SAME"
    elif strip_img(new_md) == strip_img(old_md):
        status = "IMG_ONLY"
    else:
        status = "CONTENT"

    detail = None
    if status in ("NEW", "CONTENT", "IMG_ONLY"):
        detail = {"link": link, "url": url, "slug": slug,
                  "old": old_md or "", "new": new_md, "title": d["title"]}

    if not DRY_RUN:
        if status in ("NEW", "CONTENT", "IMG_ONLY"):
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            MD_DIR.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(html, encoding="utf-8")
            md_path.write_text(new_md + "\n", encoding="utf-8")

    return link, status, detail


def main():
    start = datetime.datetime.now()
    log(f"安全漂移刷新 → {KB_ROOT}  (workers={WORKERS}, dry_run={DRY_RUN})")

    meta = C.fetch_vitepress_metadata()
    links = meta["links"]
    log(f"  sitemap 发现 {len(links)} 个中文页面")

    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, res in enumerate(ex.map(fetch_one, links), 1):
            results.append(res)
            if i % 50 == 0 or res[1] not in ("SAME",):
                log(f"  [{i}/{len(links)}] {res[1]:<10} {res[0][:80]}")

    cnt = Counter(r[1] for r in results)
    changed = [r[2] for r in results if r[1] == "CONTENT"]
    img_only = [r[2] for r in results if r[1] == "IMG_ONLY"]
    new = [r[2] for r in results if r[1] == "NEW"]
    failed = [(r[0], r[1]) for r in results
              if r[1].startswith(("HTTP", "ERR", "PARSE"))]

    # ── 重建索引：用本地 raw 全量重解析（与 crawler 增量路径同源）────────────
    log("正在重建索引...")
    pages = []
    for link in links:
        slug = C.slugify(link.lstrip("/").rstrip(".html"))
        raw_path = RAW_DIR / f"{slug}.html"
        md_path = MD_DIR / f"{slug}.md"
        url = urljoin(C.BASE_URL, link) if not link.startswith("http") else link
        if raw_path.exists():
            try:
                html = raw_path.read_text(encoding="utf-8")
                d = C.extract_content(html, url)
                d["path"] = link
                pages.append(d)
                continue
            except Exception as e:
                log(f"  ⚠ 解析失败 {link}: {e}")
        # 兜底：raw 不可用时用 md 兜底（保证索引条目数不缩水）
        if md_path.exists():
            txt = md_path.read_text(encoding="utf-8")
            first = txt.splitlines()[0].lstrip("# ").strip() if txt else ""
            pages.append({"title": first, "description": "", "content_md": txt,
                          "path": link, "keywords": []})
            log(f"  ⚠ raw 缺失，用 md 兜底: {link[:70]}")

    index = C.build_search_index(pages)

    # ── 清理孤儿：sitemap 里已下线的页面，其 md/raw 残留在本地会污染计数 ──
    live_slugs = {C.slugify(l.lstrip("/").rstrip(".html")) for l in links}
    orphans = [p for p in list(MD_DIR.glob("*.md")) + list(RAW_DIR.glob("*.html"))
               if p.stem not in live_slugs]
    for p in orphans:
        if not DRY_RUN:
            p.unlink()
    if orphans:
        log(f"  清理孤儿文件 {len(orphans)} 个: "
            + ", ".join(p.name[:50] for p in orphans[:5]))

    if not DRY_RUN:
        C.save_json(index, INDEX_F)
        C.save_yaml({
            "crawled_at": start.isoformat(),
            "finished_at": datetime.datetime.now().isoformat(),
            "total_links": len(links),
            "pages_crawled": len(pages),
            "pages_failed": len(failed),
            "failed_urls": [{"link": l, "error": e} for l, e in failed],
            "version": start.strftime("%Y%m%d"),
            "mode": "refresh_drift",
        }, META_F)

    # ── 报告 ────────────────────────────────────────────────────────────────
    elapsed = datetime.datetime.now() - start
    log(f"\n刷新完成！耗时 {elapsed}")
    log(f"  统计: {dict(cnt)}")
    log(f"  索引条目: {len(index)}  (index.json: {INDEX_F})")

    for d in changed[:10]:
        log(f"\n  ⚠ 正文变更: {d['link']}")
        dl = list(difflib.unified_diff(d["old"].splitlines(), d["new"].splitlines(),
                                       lineterm="", n=1))
        for line in dl[:14]:
            log(f"      {line[:150]}")
    if len(changed) > 10:
        log(f"  ... 另有 {len(changed) - 10} 处正文变更未展开")

    for d in new[:10]:
        log(f"  ＋ 新增页面: {d['link']}")
    for l, e in failed[:10]:
        log(f"  ✗ 抓取失败(保留旧缓存): {l} → {e}")
    if len(failed) > 10:
        log(f"  ... 另有 {len(failed) - 10} 个失败")

    rc = 1 if (failed or changed) else 0
    log(f"\nexit code : {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
