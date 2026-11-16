#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
token 级「proxy 内存索引 vs 磁盘 index.json」一致性检查。

⚠️ 三个必须同时守住的点（错了就是全量假阳性）：
  1. 内存侧用 `_doc_scores[kb]`（分词后的 token 集合），
     **不是** `_index_data[kb]`（原始 dict，字段是字符串）—— 用错必报「全量不一致」
  2. 磁盘侧字段名是 `title` / `description` / `content_snippet`
     （**不是** `desc` / `content`）—— 取错名 -> 磁盘侧切成空 token 集 -> 全量假阳性
  3. 两边必须用**同一套 jieba 规则**（`len(w) >= 2`）
  4. 必须先 `mod.load_all_indexes()`，否则 `_doc_scores` 为空

「差异数整齐地等于条目数」= 字段名/结构取错的指纹。

退出码：0 = 一致；1 = 不一致（内存索引过期）。
"""

import importlib.util
import json
import sys
from pathlib import Path

import jieba

PROXY = Path.home() / "hermes-skill-proxy/hermes-skill-proxy.py"
KB_ROOT = Path.home() / ".hermes/kb"


def toks(s):
    """与 proxy 的切词规则保持一致。"""
    return {w for w in jieba.cut(s or "") if len(w) >= 2}


def check(kb, disk_dir):
    spec = importlib.util.spec_from_file_location("hsp", str(PROXY))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hsp"] = mod
    spec.loader.exec_module(mod)
    mod.load_all_indexes()          # 必须调用，否则 _doc_scores 为空

    disk = json.loads((disk_dir / "index.json").read_text(encoding="utf-8"))
    mem = mod._doc_scores[kb]       # token 化后的内存索引

    dk, mk = set(disk), set(mem)
    print("=" * 62)
    print("token 级一致性: %s" % kb)
    print("=" * 62)
    print("  磁盘条目数   : %d" % len(dk))
    print("  内存条目数   : %d" % len(mk))
    print("  key 集合相同 : %s" % (dk == mk))
    if dk != mk:
        print("    仅磁盘有   : %d" % len(dk - mk))
        print("    仅内存有   : %d" % len(mk - dk))

    bad = 0
    for k in dk.intersection(mk):
        d, m = disk[k], mem[k]
        if (toks(d.get("title", "")) != m["title_tokens"]
                or toks(d.get("description", "")) != m["desc_tokens"]
                or toks(d.get("content_snippet", "")) != m["content_tokens"]):
            bad += 1
    print("  token 级不一致 : %d" % bad)

    if bad and bad == len(dk.intersection(mk)):
        print("\n  [!] 差异数整齐地等于条目数 -> 疑似字段名/结构取错（陷阱 18），不是数据损坏。")
    return bad, len(dk.intersection(mk))


def main():
    rc = 0
    for kb, dirname in (("inexbot", "inexbot"), ("inexbot-open", "inexbot-open")):
        d = KB_ROOT / dirname
        if not (d / "index.json").exists():
            print("skip %s (no index.json)" % kb)
            continue
        bad, total = check(kb, d)
        if bad:
            rc = 1
        print()
    print("=> PASS: 两个 KB 的内存索引与磁盘 index.json 逐条一致。" if rc == 0
          else "=> FAIL: 存在 token 级不一致，内存索引可能过期。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
