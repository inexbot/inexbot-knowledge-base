#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""结构自检：共享 pitfalls 文件有没有「重复块 / 孤儿块 / 标题截断 / 正文交错」。

背景（2026-11-13 实测，见 shared-proxy-service-pitfalls.md §陷阱 31）：
两个 KB 的 agent 同时 patch 同一个共享文件时，可能拼出
  - 孤儿块：有完整正文，但没有自己的 `## 陷阱 N：` 标题（标题被吞）
  - 重复块：同一段正文出现两次（一次在正常 section 里，一次在文件末尾）
  - 标题截断：`## 陷阱 N` 存在但切不出对应正文
  - 正文交错：两节的正文逐行交错（2026-11-20 实测，姊妹 KB 那份文件出现过）

这类损坏**两个 KB 都看得见**，且**sha1 两边一致**（同一个 commit 推过去的）
⇒ 只靠 `diff_shared_pitfalls.py`（比内容）**抓不到** —— 必须单独做结构检查。

用法：
    /usr/bin/python3 scripts/check_shared_pitfalls_structure.py
    /usr/bin/python3 scripts/check_shared_pitfalls_structure.py --file <path>

退出码：
    0 = 结构完好
    1 = 发现重复块 / 孤儿块 / 标题截断 / 正文交错
    2 = 文件不存在

⚠️ 必须用 /usr/bin/python3（cron 禁内联脚本，见 §陷阱 29）。

⚠️ **2026-11-25 实测重写（旧版恒定误报 exit 1）**：
旧实现只做「按行去重」，把**两类完全正常的重复**也报成损坏：
  ① **围栏代码块里的命令行**（如 `git merge-base --is-ancestor …`）——
     同一命令在多个陷阱里各出现一次是**正确**的；
  ② **跨节引用的归属注记**（如「本条由姊妹 KB 在 X 日实测并写入…」）——
     有意在两个陷阱里各留一份，是**正确**的。
⇒ 旧实现**从未真正实现它承诺的「重复块」检测**：
   `block_hashes` 算出来了但**从未被使用**（= §陷阱 40「定义了但没接进调用链」）。
⇒ 本版改为**直接对准真正的损坏形态**：
   1. `DUPLICATE_HEADING`  同一个 `## 陷阱 N` 出现两次
   2. `DUPLICATE_SECTION`  两节的正文**整体相同**
   3. `EMPTY_SECTION`      任意一节正文过短（不只是最后一节）
   4. `INTERLEAVED_BODY`   两节正文**逐行交错**（按重叠比例判定，天然容忍
      「一两句在多节重复」的正常写法）
   5. `SUSPECT_ORPHAN`      子标题数远多于 section 数（正文有、标题丢了）
判据阈值见下方常量，均已在合成样本上实测过。

⭐ **与姊妹 KB 的版本必须保持一致**（共享脚本，§陷阱 45 的「变化行是否全部
与本次改动相关」判据）—— 两边跑的是同一个 proxy，同一个坏脚本等于没修。
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

# 判定「一节正文过短」的下限（标题行不计）
MIN_SECTION_BODY_LINES = 2
# 判定「两节正文交错」的重叠比例下限。
# 正常写法里同一句话最多在两三节重复 ⇒ 单节占比通常 < 15%；
# 真交错时两节的绝大多数行互相出现 ⇒ 占比 > 60%。
INTERLEAVE_RATIO = 0.60
# 参与重叠统计的行长度下限（过滤装饰线 / 表格分隔）
MIN_OVERLAP_LINE_LEN = 12
# 孤儿体检测用的「固定长度前缀签名」行数。
# ⚠️ 不能用「整段正文」当签名：最后一节的正文延伸到 EOF，孤块若是它的复制体
#    会被吸进自己 => 签名改变 => 反而漏报（2026-11-15 实测踩到）。
SIG_LINES = 8


def _fenced_line_mask(lines):
    """1-based line numbers that sit inside fenced code blocks.

    A fenced code block legitimately repeats the same shell command across
    different trap sections; counting those as corruption produced a
    permanently red probe (measured 2026-11-25: 5 of 7 flags were exactly this).
    """
    inside = set()
    fence = False
    for i, ln in enumerate(lines, 1):
        if ln.strip().startswith("```"):
            fence = not fence
            continue
        if fence:
            inside.add(i)
    return inside


def _norm_lines(lines, start, end, skip):
    """Normalized, de-duplicated meaningful lines of a section body."""
    out = set()
    for i in range(start, end):
        if (i + 1) in skip:
            continue
        s = " ".join(lines[i].split())
        if len(s) < MIN_OVERLAP_LINE_LEN:
            continue
        out.add(s)
    return out


def analyze(text):
    lines = text.splitlines()
    skip = _fenced_line_mask(lines)

    headings = []
    for i, ln in enumerate(lines):
        m = SECTION_RE.match(ln)
        if m:
            headings.append((i, m.group(1).strip()))

    problems = []
    n_sub = sum(1 for ln in lines if SUBHEAD_RE.match(ln))

    if not headings:
        problems.append(("NO_SECTIONS", "no '## 陷阱 N' headings found at all"))
        return problems, len(headings), n_sub, lines

    # --- 1) 标题重复 ---
    head_seen = {}
    for i, t in headings:
        head_seen.setdefault(t, []).append(i + 1)
    for t, positions in head_seen.items():
        if len(positions) > 1:
            problems.append(
                ("DUPLICATE_HEADING", f"{t!r} appears at lines {positions}")
            )

    # --- section body spans ---
    spans = []
    for k, (start, title) in enumerate(headings):
        end = headings[k + 1][0] if k + 1 < len(headings) else len(lines)
        spans.append((start, end, title))

    # 全文件的非空行序列（孤儿体签名要在它上面滑动查找）
    nonempty = [ln.strip() for ln in lines if ln.strip()]

    # --- 2) 两节正文整体相同（只比正文，不含标题行 ——
    #        标题不同正是「同一段正文被复制到两节」的标志） ---
    body_hash = {}
    for start, end, title in spans:
        body = "\n".join(lines[start + 1:end]).strip()
        if not body:
            continue
        h = hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]
        body_hash.setdefault(h, []).append(title)
    for h, titles in body_hash.items():
        if len(titles) > 1:
            problems.append(
                ("DUPLICATE_SECTION",
                 f"{len(titles)} sections share the identical body: {titles}")
            )

    # --- 3) 标题截断：任意一节正文过短 ---
    for start, end, title in spans:
        body = [ln for ln in lines[start + 1:end] if ln.strip()]
        if len(body) < MIN_SECTION_BODY_LINES:
            problems.append(
                ("EMPTY_SECTION",
                 f"section {title!r} has only {len(body)} body line(s)")
            )

    # --- 4) 正文交错：两节正文逐行交错 ---
    norm = [_norm_lines(lines, s + 1, e, skip) for s, e, _ in spans]
    for a in range(len(spans)):
        for b in range(a + 1, len(spans)):
            sa, sb = norm[a], norm[b]
            if not sa or not sb:
                continue
            inter = len(sa & sb)
            ratio = inter / min(len(sa), len(sb))
            if ratio >= INTERLEAVE_RATIO and inter >= 3:
                problems.append(
                    ("INTERLEAVED_BODY",
                     f"{spans[a][2]!r} and {spans[b][2]!r} share "
                     f"{inter} identical lines (ratio {ratio:.0%}) "
                     f"-- bodies look interleaved")
                )

    # --- 5) 孤儿块：section 数远少于子标题数 ---
    if n_sub > len(headings) * 3:
        problems.append(
            ("SUSPECT_ORPHAN",
             f"{n_sub} sub-headings vs {len(headings)} sections "
             "-- check for a body without its own heading")
        )

    # --- 6) 孤儿体：某一节的正文在文件里出现了第二份（无自己的标题） ---
    #
    # ⚠️ 这条判据**不能**被上面的 #2 (DUPLICATE_SECTION, 整段 sha256) 替代：
    # 孤儿体的典型形态是「把最后一节的正文**再抄一份**追加到文件末尾」，
    # 于是**最后一节的正文区间会同时包含原件和副本** => 它的 sha256 唯一
    # => #2 看不到重复 => 孤儿体**漏检**。
    # => 必须用「固定长度前缀签名」在全文件的非空行序列里滑动查找（§陷阱 31）。
    #
    # ⚠️ 为什么不用「整段正文」当签名：最后一节的正文延伸到 EOF，孤块若是它的
    #    复制体会被**吸进自己** => 签名改变 => 反而漏报（2026-11-15 实测踩到）。
    sig_owner = {}
    for start, end, title in spans:
        body = [ln.strip() for ln in lines[start + 1:end] if ln.strip()]
        if len(body) < SIG_LINES:
            continue
        sig = tuple(body[:SIG_LINES])
        hits = 0
        for j in range(len(nonempty) - SIG_LINES + 1):
            if tuple(nonempty[j:j + SIG_LINES]) == sig:
                hits += 1
        if hits > 1:
            problems.append(
                ("DUPLICATE_BLOCK",
                 f"section body of {title!r} appears {hits} times (orphan/duplicate copy)"))
        sig_owner.setdefault(sig, []).append(title)
    for sig, owners in sig_owner.items():
        if len(owners) > 1:
            problems.append(
                ("DUPLICATE_SECTION",
                 f"{len(owners)} sections share the same body prefix {sig[:2]}"))

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
            print("  [FAIL] file not found")
            rc = 2
            continue
        text = f.read_text(encoding="utf-8")
        problems, n_sec, n_sub, lines = analyze(text)
        print(f"  sections={n_sec}  sub-headings={n_sub}  lines={len(lines)}")
        if not problems:
            print("  [OK] structure intact: no duplicate / orphan / truncated / interleaved section")
            continue
        rc = 1
        for kind, detail in problems:
            print(f"  [{kind}] {detail}")

    if rc == 0:
        print("=> PASS: 共享 pitfalls 结构完好。")
    else:
        print("=> FAIL: 发现重复块 / 孤儿块 / 标题截断 / 正文交错，需人工核对。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
