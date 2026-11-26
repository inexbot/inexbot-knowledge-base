#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归测试：check_shared_pitfalls_structure.py 的真判据必须能区分「完好」与「损坏」。

背景（2026-11-15 实测）：该脚本最初把**任何重复的长行**都判成 FAIL，
而共享 pitfalls 里不同 section 复用同一段 shell 片段是**正常的**
⇒ 对**结构完好**的真实文件稳定返回 exit 1 → 变成天天误报的假警报。
修复后必须同时满足两个方向：

  case 1 —— 真实完好文件           -> exit 0
  case 2 —— 末尾追加无标题孤儿体   -> exit 1（并报出 DUPLICATE_BLOCK）

⚠️ 必须用 /usr/bin/python3（cron 禁内联脚本，见 §陷阱 29）。

用法：
    /usr/bin/python3 scripts/test_shared_pitfalls_structure.py
退出码：0 = 两个用例都符合预期；1 = 有用例不符合预期。
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SK = Path(__file__).resolve().parent.parent
SCRIPT = SK / "scripts/check_shared_pitfalls_structure.py"
SRC = SK / "references/shared-proxy-service-pitfalls.md"


def run_guard(path):
    return subprocess.run(
        ["/usr/bin/python3", str(SCRIPT), "--file", str(path)],
        capture_output=True, text=True,
    )


def main():
    if not SRC.exists():
        print(f"[FAIL] source file missing: {SRC}")
        return 1

    rc = 0

    # --- case 1: 真实完好文件应 exit 0 ---
    r = run_guard(SRC)
    print("=== case 1: intact file ===")
    for ln in r.stdout.splitlines():
        if ln.strip().startswith("[WARN") or ln.strip().startswith("[OK") or "==" in ln:
            print("  ", ln.strip()[:160])
    print("  exit =", r.returncode)
    if r.returncode != 0:
        print("  [FAIL] intact file should exit 0")
        rc = 1
    else:
        print("  [OK] intact file exits 0")

    # --- case 2: 末尾追加一段无标题的 section 正文 -> 孤儿块，应 exit 1 ---
    lines = SRC.read_text(encoding="utf-8").splitlines()
    starts = [i for i, l in enumerate(lines) if l.startswith("## 陷阱 ")]
    if not starts:
        print("[FAIL] no '## 陷阱 ' section found in source")
        return 1

    # 选最后一个 section 的正文（不含标题行）作为孤儿块内容
    last = starts[-1]
    end = len(lines)
    body_only = [l for l in lines[last + 1:end] if l.strip()]
    if len(body_only) < 8:
        print("[FAIL] last section body too short to build a test orphan")
        return 1

    tmpdir = Path(tempfile.mkdtemp(prefix="pitfalls_guard_"))
    tmp = tmpdir / "corrupted.md"
    try:
        tmp.write_text("\n".join(lines + [""] + body_only) + "\n", encoding="utf-8")
        r2 = run_guard(tmp)
        print(f"\n=== case 2: corrupted file (orphan body appended, {len(body_only)} lines) ===")
        hit = False
        for ln in r2.stdout.splitlines():
            if ln.strip().startswith("[DUPLICATE") or ln.strip().startswith("[SUSPECT"):
                print("  ", ln.strip()[:160])
                hit = True
        print("  exit =", r2.returncode)
        if r2.returncode != 1 or not hit:
            print("  [FAIL] corrupted file should exit 1 with a DUPLICATE/SUSPECT finding")
            rc = 1
        else:
            print("  [OK] corrupted file exits 1 with a duplicate/orphan finding")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return rc


if __name__ == "__main__":
    sys.exit(main())
