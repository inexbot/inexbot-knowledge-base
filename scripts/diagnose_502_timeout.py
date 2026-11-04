#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端 502 超时归因探针 —— 把「proxy 502」定位到具体层和具体原因。

背景（2026-11-03 实测）：proxy 的上游 timeout 是 300s，而 gateway 的 provider
timeout 是 900s、整轮 gateway_timeout 是 1800s。上游 LLM 偶发停顿 >300s 时，
proxy 会先放弃并返回 502，但 gateway 那边**最终仍会完成**这个请求。

本脚本用「arrival -> response」FIFO 配对 + gateway access log 的 start-time 戳，
回答三个问题：
  1. 502 的 elapsed 是否精确等于 proxy 的 timeout？          -> 是则确定是 timeout 类
  2. gateway 侧那个 start-time 戳最终有没有出现？           -> 有=proxy 放弃太早；无=gateway 挂住
  3. 正常请求的延迟区间是多少？                             -> 用来判断上游是否异常变慢

用法：
    /usr/bin/python3 scripts/diagnose_502_timeout.py
    /usr/bin/python3 scripts/diagnose_502_timeout.py --since "2026-11-03 11:00" --unit hermes-skill-proxy

⚠️ 必须用 /usr/bin/python3（沙盒 python3 没装 requests/flask）。
⚠️ 退出码：0 = 未发现 timeout 类 502；1 = 发现（且给出归因）。
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime

PROXY_UNIT = "hermes-skill-proxy.service"
QUESTIONS_LOG = None          # 运行时填充
GATEWAY_LOG = None            # 运行时填充


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def find_home():
    # ⚠️ 不要用 subprocess 跑 `echo $HOME` —— 没有 shell 就不会展开变量
    return os.path.expanduser("~")


def load_arrivals(since_prefix):
    """proxy 每收到一个请求就往 questions.log 追加一行 —— 这是 arrival 时间源。"""
    out = []
    try:
        with open(QUESTIONS_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                t = d.get("time", "")
                if t.startswith(since_prefix):
                    out.append((t, d.get("question", "")))
    except OSError:
        pass
    return out


def load_responses(unit, since):
    out = sh(["sudo", "-n", "journalctl", "-u", unit, "--since", since,
              "--no-pager", "-o", "short-iso"])
    rx = []
    pat = (r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\+0800 .*?"
           r"POST /v1/chat/completions HTTP/1\.1\" (\d{3})")
    for m in re.finditer(pat, out, re.M):
        rx.append((m.group(1), m.group(2)))
    return rx


def gateway_completed(start_stamp):
    """gateway 的 access log 行里带请求的 start-time 戳。

    若这一行存在（哪怕晚很多），说明 gateway 最终完成了该请求
    -> proxy 放弃太早；若不存在，说明 gateway 侧真的挂住了。
    """
    try:
        out = sh(["grep", "-aF", start_stamp + " +0800", GATEWAY_LOG])
    except Exception:
        return None
    lines = [l for l in out.splitlines() if "POST /v1/chat/completions" in l]
    if not lines:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", lines[-1])
    return m.group(1) if m else "unknown"


def main():
    global QUESTIONS_LOG, GATEWAY_LOG
    home = find_home()
    QUESTIONS_LOG = home + "/.hermes/kb/inexbot/questions.log"
    GATEWAY_LOG = home + "/.hermes/logs/agent.log"

    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None,
                    help="journal 起始时间，如 '2026-11-03 11:00'（默认今天 11:00）")
    ap.add_argument("--unit", default=PROXY_UNIT)
    ap.add_argument("--proxy-timeout", type=int, default=300,
                    help="proxy 的上游 timeout 秒数（用于判定 elapsed 是否撞顶）")
    args = ap.parse_args()

    since = args.since or (datetime.now().strftime("%Y-%m-%d") + " 11:00")
    prefix = since[:13]          # 'YYYY-MM-DD HH'

    arrivals = load_arrivals(prefix)
    responses = load_responses(args.unit, since)

    print("=" * 72)
    print("502 超时归因探针")
    print("=" * 72)
    print("arrivals (questions.log) :", len(arrivals))
    print("responses (journal)      :", len(responses))
    print("proxy timeout (assumed)  :", args.proxy_timeout, "s")
    print()

    print("=== FIFO 配对：arrival -> response ===")
    i = 0
    timeouts = []
    latencies = []
    for t, status in responses:
        if i >= len(arrivals):
            print("  resp=%s %s (no arrival)" % (t[11:19], status))
            continue
        a, q = arrivals[i]
        i += 1
        try:
            t1 = datetime.strptime(a, "%Y-%m-%d %H:%M:%S")
            t2 = datetime.strptime(t.replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S")
            el = (t2 - t1).total_seconds()
        except ValueError:
            print("  arr=%s resp=%s %s (parse error)" % (a[11:], t[11:19], status))
            continue
        hit = abs(el - args.proxy_timeout) <= 2
        flag = ""
        if status != "200":
            flag = "   <<< FAIL"
        elif hit:
            flag = "   <<< 撞上 proxy timeout（但成功）"
        print("  arr=%s -> resp=%s  %s  %6.1fs  %-26s%s"
              % (a[11:], t[11:19], status, el, q[:26], flag))
        if status == "200" and not hit:
            latencies.append(el)
        if status != "200" and hit:
            timeouts.append((a, q, el))

    print()
    print("=== 结论 ===")
    if latencies:
        print("正常延迟区间 : %.1fs – %.1fs" % (min(latencies), max(latencies)))
    if not timeouts:
        print("timeout 类失败 : 0  -> 本窗口未发现 proxy 提前放弃")
        return 0

    print("timeout 类失败 : %d" % len(timeouts))
    for a, q, el in timeouts:
        stamp = a[11:]
        done = gateway_completed(stamp)
        print()
        print("  请求 %s  (%.1fs, query=%s)" % (a, el, q[:40]))
        if done:
            print("    gateway 最终完成于 : %s  -> **proxy 放弃太早**" % done)
            print("    => 修法：把 proxy 的 HERMES_TIMEOUT 调到 >= gateway provider timeout")
            print("       (gateway provider=900s / agent.gateway_timeout=1800s)")
        else:
            print("    gateway 侧没有完成记录 -> gateway/provider 侧真的挂住了")
            print("    => 查上游限流 / 并发 / provider 状态")
    print()
    print("判读表：500=检索崩了 / 502+elapsed 撞 proxy timeout=上游太慢 / RemoteDisconnected=并发 restart")
    return 1


if __name__ == "__main__":
    sys.exit(main())
