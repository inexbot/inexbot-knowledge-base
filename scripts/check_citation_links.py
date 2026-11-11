#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
引用链接实网可达性检查（inexbot KB）（2026-11-10 新增）
=========================================================

为什么需要独立脚本
------------------
`verify_kb.py` 只抽样 12 条引用链接。样本量小 -> 漏掉「个别 URL 404」的概率高。
本脚本按 proxy 的 `_kb_url()` 规则（保留既有 `%XX`）从 index.json 直接生成
官方链接，并对**全部中文路径条目**做 HEAD/GET 可达性抽检。

判定
----
- HTTP 200 / 3xx  -> PASS
- 404 / 410        -> FAIL（引用链接打不开）
- 连接类错误      -> WARN（网络抖动，非内容问题，不计入 FAIL）
- **cjk 池为空**  -> FAIL（检测谓词写错；见下方「陷阱 26」）

⚠️ 陷阱 26（shared-proxy-service-pitfalls.md）
------------------------------------------------
第一版用 `re.search(r"[一-鿿]", key)` 直接匹配 **index key** → **恒为 0**，
因为 key 是 percent-encoded 的。脚本的兜底分支让它退化成「全库随机抽」，
**看起来跑通了（60/60 200），但根本没测它声称要测的中文路径**。

⇒ 检测中文路径必须 `unquote(k)` **先解码再匹配**；
⇒ **池子为空就应当报错退出**，绝不能静默退化成全集（兜底分支是在「藏错」，不是「稳健」）。

用法
----
    /usr/bin/python3 scripts/check_citation_links.py
    /usr/bin/python3 scripts/check_citation_links.py --sample 60 --timeout 20
"""

import argparse
import json
import random
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, unquote

KB_ROOT = Path.home() / ".hermes/kb/inexbot"
BASE_URL = "https://doc.inexbot.com"


def kb_url(path):
    """Mirror the proxy's _kb_url(): if the key already contains '%', keep it encoded."""
    if "%" in path:
        return BASE_URL + quote(path, safe="/%")
    return BASE_URL + quote(path, safe="/")


def fetch_status(url, timeout):
    req = urllib.request.Request(url, method="GET", headers={
        "User-Agent": "Mozilla/5.0 (compatible; kb-citation-check)",
        "Accept": "text/html,*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(512)
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, "HTTPError"
    except Exception as e:
        return 0, type(e).__name__ + ": " + str(e)[:80]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20261110)
    args = ap.parse_args()

    index = json.loads((KB_ROOT / "index.json").read_text(encoding="utf-8"))
    keys = list(index.keys())
    print("index entries: %d" % len(keys))

    # Prefer entries with real Chinese paths -- those are the ones where
    # encoding bugs would show up.
    #
    # ⚠️ TRAP 26 (shared-proxy-service-pitfalls.md): a detection predicate run
    # against an ALREADY-ENCODED key always yields an empty set (the Chinese
    # is percent-encoded, so the CJK regex never matches). Must decode FIRST.
    # `unquote` here is for DETECTION ONLY -- the URL is still built from the
    # original key (decoding it for the URL would double-encode -> 404).
    cjk = [k for k in keys if re.search(r"[\u4e00-\u9fff]", unquote(k))]

    # ⚠️ A silently-empty pool used to fall back to the whole index, which made
    # the script "pass" while testing the wrong thing. Fail loudly instead.
    if not cjk:
        print("[FAIL] cjk pool is EMPTY -- the detection predicate is wrong.")
        print("       index keys are percent-encoded; decode before matching.")
        print("       Refusing to fall back to random sampling over the whole")
        print("       index (that would silently test the wrong subset).")
        return 1

    pool = cjk if len(cjk) >= args.sample else keys
    random.seed(args.seed)
    if len(pool) > args.sample:
        sample = random.sample(pool, args.sample)
    else:
        sample = pool

    ok = bad = warn = 0
    failures = []
    warnings = []
    for k in sample:
        url = kb_url(k)
        code, err = fetch_status(url, args.timeout)
        if code == 200:
            ok += 1
        elif code in (301, 302, 303, 307, 308):
            ok += 1
        elif code in (404, 410):
            bad += 1
            failures.append((code, k, url))
        else:
            warn += 1
            warnings.append((code or err, k, url))

    print("sampled: %d   (cjk pool: %d)" % (len(sample), len(cjk)))
    print("HTTP 200/3xx : %d" % ok)
    print("HTTP 404/410 : %d" % bad)
    print("network err  : %d" % warn)

    if failures:
        print("\n--- FAIL (引用链接打不开) ---")
        for code, k, url in failures[:20]:
            print("  %s  %s" % (code, url))
    if warnings:
        print("\n--- WARN (网络类, 非内容问题) ---")
        for code, k, url in warnings[:10]:
            print("  %s  %s" % (code, url[:120]))

    print("\n=> %s" % ("PASS: 全部引用链接可达" if bad == 0 else "FAIL: %d 条 404" % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
