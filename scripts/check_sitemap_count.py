#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上游 sitemap 条目数对账 —— **独立于本地缓存**的漂移判据。

2026-11-11 新增。

为什么需要它
------------
`check_crawl_state.py` 的 drift 判定是「本地 raw 缓存 vs 上游重抓」的对比，
**隐含假设「本地缓存本身是可信基线」**。若本地缓存整体过期（例如上游整站重写），
逐字节 diff 可能给出「IDENTICAL」的假象。

直接数**上游 sitemap 里的 zh `<loc>` 条目数**，是不依赖任何本地缓存的第三方证据：
  本地 index 条目数 == 上游 sitemap zh 条目数  =>  上游既无新增、也无下线。

用法
----
    /usr/bin/python3 scripts/check_sitemap_count.py
    /usr/bin/python3 scripts/check_sitemap_count.py --kb inexbot-open

退出码
------
    0 = 一致（或上游条目数 > 本地，提示有新页面待抓）
    1 = 本地条目数 > 上游 sitemap 条目数（上游有页面下线 / 本地有幽灵条目）
    2 = 网络错误 / 解析失败

⚠️ 必须用 /usr/bin/python3（沙盒 python3 未必有 requests）。
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = {
    "inexbot": ("https://doc.inexbot.com", "https://doc.inexbot.com/sitemap.xml"),
    "inexbot-open": ("https://open.inexbot.com", "https://open.inexbot.com/sitemap.xml"),
}

# zh 路径的判定：KB 名后跟 /zh/ （doc.inexbot.com 的 zh 路由）
ZH_RE = re.compile(r"/zh/")


def fetch(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-kb-crawler/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", default="inexbot", choices=sorted(BASE))
    ap.add_argument("--timeout", type=int, default=45)
    args = ap.parse_args()

    base, sitemap_url = BASE[args.kb]

    try:
        xml = fetch(sitemap_url, timeout=args.timeout)
    except Exception as e:
        print("[FAIL] 无法获取 %s: %s: %s" % (sitemap_url, type(e).__name__, e))
        return 2

    locs = re.findall(r"<loc>([^<]+)</loc>", xml)
    zh = [u for u in locs if ZH_RE.search(u)]
    zh_unique = sorted(set(zh))

    idx_path = Path.home() / ".hermes/kb" / args.kb / "index.json"
    try:
        disk = json.loads(idx_path.read_text(encoding="utf-8"))
    except Exception as e:
        print("[FAIL] 无法读取 %s: %s" % (idx_path, e))
        return 2

    n_disk = len(disk)

    print("=" * 62)
    print("上游 sitemap 对账 -- %s" % args.kb)
    print("=" * 62)
    print("sitemap url       : %s" % sitemap_url)
    print("total <loc>       : %d" % len(locs))
    print("zh <loc>          : %d" % len(zh))
    print("zh unique        : %d" % len(zh_unique))
    print("local index       : %d" % n_disk)

    # 本地 index 的 key 形态与上游 URL 形态不同（可能 percent-encoded），
    # 所以这里只比「数量」，不做逐条比对 —— 逐条比对交给 check_citation_links.py。
    if n_disk == len(zh_unique):
        print("\n=> PASS: 上游 zh 页面数与本地 index 条目数一致 (%d)" % n_disk)
        return 0

    if n_disk > len(zh_unique):
        print("\n=> FAIL: 本地 %d 条 > 上游 %d 条 —— 上游有页面下线或本地有幽灵条目。"
              % (n_disk, len(zh_unique)))
        print("   对策: 跑 scripts/refresh_drift.py 清孤儿（crawler.py 不会清）。")
        return 1

    print("\n=> NOTE: 本地 %d 条 < 上游 %d 条 —— 上游新增了 %d 页，本轮应重爬。"
          % (n_disk, len(zh_unique), len(zh_unique) - n_disk))
    print("   对策: 跑 scripts/crawler.py --force（或 refresh_drift.py）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
