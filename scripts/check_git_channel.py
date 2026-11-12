#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测 github.com 的 443 (HTTPS/TLS) 与 22 (SSH/TCP) 通道可达性。

用途：git push 报 "Failed to connect to github.com port 443" 时，快速定性
      「是不是 github.com:443 这一台机器的端口问题，SSH 通道还能不能用」。

⚠️ 判读时务必记住「假绿」（2026-11-12 实测）：
   探针报 443 = OK **不代表**真实 git push 会成功 —— 443 的可达性是波动的，
   实测出现过「探针 3/3 OK 但 push 仍然 130s 超时」。
   ⇒ **真正的判据是 push 本身的结果**；本脚本的用途是
     「push 失败之后快速定性」，**不是**「push 之前绿了就放心用 HTTPS」。

用法：
    /usr/bin/python3 scripts/check_git_channel.py
    /usr/bin/python3 scripts/check_git_channel.py --attempts 5

退出码：
    0 = 至少一条通道可用（SSH 通 = 可以改走 SSH push）
    1 = 两条通道都不可用（等网络恢复，别硬推）
    2 = 参数错误

⚠️ 必须用 /usr/bin/python3（沙盒 python3 没有 ssl 之外的环境差异，且 cron 禁内联脚本）。
   见 shared-proxy-service-pitfalls.md §陷阱 29。
"""

import argparse
import socket
import ssl
import sys
import time

DEFAULT_HOST = "github.com"


def probe(host, port, use_tls, attempts, timeout):
    """返回 (成功次数, 总次数, [每次结果字符串])。"""
    ok = 0
    results = []
    for _ in range(attempts):
        t0 = time.time()
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            try:
                if use_tls:
                    ctx = ssl.create_default_context()
                    wrapped = ctx.wrap_socket(sock, server_hostname=host)
                    wrapped.close()
                else:
                    sock.close()
            except Exception:
                sock.close()
                raise
            results.append("%.2fs" % (time.time() - t0))
            ok += 1
        except Exception as exc:
            results.append("FAIL(%s)" % type(exc).__name__)
        time.sleep(0.3)
    return ok, attempts, results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=8.0)
    args = ap.parse_args()

    print("=== github channel probe (host=%s) ===" % args.host)

    https_ok, https_n, https_times = probe(
        args.host, 443, True, args.attempts, args.timeout)
    print("  :443 (TLS)  %d/%d OK  [%s]" % (
        https_ok, https_n, ", ".join(https_times)))

    ssh_ok, ssh_n, ssh_times = probe(
        args.host, 22, False, args.attempts, args.timeout)
    print("  :22  (TCP)  %d/%d OK  [%s]" % (
        ssh_ok, ssh_n, ", ".join(ssh_times)))

    if https_ok == https_n:
        verdict = "OK"
    elif https_ok:
        verdict = "DEGRADED"
    else:
        verdict = "UNREACHABLE"
    print("  -> :443 verdict = %s" % verdict)

    print("\nREMINDER: 探针 :443 = OK **不代表** push 会成功（假绿，见文件头）。")
    print("  push 失败时用本脚本定性：")
    print("    :443 UNREACHABLE + :22 OK  ->  改走 SSH 传输通道：")
    print("      git push git@github.com:owner/repo.git main:main")
    print("      （用一次性语法，**不要** git remote set-url —— 两个 KB 共用仓库配置）")

    if ssh_ok == 0 and https_ok == 0:
        print("\nRESULT: both channels unreachable -> wait for network, do not force push")
        return 1
    print("\nRESULT: at least one channel usable (prefer SSH when :443 is not fully OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
