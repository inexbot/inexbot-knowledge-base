#!/usr/bin/env python3
"""Determine the proxy's next automatic reload time AND whether the reload
chain is still alive -- by reading thread start times, not the journal.

Why this exists (2026-11-06)
----------------------------
The naive ways to check "will the proxy pick up the new index.json?":

  1. `journalctl | grep Total:`  -> UNRELIABLE. Under systemd, Python's
     stdout is block-buffered, so the reload line may sit in the user-space
     buffer for hours. "No reload line in journal" does NOT mean "no
     reload happened" (see references/proxy-runtime-freshness.md).
  2. `/health` docs count        -> tells you the CURRENT state but not
     WHEN the next reload lands, so you cannot tell "5h window, fine"
     from "reload chain broke, will never happen".

The reliable signal: every `schedule_reload()` fire creates a NEW
`threading.Timer` thread. That thread is born at the previous fire and
lives exactly RELOAD_INTERVAL (5h) before firing again -- so its age is
ALWAYS in the [0, 5h) range, uniformly distributed over the cycle.
If the chain broke (the pre-2026-10-27 bug), no such thread is created
and the proxy stays on the old index forever.

⚠️ 2026-11-07 FIX: the original version looked for an age in
[3.5h, 5.25h] and printed [FAIL] otherwise. That is wrong -- a healthy
timer's age is uniformly distributed in [0, 5h), so ~70% of the time it
lands OUTSIDE that window and the probe reports a false "chain broken".
That is a false-positive generator: it would tell a future cron to
restart the proxy for no reason (and a restart interrupts the sister
KB's e2e probe -- see pitfalls 1/20).

The correct identification: the reload timer is the OLDEST thread other
than the main thread whose age is below RELOAD_INTERVAL. Request worker
threads are short-lived (seconds to a couple of minutes), so "oldest
sub-5h thread" is the timer. When the timer has just fired (<2 min old)
the identification is ambiguous, so we fall back to comparing the proxy's
in-memory doc count against the on-disk index.json -- if they match,
the reload demonstrably happened and the chain is alive.
"""
import datetime
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

PID = subprocess.check_output(["pgrep", "-f", "hermes-skill-proxy.py"]).decode().split()[0]
hz = os.sysconf("SC_CLK_TCK")
uptime = float(Path("/proc/uptime").read_text().split()[0])
now = datetime.datetime.now()

print("proxy PID =", PID)
print("now      =", now.strftime("%Y-%m-%d %H:%M:%S"))
print()
threads = []
for t in sorted(Path("/proc/%s/task" % PID).iterdir()):
    try:
        stat = (t / "stat").read_text()
        comm = (t / "comm").read_text().strip()
    except OSError:
        continue
    # field 22 (1-indexed) is starttime in clock ticks; the comm field can
    # contain spaces/parens so split after the last ')'
    rest = stat[stat.rfind(")") + 1:].split()
    start_ticks = int(rest[19])   # 0-indexed after the state field
    age = uptime - start_ticks / hz
    started = now - datetime.timedelta(seconds=age)
    threads.append((t.name, comm, started, age))
    print("tid=%-8s comm=%-10s started=%s  age=%.0fs (%.2fh)"
          % (t.name, comm, started.strftime("%Y-%m-%d %H:%M:%S"), age, age / 3600))

print()
RELOAD = 5 * 3600

# Identify the reload timer thread.
#
# The timer thread is born at the previous fire and lives exactly
# RELOAD_INTERVAL before firing again, so its age is ALWAYS in [0, RELOAD).
# Request worker threads are short-lived. Therefore the timer is the
# OLDEST non-main thread whose age is below RELOAD_INTERVAL.
#
# ⚠️ Do NOT look for a narrow age band (the original 3.5-5.25h window was
# wrong -- it false-positived ~70% of the time). See module docstring.
main_tid = str(PID)
candidates = [t for t in threads if t[0] != main_tid and t[3] < RELOAD * 1.05]
timer = None
if candidates:
    # oldest sub-RELOAD non-main thread
    timer = sorted(candidates, key=lambda x: -x[3])[0]

# Cross-check: does the proxy's in-memory index match the on-disk index?
# This is the ground truth -- if it matches, a reload demonstrably happened.
disk_docs = {}
mem_docs = {}
try:
    disk_docs = json.loads(
        Path.home().joinpath(".hermes/kb/inexbot/index.json").read_text(encoding="utf-8"))
except Exception as e:
    print("[WARN] 读磁盘 index.json 失败: %s" % e)
try:
    with urllib.request.urlopen("http://localhost:8643/health", timeout=15) as r:
        health = json.loads(r.read().decode())
    mem_docs = {k: v.get("docs") for k, v in (health.get("indexes") or {}).items()}
except Exception as e:
    print("[WARN] 读 proxy /health 失败: %s" % e)

print("磁盘 index.json : inexbot = %s" % len(disk_docs))
print("proxy 内存索引   : %s" % mem_docs)
print()

in_sync = mem_docs.get("inexbot") == len(disk_docs) and len(disk_docs) > 0

if timer is None:
    if in_sync:
        print("[OK] 重载链存活（内存索引与磁盘一致，且当前无待触发定时器线程）")
        print("  -> 磁盘条目已在内存索引中生效，无需 restart。")
    else:
        print("[FAIL] 未找到重载定时器线程，且内存索引与磁盘不一致")
        print("       -> 重载链可能已断裂：proxy 将永远停在旧索引上")
        print("       -> 修复：确认 schedule_reload() 的 finally 块还在（proxy repo）")
        print("       -> 部署：sudo -n systemctl restart hermes-skill-proxy.service")
        sys.exit(1)
    sys.exit(0)

tid, comm, started, age = timer
next_reload = started + datetime.timedelta(seconds=RELOAD)
delta = (next_reload - now).total_seconds()
print("[OK] 重载链存活：定时器线程 tid=%s" % tid)
print("  -> 上次触发 %s" % started.strftime("%Y-%m-%d %H:%M:%S"))
print("  -> 下次重载 %s  (在 %.0f 分钟后)" % (next_reload.strftime("%Y-%m-%d %H:%M:%S"), delta / 60))
print("  -> 内存/磁盘同步: %s" % ("是" if in_sync else "否（尚未到重载时间，属正常窗口）"))
print()
print("=> 磁盘 index.json 的新条目会在下次重载时进入内存索引。")
print("=> 若下轮 cron /health 的 docs 仍小于磁盘条目数 -> 查本脚本是否报 [FAIL]。")
