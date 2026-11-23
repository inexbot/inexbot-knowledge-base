#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上游「URL 形态」三形态探测（裸 / +.html / +/index.html）。

背景（见 shared-proxy-service-pitfalls.md §陷阱 39 / §陷阱 43）：
上游 doc.inexbot.com 的 URL 路由形态会**反复漂移**（一周内切过两次且方向相反）：

    | 日期     | 裸路径 | .html 后缀 | 目录页 /index.html | 判定        |
    |----------|--------|------------|--------------------|-------------|
    | 2026-11-19 | 404  | 200        | 200                | 只认后缀     |
    | 2026-11-21 | 200  | 200        | 200                | 两套并存     |
    | 2026-11-22 | 200  | 200        | 200                | 两套并存     |

⇒ 每轮 cron 都要跑一次本探针，判断「上游当前是哪种形态」。
⇒ **处置原则**：
    - 形态**收紧**（裸路径全 404）⇒ 必须按 KB 分派做全套修复（见 upstream-url-suffix-routing.md）
    - 形态**放宽**（两套并存）⇒ **不改代码** —— 保留 url_suffix 兼容层，
      它在两种路由下都可达，零成本更稳。**绝不**因为「裸形态现在能用」就删兼容层。

用法：
    /usr/bin/python3 scripts/check_url_forms.py
    /usr/bin/python3 scripts/check_url_forms.py --sample 40
    /usr/bin/python3 scripts/check_url_forms.py --kb inexbot          # 只探本库
    /usr/bin/python3 scripts/check_url_forms.py --kb inexbot-open

退出码：
    0 = 探针完成（结果看输出里的 VERDICT 行）
    1 = 探针自身出错（例如 index.json 读不到）

⚠️ 必须用 /usr/bin/python3（cron 禁内联脚本，见 §陷阱 29）。

⚠️⚠️ 本脚本已经内建修复了两个 2026-11-22 实测踩到的**探针自伤**坑
    （= 陷阱 26「谓词作用在已编码字符串上」的变体）：

  坑 A：**用 `"%" in key` 筛「中文路径池」**
      对 `inexbot` 成立（key 是 percent-encoded），
      但对 `inexbot-open` **恒为 0 条**（它的 key 是**明文中文**）
      ⇒ 会输出「sampled: 0」，被误读成「姊妹 KB 整个挂了」。
      ⇒ 本脚本改为：**先判该 KB 的 key 编码态，再选池子**（见 pick_pool）。

  坑 B：**明文中文路径直接交给 urllib**
      urllib 不会自动 percent-encode → 抛 URLError → 本脚本记为 -1
      ⇒ 输出「10/15 failures」，被误读成「姊妹 KB 大批链接失效」。
      ⇒ 本脚本改为：**明文 key 先 quote()，已编码 key 保留 %XX**（见 build_url）。
"""

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, unquote

TIMEOUT = 20
UA = {"User-Agent": "Mozilla/5.0 (KB-cron-url-form-probe)"}

KBS = {
    "inexbot": {
        "base": "https://doc.inexbot.com",
        "index": Path.home() / ".hermes/kb/inexbot/index.json",
    },
    "inexbot-open": {
        "base": "https://open.inexbot.com",
        "index": Path.home() / ".hermes/kb/inexbot-open/index.json",
    },
}


def http_status(url):
    """返回 (status, note)。status: 2xx/3xx=ok, 4xx/5xx=具体码, -1=网络错误。"""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return -1, type(e).__name__


def pick_pool(keys):
    """按该 KB 的 key 编码态挑「中文路径池」—— 坑 A 的修复。

    判据（等价于 proxy 的 _kb_url()）：key 里有没有 '%'。
      - 有 '%'  ⇒ key 已 percent-encoded ⇒ unquote 之后才看得到 CJK
      - 无 '%'  ⇒ key 是明文中文        ⇒ unquote 之后同样看得到 CJK
    ⇒ 两种形态**统一**用 unquote 后再检测（与 §陷阱 26 的修法一致）。
    """
    cjk = []
    for k in keys:
        probe = unquote(k)
        if any("一" <= ch <= "鿿" for ch in probe):
            cjk.append(k)
    return cjk


def build_url(base, key):
    """构造 URL —— 坑 B 的修复。

    key 已 percent-encoded（inexbot）⇒ 保留既有 %XX，只编码其余字符
    key 是明文中文（inexbot-open）⇒ 整体编码
    """
    if "%" in key:
        return base + quote(key, safe="/%")
    return base + quote(key, safe="/")


def probe_kb(name, cfg, sample_n, seed):
    idx_path = Path(cfg["index"])
    if not idx_path.exists():
        print("=== %s ===" % name)
        print("  [SKIP] index.json 不存在: %s" % idx_path)
        return None

    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    items = list(idx.items())
    base = cfg["base"]

    print("=" * 72)
    print("KB: %s   entries=%d   base=%s" % (name, len(items), base))
    print("=" * 72)

    # url_suffix 分布（inexbot 有；inexbot-open 没有这个字段）
    dist = {}
    for _k, v in items:
        s = v.get("url_suffix", "(none)")
        dist[s] = dist.get(s, 0) + 1
    print("url_suffix 分布: %s" % dist)

    keys = [k for k, _v in items]
    pool = pick_pool(keys)
    print("中文路径池: %d / %d" % (len(pool), len(keys)))

    if not pool:
        # 池子为空 ⇒ 探针自错的强信号（坑 A 的残留）。不要静默退化。
        print("  [FAIL] 中文路径池为空 —— 这是**探针自己的问题**，不是 KB 故障。")
        print("         坑 A 复现：用 '\"%%\" in key' 筛池对明文中文 key 的 KB 恒为 0。")
        return {"name": name, "verdict": "PROBE_BUG_EMPTY_POOL", "forms": {}}

    rnd = random.Random(seed)
    by_key = dict(items)
    picked_keys = rnd.sample(pool, min(sample_n, len(pool)))

    # 目录页强制并入样本（随机几乎抽不到，而它们恰是最易写错的那一类）
    forced = 0
    for k, v in items:
        if v.get("url_suffix") == "/index.html":
            if k not in picked_keys:
                picked_keys.append(k)
                forced += 1
    print("抽样: %d 条（随机 %d + 强制并入目录页 %d）" % (len(picked_keys), sample_n, forced))

    forms = {"bare": 0, "html": 0, "indexhtml": 0}
    net_err = 0
    hard_fail = []
    for k in picked_keys:
        v = by_key.get(k, {})
        bare = build_url(base, k)
        suffix = v.get("url_suffix", "")
        if suffix == "/index.html":
            variants = [("bare", bare), ("indexhtml", bare.rstrip("/") + "/index.html")]
        elif suffix == ".html":
            variants = [("bare", bare), ("html", bare + ".html")]
        else:
            # 无 url_suffix（inexbot-open）⇒ 只探裸形态，另加一个 .html 作对照
            variants = [("bare", bare), ("html", bare + ".html")]

        for tag, url in variants:
            st, note = http_status(url)
            if st == -1:
                net_err += 1
                hard_fail.append((tag, "NETWORK_ERR(%s)" % note, k))
                continue
            if 200 <= st < 400:
                forms[tag] = forms.get(tag, 0) + 1
            else:
                hard_fail.append((tag, str(st), k))

    print()
    for tag in ("bare", "html", "indexhtml"):
        if tag in forms:
            print("  %-10s 200/3xx: %d" % (tag, forms[tag]))
    print("  硬失败: %d    网络错误: %d" % (len(hard_fail), net_err))
    for tag, st, k in hard_fail[:8]:
        print("    FAIL %-10s %-20s key=%s" % (tag, st, k[:90]))

    # ---- 判定（对应陷阱 43 的三档表）----
    bare_ok = forms.get("bare", 0) > 0
    sfx_ok = forms.get("html", 0) + forms.get("indexhtml", 0) > 0
    if bare_ok and sfx_ok:
        verdict = "DUAL（两套并存）⇒ 不改代码，保留 url_suffix 兼容层"
    elif (not bare_ok) and sfx_ok:
        verdict = "SUFFIX_ONLY（只认后缀）⇒ 上游收紧，必须按 KB 分派做全套修复"
    elif bare_ok and (not sfx_ok):
        verdict = "BARE_ONLY（只认裸路径）⇒ 上游再次改形态，需重新评估兼容层"
    else:
        verdict = "UNKNOWN（全挂或探针自错）⇒ 先怀疑探针，再怀疑上游"

    print()
    print("  VERDICT: %s" % verdict)
    return {"name": name, "verdict": verdict, "forms": forms,
            "hard_fail": len(hard_fail), "net_err": net_err}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=30, help="每个 KB 随机抽样条数")
    ap.add_argument("--kb", action="append", choices=sorted(KBS), help="只探指定 KB（可重复）")
    ap.add_argument("--seed", type=int, default=20261122)
    args = ap.parse_args()

    targets = args.kb if args.kb else sorted(KBS)
    results = []
    for name in targets:
        r = probe_kb(name, KBS[name], args.sample, args.seed)
        if r:
            results.append(r)
        print()

    print("=" * 72)
    print("SUMMARY")
    for r in results:
        print("  %-14s %s" % (r["name"], r["verdict"]))
    print("=" * 72)
    print("处置原则：形态收紧 ⇒ 全套修复（按 KB 分派）；形态放宽 ⇒ 不改代码。")
    print("⚠️ 绝不因「裸形态现在能用」就删掉 url_suffix 兼容层（上游形态反复漂移）。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover
        print("PROBE ERROR: %r" % (exc,), file=sys.stderr)
        sys.exit(1)
