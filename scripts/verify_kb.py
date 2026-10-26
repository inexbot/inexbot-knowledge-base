#!/usr/bin/env python3
"""
KB 回归验证：一次性核对两个知识库的索引完整性、slug 契约、检索链路与引用链接可达性。

用途：每次 KB 定时爬取后跑一遍，替代手写的临时探针脚本。

⚠️ 必须用 /usr/bin/python3 跑（沙盒 python3 没装 flask，import proxy 模块会失败）：
    /usr/bin/python3 ~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/verify_kb.py

⚠️ 本脚本会实网 curl（每个 KB 抽 12 条 URL），耗时约 20–40 秒。

退出码：0 = 全部通过；1 = 有 FAIL。
"""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, unquote

PROXY = Path("/home/ecs-user/hermes-skill-proxy/hermes-skill-proxy.py")
KB_ROOT = Path.home() / ".hermes" / "kb"
BASE = {"inexbot": "https://doc.inexbot.com", "inexbot-open": "https://open.inexbot.com"}
QUERIES = ["冲压工艺手册 参数设置", "示教器 操作手册", "Modbus 功能 使用"]
SAMPLE = 12
ZWSP = chr(0x200B)   # 零宽空格；用 chr() 写，避免源码里出现不可见字符

fails = []
_scope = [""]   # 当前 KB 作用域，供 check() 归属失败项


def check(label, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        fails.append(f"{_scope[0]}: {label}" if _scope[0] else label)


def md_candidates(path):
    """index key -> md 文件名候选（unquote 后 /→- 是 crawler 的真实规则）"""
    raw = path.lstrip("/")
    return [raw.replace("/", "-"),
            unquote(raw).replace("/", "-"),
            quote(raw, safe="")]


def head(url):
    r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                        "-L", "--max-time", "25", url],
                       capture_output=True, text=True)
    return r.stdout.strip()


def load_proxy():
    spec = importlib.util.spec_from_file_location("hsp", PROXY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hsp"] = mod
    spec.loader.exec_module(mod)
    mod.load_all_indexes()          # 不调用则 _doc_scores 为空，检索返回 []
    return mod


def check_kb(name):
    print(f"\n=== {name} ===")
    _scope[0] = name
    kb = KB_ROOT / name
    idx = json.loads((kb / "index.json").read_text(encoding="utf-8"))
    md_dir, raw_dir = kb / "md", kb / "raw"

    # --- 索引完整性 ---
    check("index 条目数 > 0", len(idx) > 0, str(len(idx)))
    check("md 文件数 == index 条目数",
          len(list(md_dir.glob("*.md"))) == len(idx),
          f"{len(list(md_dir.glob('*.md')))} vs {len(idx)}")
    if raw_dir.exists():
        check("raw 文件数 == index 条目数",
              len(list(raw_dir.glob("*.html"))) == len(idx),
              f"{len(list(raw_dir.glob('*.html')))} vs {len(idx)}")
    check("无零长度 snippet（= 抓到 404 空壳页）",
          sum(1 for v in idx.values() if not (v.get("content_snippet") or "").strip()) == 0)
    check("无 description=='Not Found'",
          sum(1 for v in idx.values() if v.get("description") == "Not Found") == 0)
    check("无空标题", sum(1 for v in idx.values() if not v.get("title")) == 0)
    check("标题/描述无零宽字符 U+200B",
          sum(1 for v in idx.values()
              if ZWSP in (v.get("title") or "") + (v.get("description") or "")) == 0)
    check("key 里无裸 %（否则引用链接必 404）",
          sum(1 for k in idx if re.search(r"%(?![0-9A-Fa-f]{2})", k)) == 0)

    # --- slug 契约：index key 是否都能定位到 md ---
    resolved = 0
    for k in idx:
        for c in md_candidates(k):
            try:
                if (md_dir / f"{c}.md").exists():
                    resolved += 1
                    break
            except OSError:
                continue        # 文件名过长 (Errno 36)
    check("所有 index key 都能定位到 md 文件", resolved == len(idx),
          f"{resolved}/{len(idx)}")

    # --- 附图覆盖率：含图 md 是否都能从 index key 反查 ---
    img_re = re.compile(r"!\[[^\]]*\]\(https?://")
    with_imgs = {f.stem for f in md_dir.glob("*.md")
                 if img_re.search(f.read_text(encoding="utf-8", errors="ignore"))}
    reachable = {unquote(k.lstrip("/")).replace("/", "-") for k in idx}
    check("含图 md 全部可从 index 反查",
          len(with_imgs & reachable) == len(with_imgs),
          f"{len(with_imgs & reachable)}/{len(with_imgs)}")
    return idx


def check_proxy(mod):
    print("\n=== proxy 检索链路 ===")
    _scope[0] = "proxy"
    all_urls, degraded = [], []
    for kb in BASE:
        for q in QUERIES:
            for r in mod.search_single_kb(kb, q, 5):
                all_urls.append(r["url"])
                # 800 = index 摘要上限；<=800 说明正文没读到（静默降级）
                if len(r.get("content_snippet", "")) <= 800:
                    degraded.append((kb, q, r["title"], len(r.get("content_snippet", ""))))
    check("检索有返回结果", len(all_urls) > 0, f"{len(all_urls)} urls")
    check("无双重编码 URL（%25）", not any("%25" in u for u in all_urls),
          f"{sum(1 for u in all_urls if '%25' in u)} 个")
    for kb, q, title, n in degraded:
        tag = "上游占位页，属正常" if n < 200 else "疑似静默降级"
        print(f"      note: 短 snippet {n:>4}  {kb} / {q} / {title[:34]}  ← {tag}")
    return all_urls


def check_urls(urls):
    print("\n=== 引用链接实网可达性 ===")
    _scope[0] = "proxy"
    uniq = list(dict.fromkeys(urls))
    step = max(1, len(uniq) // SAMPLE)
    sample = uniq[::step][:SAMPLE]
    ok = 0
    for u in sample:
        code = head(u)
        if code.startswith("2"):
            ok += 1
        else:
            print(f"      MISS {code} {u[:120]}")
    check(f"抽样 {len(sample)} 条引用链接全部 HTTP 200", ok == len(sample),
          f"{ok}/{len(sample)}")


def check_service():
    print("\n=== proxy 服务 ===")
    _scope[0] = "proxy"
    r = subprocess.run(["curl", "-s", "--max-time", "15",
                        "http://127.0.0.1:8643/health"], capture_output=True, text=True)
    try:
        j = json.loads(r.stdout)
        check("/health status == ok", j.get("status") == "ok", r.stdout[:100])
        for kb in BASE:
            d = j["indexes"][kb]
            check(f"{kb} loaded", d["loaded"], f"docs={d['docs']}")
    except Exception as e:
        check("/health 可解析", False, f"{e} {r.stdout[:100]}")


def main():
    print("=" * 64)
    print("KB 回归验证")
    print("=" * 64)
    for kb in BASE:
        check_kb(kb)
    mod = load_proxy()
    urls = check_proxy(mod)
    check_urls(urls)
    check_service()
    print("\n" + "=" * 64)
    if fails:
        print(f"FAILURES ({len(fails)}):")
        # 按 KB 分组，方便一眼看出是哪个知识库出的问题
        by_kb = {}
        for f in fails:
            kb = f.split(":", 1)[0] if ":" in f else "(global)"
            by_kb.setdefault(kb, []).append(f)
        for kb, items in by_kb.items():
            print(f"  [{kb}] {len(items)} 项")
            for f in items:
                print("    -", f)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
