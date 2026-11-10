#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检索链路审计（proxy 侧）—— 判「真静默降级」的正确口径（2026-11-10 新增）
=====================================================================

为什么需要这个脚本
------------------
`verify_kb.py` 的 "短 snippet" 只是**粗筛**（长度 < 800），会把两类东西混在一起：

| 现象 | 真实含义 | 是否 BUG |
|---|---|---|
| index 里 `content_snippet == 800` | `crawler.py` **按设计**截到 800 的摘要窗口 | 否，正常 |
| **proxy 返回的 snippet == 800** | proxy 回落到了 index 摘要（没找到 md） | **是，静默降级** |

=> 判「静默降级」**必须看 proxy 侧的返回**，且长度必须是**字符数**不是字节数
   （中文 1 字 = 3 字节，比字节会误判）。

本脚本的口径（与 skill 正文一致）
----------------------------------
| 判据 | 含义 |
|---|---|
| proxy snippet 字符数 == 800 | **真静默降级** |
| proxy snippet 字符数 == md 字符数 | 全文命中 |
| proxy snippet 字符数 < md 字符数 | 命中 4000 字符上限（设计如此） |

url -> index key 的归一化（**只**替换 %26 / %2B，整体 unquote() 是错的）
--------------------------------------------------------------------
`index.json` 的 key 是**混合编码态**：中文 percent-encoded，`&` 和 `+` 是字面量；
而 proxy 返回的 url 把 `&` 编成 `%26`、`+` 编成 `%2B`。
=> `key = path.replace("%26", "&").replace("%2B", "+")`
=> 整体 `unquote()` 会把中文那半边的 %XX 也解掉 -> 查表几乎全 miss -> 假报「md not found」。

用法
----
    /usr/bin/python3 scripts/check_retrieval_chain.py
    /usr/bin/python3 scripts/check_retrieval_chain.py --queries 20
    /usr/bin/python3 scripts/check_retrieval_chain.py --json
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

KB_ROOT = Path.home() / ".hermes/kb/inexbot"
MD_ROOT = KB_ROOT / "md"
PROXY_PY = Path.home() / "hermes-skill-proxy/hermes-skill-proxy.py"
BASE_URL = "https://doc.inexbot.com"

DEFAULT_QUERIES = [
    "冲压工艺 手册 参数设置",
    "示教器 操作手册",
    "通讯协议 地址码 Modbus 寄存器",
    "伺服报警 故障码 处理",
    "控制器 以太网 IP 配置",
    "输入输出 IO 端口 接线",
    "机器人 示教 编程 坐标系",
    "系统 备份 恢复 参数",
    "EtherCAT 总线 从站 诊断",
    "安全 急停 门锁 回路",
    "视觉 相机 标定 抓取",
    "焊接 工艺 参数 电流 电压",
]


def load_proxy():
    """Load the proxy module in-process (must use /usr/bin/python3 -- flask needed)."""
    spec = importlib.util.spec_from_file_location("hsp", str(PROXY_PY))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hsp"] = mod          # required: proxy module expects to be importable
    spec.loader.exec_module(mod)
    mod.load_all_indexes()            # required: otherwise _doc_scores is empty -> []
    return mod


def url_path_to_index_key(url):
    """Minimal normalization -- ONLY %26 and %2B. Never a blanket unquote()."""
    path = url.split(BASE_URL, 1)[-1] if BASE_URL in url else url
    return path.replace("%26", "&").replace("%2B", "+")


def md_char_count(mod, key):
    """Resolve an index key to its md file using the proxy's own slug candidates.

    Returns (char_count, filename) or (None, None).
    NOTE: proxy's _md_slug_candidates() returns slugs WITHOUT the .md suffix.
    """
    try:
        cands = mod._md_slug_candidates(key)
    except Exception:
        return None, None
    for slug in cands:
        p = MD_ROOT / (slug + ".md")
        try:
            if p.exists():
                return len(p.read_text(encoding="utf-8")), p.name
        except OSError:          # Errno 36: file name too long
            continue
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=int, default=12, help="how many queries to run")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    mod = load_proxy()
    queries = DEFAULT_QUERIES[: max(1, args.queries)]

    rows = []
    for q in queries:
        for r in mod.search_single_kb("inexbot", q, args.top_k):
            url = r.get("url", "")
            key = url_path_to_index_key(url)
            md_chars, fname = md_char_count(mod, key)
            rows.append({
                "query": q,
                "title": r.get("title"),
                "snip_chars": len(r.get("content_snippet") or ""),
                "md_chars": md_chars,
                "md_file": fname,
                "key": key,
                "url": url,
            })

    true_degrade = [r for r in rows if r["snip_chars"] == 800]
    full_hit = [r for r in rows if r["md_chars"] is not None and r["snip_chars"] == r["md_chars"]]
    trunc = [r for r in rows if r["md_chars"] is not None and 800 < r["snip_chars"] < r["md_chars"]]
    no_md = [r for r in rows if r["md_chars"] is None]
    short_page = [r for r in rows if r["md_chars"] is not None and r["snip_chars"] < 800]
    over = [r for r in rows if r["snip_chars"] > 4000]

    summary = {
        "total_results": len(rows),
        "true_silent_degradation": len(true_degrade),
        "full_text_hit": len(full_hit),
        "truncated_at_4000": len(trunc),
        "md_not_found": len(no_md),
        "short_page_full_hit": len(short_page),
        "over_4000": len(over),
    }

    if args.json:
        print(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2))
        return 1 if (true_degrade or no_md or over) else 0

    print("=" * 62)
    print("proxy 检索链路审计 (char-count criterion)")
    print("=" * 62)
    for k, v in summary.items():
        print("  %-28s %s" % (k, v))

    if no_md:
        print("\n--- md not found (normalize bug? check url->key rule) ---")
        for r in no_md[:15]:
            print("  snip=%-5d %-40s %s" % (r["snip_chars"], (r["title"] or "")[:40], r["key"][:90]))

    if short_page:
        print("\n--- short snippets <800 (md itself short => full hit, OK) ---")
        for r in short_page[:15]:
            print("  snip=%-4d md=%-6s %-36s %s" % (
                r["snip_chars"], r["md_chars"], (r["title"] or "")[:36], (r["md_file"] or "")[:60]))

    print("\n--- sample full-text hits ---")
    for r in full_hit[:5]:
        print("  snip=%-5d md=%-5d %s" % (r["snip_chars"], r["md_chars"], (r["title"] or "")[:50]))

    ok = not (true_degrade or no_md or over)
    print("\n=> %s" % ("PASS: 无真静默降级, md 全部可定位" if ok
                      else "FAIL: 见上方明细"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
