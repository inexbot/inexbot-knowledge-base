#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""结构自检：共享 pitfalls 文件有没有「重复块 / 孤儿块 / 标题截断」。

背景（2026-11-13 实测，见 shared-proxy-service-pitfalls.md §陷阱 31）：
两个 KB 的 agent 同时 patch 同一个共享文件时，可能拼出
  - 孤儿块：有完整正文，但没有自己的 `## 陷阱 N：` 标题（标题被吞）
  - 重复块：同一段正文出现两次（一次在正常 section 里，一次在文件末尾）
  - 标题截断：`## 陷阱 N` 存在但切不出对应正文

这类损坏**两个 KB 都看得见**，且**sha1 两边一致**（同一个 commit 推过去的）
⇒ 只靠 `diff_shared_pitfalls.py`（比内容）**抓不到** —— 必须单独做结构检查。

用法：
    /usr/bin/python3 scripts/check_shared_pitfalls_structure.py
    /usr/bin/python3 scripts/check_shared_pitfalls_structure.py --file <path>

退出码：
    0 = 结构完好
    1 = 发现重复块 / 孤儿块 / 标题截断
    2 = 文件不存在

⚠️ 必须用 /usr/bin/python3（cron 禁内联脚本，见 §陷阱 29）。
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

DEFAULT_FILES = [
    Path.home() / ".hermes/skills/productivity/inexbot-open-knowledge-base/references/shared-proxy-service-pitfalls.md",
    Path.home() / ".hermes/skills/productivity/inexbot-knowledge-base/references/shared-proxy-service-pitfalls.md",
]

SECTION_RE = re.compile(r"^##\s+(陷阱\s+\d+[^\n]*)$")
SUBHEAD_RE = re.compile(r"^###\s+")
# 门槛：短于这个长度的重复行多半是表格分隔线 / 装饰线，不算重复块
MIN_LINE_LEN = 40


def analyze(text):
    lines = text.splitlines()
    headings = []
    for i, ln in enumerate(lines):
        m = SECTION_RE.match(ln)
        if m:
            headings.append((i, m.group(1).strip()))

    problems = []

    # --- 1) 重复行（正文被复制成两段） ---
    seen = {}
    for i, ln in enumerate(lines):
        s = ln.strip()
        if len(s) < MIN_LINE_LEN:
            continue
        if s.startswith("|") or s.startswith("#"):
            # 表格行 / 标题行：只有当它不是标题且足够长才算可疑
            if s.startswith("#"):
                continue
        seen.setdefault(s, []).append(i + 1)
    for s, positions in seen.items():
        if len(positions) > 1:
            problems.append(
                ("DUPLICATE_LINE", f"line {s[:60]!r} appears at lines {positions}")
            )

    # --- 2) 标题截断：最后一个标题之后没有正文 ---
    if headings:
        last_idx, last_title = headings[-1]
        tail = [ln for ln in lines[last_idx + 1:] if ln.strip()]
        if not tail:
            problems.append(("EMPTY_SECTION", f"last section {last_title!r} has no body"))
        # 最后一个 section 的正文应该直到文件尾
    else:
        problems.append(("NO_SECTIONS", "no '## 陷阱 N' headings found at all"))

    # --- 3) 子标题多于 section 数 -> 可能有孤儿块 ---
    n_sub = sum(1 for ln in lines if SUBHEAD_RE.match(ln))
    if headings and n_sub > len(headings) * 3:
        problems.append(
            ("SUSPECT_ORPHAN", f"{n_sub} sub-headings vs {len(headings)} sections -- check for a body without its own heading")
        )

    # --- 4) 正文块 hash 重复（整段被复制） ---
    block_hashes = {}
    for k, (start, title) in enumerate(headings):
        end = headings[k + 1][0] if k + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start:end])
        h = hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]
        block_hashes.setdefault(h, []).append(title)

    return problems, len(headings), n_sub, lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", help="path to check (repeatable)")
    args = ap.parse_args()

    files = [Path(f) for f in args.file] if args.file else DEFAULT_FILES
    rc = 0
    for f in files:
        print(f"=== {f} ===")
        if not f.exists():
            print(f"  [FAIL] file not found")
            rc = 2
            continue
        text = f.read_text(encoding="utf-8")
        problems, n_sec, n_sub, lines = analyze(text)
        print(f"  sections={n_sec}  sub-headings={n_sub}  lines={len(lines)}")
        if not problems:
            print("  [OK] structure intact: no duplicate/orphan/truncated sections")
            continue
        rc = 1
        for kind, detail in problems:
            print(f"  [{kind}] {detail}")
        # 打印重复正文块的标题，供人工核对
        heads = [SECTION_RE.match(ln).group(1).strip()
                 for ln in lines if SECTION_RE.match(ln)]
        print(f"  section titles: {heads}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
