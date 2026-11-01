#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端请求探针 —— 唯一能抓到「proxy -> gateway -> LLM」链路故障的检查。

2026-10-31 新增。原因：proxy 上游 read timeout 硬编码 120s 时，
/health 绿灯、检索链路 PASS、引用链接 200 —— 所有表层检查全绿，
但用户查长手册类问题时随机拿到 HTTP 502。

用法：
    /usr/bin/python3 scripts/check_e2e_request.py              # 默认 4 次
    /usr/bin/python3 scripts/check_e2e_request.py --runs 6      # 更多次
    /usr/bin/python3 scripts/check_e2e_request.py --query "冲压工艺 手册 参数设置"

退出码：
    0 = 全部 200
    1 = 出现非 200（详见 stderr 判读）

⚠️ 必须用 /usr/bin/python3（沙盒 python3 没装 requests/flask）。
⚠️ 客户端 timeout 必须 > proxy 的上游 timeout（现 300s）→ 用 -m 360。
⚠️ timeout 类故障是【随机】的 —— 单次 200 不能证明通过，必须连打多次。
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

PROXY_URL = "http://localhost:8643/v1/chat/completions"
GATEWAY_URL = "http://localhost:8642/v1/chat/completions"
API_KEY = "hermes-website-search"

# 故意用不存在的 model，让 gateway 快速拒绝，从而快速区分「检索崩了」与「网关慢」
FAKE_MODEL = "definitely-not-a-real-model-xyz"

DEFAULT_QUERIES = [
    "C1102 控制器 通讯接口 有哪些",
    "冲压工艺 手册 参数设置",
    "示教器 操作手册 功能说明",
]


def call(url, query, timeout):
    payload = {
        "model": FAKE_MODEL,
        "messages": [{"role": "user", "content": query}],
        "max_tokens": 16,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + API_KEY,
        },
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, time.time() - t0, ""
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        return e.code, time.time() - t0, body
    except Exception as e:
        return "ERR", time.time() - t0, "%s: %s" % (type(e).__name__, str(e)[:160])


def classify(status, body):
    if status == 200:
        return "OK"
    if status == 500:
        return "RETRIEVAL-BROKEN (500) —— slug 契约断裂 / index 读取异常"
    if status == 502:
        if "timed out" in body or "timeout" in body:
            return ("GATEWAY-TIMEOUT (502) —— 检索多半成功，是网关比 proxy timeout 慢；"
                    "直打 8642 量真实耗时再与 proxy timeout 比对")
        return "GATEWAY-ERROR (502)"
    if status == "ERR":
        if "RemoteDisconnected" in body:
            return "CONCURRENT-RESTART —— 查 PID + journal，不是检索故障"
        return "CLIENT-ERROR —— 客户端 -m 给太小？用 -m 360"
    return "UNKNOWN"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=4, help="每个查询连打几次（默认 4）")
    ap.add_argument("--timeout", type=int, default=360, help="客户端超时秒（默认 360）")
    ap.add_argument("--query", action="append", default=None, help="自定义查询，可重复")
    ap.add_argument("--gateway-probe", action="store_true",
                    help="额外直打 gateway 8642 量真实耗时")
    args = ap.parse_args()

    queries = args.query or DEFAULT_QUERIES
    total = 0
    ok = 0
    failures = []

    print("=== 端到端请求探针（proxy 8643 -> gateway 8642 -> LLM）===")
    print("runs/query = %d | client timeout = %ds | model = %s"
          % (args.runs, args.timeout, FAKE_MODEL))

    for q in queries:
        for i in range(args.runs):
            status, elapsed, body = call(PROXY_URL, q, args.timeout)
            total += 1
            verdict = classify(status, body)
            flag = "" if status == 200 else "   <<< FAIL"
            print("  [%s] HTTP %-4s %6.1fs | %s%s"
                  % (q[:18], status, elapsed, verdict, flag), flush=True)
            if status == 200:
                ok += 1
            else:
                failures.append((q, status, elapsed, verdict, body))

    if args.gateway_probe:
        print("\n=== 直打 gateway 8642（绕过 proxy）量真实耗时 ===")
        for q in queries:
            status, elapsed, body = call(GATEWAY_URL, q, args.timeout)
            print("  HTTP %-4s %6.1fs | %s" % (status, elapsed, q[:40]), flush=True)
        print("  → 若真实耗时 > proxy 的上游 timeout，则 502 与检索无关，是 timeout 太短。")

    print("\nSUMMARY: %d/%d succeeded" % (ok, total))
    if failures:
        print("\nFAILURES (%d):" % len(failures))
        for q, status, elapsed, verdict, body in failures:
            print("  - %s | HTTP %s in %.1fs | %s" % (q[:40], status, elapsed, verdict))
            if body:
                print("      body: %s" % body[:160])
        print("\n判读：500=检索崩了 / 502=网关慢（检索多半成功）/ "
              "RemoteDisconnected=并发 restart / 000=客户端 timeout 太小")
        return 1

    print("→ 全部 200。注意：timeout 类故障是随机的，单次通过不作数。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
