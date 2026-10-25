#!/usr/bin/env python3
"""
inexbot KB 状态探针 —— 回答三个问题：

1. 索引本身是否健康？      → 条目数 / md 与 raw 文件对账 / 孤儿文件 / 缺失文件
2. 相对上次爬取是否变了？  → index.json 字节级 diff（快照存 .crawl_state.json）
3. 上游站点是否变了？      → 抽样重新抓取并做「内容级」比对（增量爬虫的盲区）

第 3 点是本探针存在的理由：crawler.py 默认是增量的（raw/ 和 md/ 已存在就跳过），
所以「爬取成功 558/558」并不代表上游没变 —— 页面正文被改也会全部显示「跳过（已存在）」。
只有重新抓取才能发现上游漂移。

用法：
    python3 check_crawl_state.py            # 全量检查 + 抽样 25 页漂移检测
    python3 check_crawl_state.py --quick    # 只查索引健康度，不做网络抽样
    python3 check_crawl_state.py --sample 60

输出 verdict：
    IDENTICAL            索引与上次逐字节相同，且抽样未发现上游漂移
    CONTENT-DRIFT        索引逐字节相同，但上游抽样发现正文变了 → 需要 --force 重爬
    CHANGED: N -> M      索引条目数变了
    NO-SNAPSHOT          首次运行，已写入基线
    HEALTHY              索引变了但上游抽样无漂移（正常的内容更新）
退出码：0 = 正常，1 = 存在需要 --force 重爬的内容漂移
"""
import json, re, sys, hashlib, random, datetime
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor

KB_ROOT = Path.home() / ".hermes" / "kb" / "inexbot"
INDEX_F = KB_ROOT / "index.json"
MD_DIR = KB_ROOT / "md"
RAW_DIR = KB_ROOT / "raw"
SNAPSHOT_F = KB_ROOT / ".crawl_state.json"

BASE_URL = "https://doc.inexbot.com"
ZWSP = "​"

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import crawler as C
except Exception:
    C = None  # 抽样检测不可用时降级为只做索引健康检查

# ── 参数 ──────────────────────────────────────────────────────────────────────
QUICK = "--quick" in sys.argv
SAMPLE = 25
for i, a in enumerate(sys.argv):
    if a == "--sample" and i + 1 < len(sys.argv):
        SAMPLE = int(sys.argv[i + 1])


def slugify(text: str, max_len: int = 200) -> str:
    """与 crawler.slugify 保持一致（含 unquote + 字节截断 + MD5 后缀）。"""
    from urllib.parse import unquote
    text = unquote(text)
    text = text.strip().replace("/", "-").replace("\\", "-")
    text = re.sub(r'[<>:"|?*]', "", text)
    if len(text.encode("utf-8")) > max_len:
        head = text.encode("utf-8")[: max_len - 16].decode("utf-8", errors="ignore")
        text = head + "-" + hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    return text


def build_md(d: dict) -> str:
    """复刻 crawler.py 写 md 文件的格式，用于内容级比对。"""
    s = f"# {d['title']}\n\n"
    if d["description"]:
        s += f">{d['description']}\n\n"
    s += d["content_md"]
    return s.strip()


# ── 1. 索引健康度 ────────────────────────────────────────────────────────────
def check_health():
    idx = json.loads(INDEX_F.read_text(encoding="utf-8"))
    mds = list(MD_DIR.glob("*.md"))
    raws = list(RAW_DIR.glob("*.html")) if RAW_DIR.exists() else []

    slugs = set()
    missing = []
    for k in idx:
        s = slugify(k.lstrip("/").rstrip(".html"))
        slugs.add(s)
        if not (MD_DIR / f"{s}.md").exists():
            missing.append(k)

    orphans = [p.name for p in mds if p.stem not in slugs]

    short = sum(1 for v in idx.values() if len(v.get("content_snippet") or "") < 60)
    empty_title = sum(1 for v in idx.values() if not (v.get("title") or "").strip())
    zwsp = sum(1 for v in idx.values()
               if ZWSP in (v.get("title") or "") or ZWSP in (v.get("description") or ""))

    print(f"index.json : {len(idx)} entries, {INDEX_F.stat().st_size:,} bytes, "
          f"sha={hashlib.sha256(INDEX_F.read_bytes()).hexdigest()[:16]}")
    print(f"md/ files  : {len(mds)}   raw/ files: {len(raws)}")
    print(f"missing md : {len(missing)}   orphan md: {len(orphans)}")
    print(f"snippet<60ch: {short}   empty titles: {empty_title}   ZWSP in title/desc: {zwsp}")
    for k in missing[:5]:
        print(f"   MISSING: {k}")
    for o in orphans[:5]:
        print(f"   ORPHAN : {o}")

    healthy = not missing and not orphans and len(idx) > 0
    print(f"health     : {'OK' if healthy else 'PROBLEM'}")
    return idx, healthy, len(missing) + len(orphans)


# ── 2. 上游漂移检测（内容级） ────────────────────────────────────────────────
def check_drift(idx, sample_size):
    if C is None:
        print("\ndrift      : SKIPPED (无法导入 crawler 模块)")
        return None

    keys = list(idx.keys())
    if not keys:
        return None
    random.seed()
    sample = random.sample(keys, min(sample_size, len(keys)))

    import httpx
    headers = {"User-Agent": "Mozilla/5.0 (compatible; HermesKB/1.0)"}

    def one(k):
        url = urljoin(BASE_URL, k)
        s = slugify(k.lstrip("/").rstrip(".html"))
        md_p = MD_DIR / f"{s}.md"
        try:
            with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as cl:
                r = cl.get(url)
            if r.status_code != 200:
                return k, f"HTTP{r.status_code}", None
            d = C.extract_content(r.text, url)
            new_md = build_md(d)
            old_md = md_p.read_text(encoding="utf-8").strip() if md_p.exists() else ""
            if new_md == old_md:
                return k, "SAME", None
            # 只改了图片 URL（VitePress 资源 hash 重命名）不算正文变更
            strip_img = lambda t: re.sub(r"!\[[^\]]*\]\([^)]*\)", "![IMG]", t)
            if strip_img(new_md) == strip_img(old_md):
                return k, "IMG_ONLY", None
            return k, "CONTENT", (k, old_md, new_md)
        except Exception as e:
            return k, f"ERR:{type(e).__name__}", None

    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for res in ex.map(one, sample):
            results.append(res)

    from collections import Counter
    cnt = Counter(r[1] for r in results)
    real = [r for r in results if r[1] == "CONTENT"]
    print(f"\ndrift      : 抽样 {len(results)} 页 → {dict(cnt)}")
    for r in real[:5]:
        k, old_md, new_md = r[2]
        print(f"   CONTENT CHANGED: {k}")
        import difflib
        dl = list(difflib.unified_diff(old_md.splitlines(), new_md.splitlines(),
                                       lineterm="", n=1))
        for line in dl[:12]:
            print(f"      {line[:160]}")
    return len(real)


# ── 主流程 ───────────────────────────────────────────────────────────────────
def main():
    print("=" * 66)
    print(f"inexbot KB state probe — {datetime.datetime.now().isoformat(timespec='seconds')}")
    print("=" * 66)

    idx, healthy, problems = check_health()

    drift = None
    if not QUICK:
        drift = check_drift(idx, SAMPLE)
    else:
        print("\ndrift      : SKIPPED (--quick)")

    cur = {
        "entries": len(idx),
        "bytes": INDEX_F.stat().st_size,
        "sha256": hashlib.sha256(INDEX_F.read_bytes()).hexdigest(),
        "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    prev = None
    if SNAPSHOT_F.exists():
        try:
            prev = json.loads(SNAPSHOT_F.read_text(encoding="utf-8"))
        except Exception:
            prev = None

    if prev is None:
        verdict = "NO-SNAPSHOT (已写入基线，下次运行即可做字节级 diff)"
    elif prev.get("entries") != cur["entries"]:
        verdict = f"CHANGED: {prev['entries']} -> {cur['entries']} docs"
    elif prev.get("sha256") != cur["sha256"]:
        verdict = "HEALTHY (index.json 字节变化，但条目数不变 — 上游正文有更新)"
    elif drift:
        verdict = f"CONTENT-DRIFT (索引逐字节相同，但抽样 {drift} 页上游正文已变 → 建议 --force 重爬)"
    else:
        verdict = "IDENTICAL (索引与上次逐字节相同，抽样未发现上游漂移)"

    print(f"\nverdict    : {verdict}")

    SNAPSHOT_F.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"snapshot   : {SNAPSHOT_F}")

    rc = 0
    if problems:
        rc = 1
    if verdict.startswith("CONTENT-DRIFT"):
        rc = 1
    print(f"exit code  : {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
