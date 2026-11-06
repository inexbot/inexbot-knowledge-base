#!/usr/bin/env python3
"""
校验 hermes-skill-proxy **线上进程**实际拿到的环境变量（hash-only 输出）。

为什么需要这个脚本（2026-11-05 现场）：
  「补丁『写了』≠ 补丁『上线了』」的教科书案例 —— unit 文件从 11-04 11:36 起就带着
  `Environment="HERMES_TIMEOUT=1800"`，但线上进程是 10-31 11:36 启动的，
  **早于补丁 4 天** → 一直跑旧代码（300s 上限）→ 用户随机 502。
  判据不是「unit 文件里有没有」，而是「/proc/<pid>/environ 里有没有」。

⚠️ 为什么只打印 sha 摘要、不打印明文：
  1. Hermes 的**输出脱敏**会把密钥渲染成 `hermes...rch` 之类带省略号的形式，
     看起来像「被截断的占位符」→ 极易误判成部署污染（2026-10-29 曾因此误判）。
     判读一律用 sha 摘要。
  2. 别把 key 明文打进日志。

用法：
    python3 check_proxy_env.py            # 只查线上进程
    python3 check_proxy_env.py --units    # 额外解析 /etc 与 repo 模板两份 unit

退出码：
    0 = 全部环境变量到位（且与代码默认值一致）
    1 = 有变量缺失 / 与预期不符
    2 = 找不到 proxy 进程
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

# 预期值。PROXY_PORT / HERMES_URL / SKILL_NAME 是行为参数；
# HERMES_API_KEY 必须等于代码默认值，否则 proxy 会用一个错误 key 去转发 gateway。
EXPECTED = {
    "PROXY_PORT": "8643",
    "HERMES_URL": "http://localhost:8642",
    "HERMES_API_KEY": "hermes-website-search",
    "SKILL_NAME": "inexbot-knowledge-base",
    # 2026-11-05 起与 gateway 的 agent.gateway_timeout(1800s) 对齐。
    # 若要改这里，先改 /etc/systemd/system/hermes-skill-proxy.service 与
    # hermes-skill-proxy repo 里的模板**两份**，再 daemon-reload + restart。
    "HERMES_TIMEOUT": "1800",
}

UNIT_FILES = [
    "/etc/systemd/system/hermes-skill-proxy.service",
    "/home/ecs-user/hermes-skill-proxy/hermes-skill-proxy.service",
]


def sha12(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:12]


def find_pid() -> str:
    out = subprocess.check_output(["pgrep", "-f", "hermes-skill-proxy.py"]).decode()
    pids = out.split()
    if not pids:
        raise SystemExit("no hermes-skill-proxy.py process found")
    return pids[0]


def read_proc_env(pid: str) -> dict:
    env = {}
    raw = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    for item in raw:
        if b"=" in item:
            k, v = item.split(b"=", 1)
            env[k.decode(errors="replace")] = v.decode(errors="replace")
    return env


def parse_unit(path: str) -> dict:
    """解析 unit 里的 Environment="K=V" 行。

    ⚠️ systemd 不认 `Environment=` 后跟缩进续行（那是 shell .env 写法）——
    那样写会把后续行当成未知 directive key 全部丢弃。
    """
    out = {}
    p = Path(path)
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s.startswith("Environment="):
            continue
        body = s[len("Environment="):].strip()
        if body.startswith('"') and body.endswith('"'):
            body = body[1:-1]
        if "=" in body:
            k, v = body.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", action="store_true", help="额外解析两份 unit 文件")
    args = ap.parse_args()

    try:
        pid = find_pid()
    except SystemExit as e:
        print(f"[FAIL] {e}")
        return 2

    print(f"proxy PID = {pid}")
    try:
        started = subprocess.check_output(
            ["ps", "-o", "lstart=", "-p", pid]).decode().strip()
        print(f"  started  = {started}")
    except Exception:
        pass
    print()

    env = read_proc_env(pid)
    problems = []

    print("--- live process env (/proc/<pid>/environ) ---")
    for name, expected in EXPECTED.items():
        actual = env.get(name)
        if actual is None:
            print(f"  [ABSENT] {name}   <-- 未送达线上进程！补丁没上线")
            problems.append(f"{name} ABSENT")
            continue
        ok = actual == expected
        print(f"  {'[OK    ]' if ok else '[DIFF  ]'} {name}: "
              f"len={len(actual)} sha12={sha12(actual)}")
        if not ok:
            problems.append(f"{name} != expected (sha12 {sha12(actual)} vs {sha12(expected)})")

    print()
    print("--- expected (code defaults) ---")
    for name, expected in EXPECTED.items():
        print(f"  {name}: len={len(expected)} sha12={sha12(expected)}")

    if args.units:
        for u in UNIT_FILES:
            print()
            print(f"--- unit: {u} ---")
            vals = parse_unit(u)
            if not vals:
                print("  <no Environment= lines found>")
                continue
            for name in EXPECTED:
                v = vals.get(name)
                if v is None:
                    print(f"  [ABSENT] {name}   <-- unit 里没有！")
                    problems.append(f"unit {u} missing {name}")
                else:
                    ok = v == EXPECTED[name]
                    print(f"  {'[OK    ]' if ok else '[DIFF  ]'} {name}: "
                          f"len={len(v)} sha12={sha12(v)}")

    print()
    if problems:
        print("[FAIL] 问题清单：")
        for p in problems:
            print(f"  - {p}")
        print("\n判读：")
        print("  * unit 文件里没有       -> 改 unit（/etc 与 repo 模板两份都要改）")
        print("  * unit 有但进程 ABSENT  -> 需要 daemon-reload + restart 才上线")
        print("  * 进程有但值 != expected -> 改 unit 的值，并确认它等于代码默认值")
        return 1

    print("[OK] 线上进程环境变量全部到位且与代码默认值一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
