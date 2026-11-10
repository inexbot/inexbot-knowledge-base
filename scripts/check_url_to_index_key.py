#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反向查表守卫：proxy 返回的 url → index.json 的 key（2026-11-09 新增）
=====================================================================

为什么需要这个脚本
------------------
审计脚本常要「从 proxy 的检索结果反查这条页面对应的 md 文件存不存在」。
**这一步的归一化本身就是一套隐式契约**，且极易写错。

⚠️⚠️ **归一化规则必须按 KB 分开**（2026-11-10 实测更正 —— 这条最重要）

两个 KB 的 index key 是**相反**的编码态：

| KB | key 形态 | 中文 | `&` / `+` | 需要的动作 |
|---|---|---|---|---|
| `inexbot` (doc.inexbot.com) | 已 percent 编码 | `%E6%8A%80…` | 字面 `&` / `+` | 只把 url 里的 `%26`→`&`、`%2B`→`+` |
| `inexbot-open` (open.inexbot.com) | **明文中文** | `上位机` | 字面 `&` / `+` | url 是整体编码态 → 需**整体 unquote** |

判别方式：**看该 KB 的 index key 里有没有 `%`**（等价于 proxy 的 `_kb_url()` 判据）。
实测 2026-11-10：
- `inexbot`：559/560 key 含 `%`，**0** 个明文中文 → 「只替换两字符」正确
- `inexbot-open`：**0** 个 key 含 `%`，441 个明文中文 → 「只替换两字符」**必然大面积 miss**

⇒ 脚本第一版对两个 KB 用同一条规则 → 45 条 `inexbot-open` 结果全部查不到，
  **看着像 KB 回归，其实是脚本自己的查表 bug**（与 11-09 同类的「审计脚本自伤」陷阱）。

`inexbot` 的实测命中率（47 条 proxy 结果，2026-11-09）：
- 只替换两字符              : **47 / 47**  <- 正确
- 先精确匹配 + unquote 兜底 : 46 / 47      <- `+` 那条救不回来
- 整体 unquote              : **1 / 47**   <- 几乎全错

2026-11-09 那次就是因为用了整体 `unquote()`，把一条**明明存在的 md**
（`zh-操作手册-25.01版本-输入输出类+定时器类+运算类手册.md`，17,916 字节）
误报成「md not found」，差点当成 KB 回归写进报告。

⇒ **教训：反查 md 的归一化不是「一条全局规则」，而是「每个 KB 一条」。**
⇒ 写完这类审计脚本后跑本脚本验一遍。

用法
----
    /usr/bin/python3 scripts/check_url_to_index_key.py
    /usr/bin/python3 scripts/check_url_to_index_key.py --queries 10

输出
----
    URL->index-key hit (norm)  : 47 / 47
    true silent-degradation(800): 0
    full text hit               : 24
    hit 4000-char cap           : 23
    no-md lookup                : 0

退出码：0 = 全部查得到；1 = 有查不到的条目（可能是脚本 bug，也可能是真故障）。

⚠️ 必须用 **/usr/bin/python3**（沙盒 python3 没装 flask）。
⚠️ 本地 security policy 禁止 `python3 -c`，脚本必须走文件路径。
"""
import importlib.util as _iu
import json
import sys
from pathlib import Path
from urllib.parse import unquote

PROXY = "/home/ecs-user/hermes-skill-proxy/hermes-skill-proxy.py"

# 两个 KB 的 KB 根目录；base_url 用于从 proxy url 里切出 path
KB_ROOTS = {
    "inexbot": (Path.home() / ".hermes/kb/inexbot", "doc.inexbot.com"),
    "inexbot-open": (Path.home() / ".hermes/kb/inexbot-open", "open.inexbot.com"),
}

DEFAULT_QUERIES = [
    "冲压工艺 手册 参数设置",
    "0x0051 IPM故障",
    "通讯协议 地址码 Modbus 寄存器",
    "示教器 手动示教 操作步骤",
    "伺服 报警 故障码 处理",
    "机器人 TCP 标定 方法",
    "输入输出 IO 组号 DOUT",
    "控制器 以太网 通讯 配置",
    "双机器人 协同 焊接",
    "AGV 导航 调度",
]


def norm_path(path, kb="inexbot"):
    """proxy url 的 path -> index.json 的 key。

    ⚠️ **归一化规则必须按 KB 分开**（2026-11-10 实测更正）：

    两个 KB 的 index key 是**相反**的编码态：

    | KB | key 形态 | 中文 | `&` / `+` | 需要的动作 |
    |---|---|---|---|---|
    | `inexbot` (doc.inexbot.com) | 已 percent 编码 | `%E6%8A%80…` | 字面 `&` / `+` | 只把 url 里的 `%26`→`&`、`%2B`→`+` |
    | `inexbot-open` (open.inexbot.com) | 明文中文 | `上位机` | 字面 `&` / `+` | url 是整体编码态 -> 需**整体 unquote** |

    实测（2026-11-10）：
    - `inexbot`：559/560 key 含 `%`，0 个明文中文 -> 「只替换两字符」正确
    - `inexbot-open`：**0** 个 key 含 `%`，441 个明文中文 -> 「只替换两字符」**必然大面积 miss**

    ⇒ 旧版脚本对两个 KB 用同一条规则 -> 45 条 `inexbot-open` 结果全部查不到，
      **看起来像 KB 回归，其实是脚本自己的查表 bug**。
    ⇒ 判别方式：**看该 KB 的 index key 里有没有 `%`**（等价于 proxy 的 `_kb_url()` 判据）。
    """
    if kb == "inexbot":
        # key 是已编码态：只还原被编码的 & 和 +，中文那半边的 %XX 必须原样保留
        return path.replace("%26", "&").replace("%2B", "+")
    # inexbot-open：key 是明文态，url 是整体编码态 -> 需要整体 unquote
    return unquote(path)


def load_proxy():
    spec = _iu.spec_from_file_location("px", PROXY)
    mod = _iu.module_from_spec(spec)
    sys.modules["px"] = mod
    spec.loader.exec_module(mod)
    mod.load_all_indexes()
    return mod


def md_chars_for(mod, md_root, key):
    """按 proxy 的 _md_slug_candidates() 找 md 文件，返回**字符数**。

    ⚠️ 两个必踩的坑（见共享 pitfalls 陷阱 11 / 24）：
      1. `_md_slug_candidates()` 返回**不带 .md 后缀**的裸 slug -> 必须自己拼。
      2. 超长文件名会让 Path.exists() 抛 OSError [Errno 36] -> 必须 except。
    ⚠️ 比**字符数**不是字节数（中文 1 字 = 3 字节，比字节会误判）。
    """
    try:
        cands = mod._md_slug_candidates(key)
    except Exception:
        return None
    for c in cands:
        try:
            p = md_root / (c + ".md")
            if p.exists():
                return len(p.read_text(encoding="utf-8"))
        except OSError:
            continue
    return None


def main(argv):
    queries = DEFAULT_QUERIES
    if "--queries" in argv:
        try:
            i = argv.index("--queries")
            queries = DEFAULT_QUERIES[: int(argv[i + 1])]
        except (IndexError, ValueError):
            pass

    if not Path(PROXY).exists():
        print("✗ proxy 不存在: %s" % PROXY)
        return 1
    try:
        P = load_proxy()
    except Exception as e:
        print("✗ proxy 加载失败: %s: %s" % (type(e).__name__, e))
        print("  → 确认用 /usr/bin/python3 跑（沙盒 python3 没装 flask）")
        return 1

    total = 0
    keyhit = 0
    degraded = 0
    full = 0
    trunc = 0
    nomd = 0
    bad = []

    for kb, (kb_root, base) in KB_ROOTS.items():
        idx_path = kb_root / "index.json"
        if not idx_path.exists():
            print("ⓘ 跳过 %s（没有 %s）" % (kb, idx_path))
            continue
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        md_root = kb_root / "md"

        for q in queries:
            try:
                res = P.search_single_kb(kb, q, 5)
            except Exception as e:
                print("  ✗ search_single_kb(%s, %r) 抛异常: %s: %s"
                      % (kb, q, type(e).__name__, e))
                continue
            for r in res:
                total += 1
                snip = r.get("content_snippet") or ""
                n = len(snip)
                url = r.get("url") or ""
                if base not in url:
                    nomd += 1
                    bad.append((kb, r.get("title", "")[:40],
                                "URL 中找不到 base: " + url[:100]))
                    continue
                path = url.split(base, 1)[-1]
                key = norm_path(path, kb)
                if key in idx:
                    keyhit += 1
                    md = md_chars_for(P, md_root, key)
                else:
                    md = None
                    bad.append((kb, r.get("title", "")[:40], path))
                if n == 800:
                    degraded += 1
                elif md is None:
                    nomd += 1
                elif n == md:
                    full += 1
                elif n < md:
                    trunc += 1

    print("=" * 70)
    print("URL -> index key 反查守卫（归一化按 KB 分开：inexbot 只换 %%26/%%2B，"
          "inexbot-open 整体 unquote）")
    print("=" * 70)
    print("total proxy results              : %d" % total)
    print("URL->index-key hit (norm)        : %d / %d" % (keyhit, total))
    print("true silent-degradation(==800)   : %d" % degraded)
    print("full text hit (chars == md chars): %d" % full)
    print("hit 4000-char cap                : %d" % trunc)
    print("no-md lookup                     : %d" % nomd)

    if bad:
        print("\n--- 查不到 key 的条目 ---")
        for kb, title, path in bad[:10]:
            print("   [%s] %s" % (kb, title))
            print("        %s" % path[:120])

    if bad or degraded or nomd:
        print("\n⚠️ 有条目查不到 / 静默降级 —— **先确认是不是本脚本的查表 bug**：")
        print("   归一化**按 KB 分开**：inexbot（key 已编码）只换 %%26/%%2B；")
        print("   inexbot-open（key 是明文中文）需整体 unquote。")
        print("   用同一条规则套两个 KB -> 必然大面积假 miss。")
        print("   详见共享 pitfalls §陷阱 24。")
        return 1

    print("\n✓ 全部条目都能反查到 index key，且无 800 字静默降级。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
