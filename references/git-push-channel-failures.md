# GitHub 推送通道故障：github.com:443 不稳 + socket 探针「假绿」

**适用**：两个 KB 的 cron 都要往 GitHub 推 commit，**都受影响**。
姊妹 KB `inexbot-knowledge-base` 与本 skill `inexbot-open-knowledge-base` 各有自己的
repo，但**共用同一个 github.com 主机**——443 挂了就是**两边一起挂**。

---

## 症状

```
fatal: unable to access 'https://github.com/inexbot/...': Failed to connect to github.com port 443 after 129573 ms: Connection timed out
fatal: unable to access 'https://github.com/inexbot/...': Error in the HTTP2 framing layer
```

**但同一台机器上**（2026-11-12 实测）：

```bash
curl -m 30 https://api.github.com/     # → 200（0.37s）✅ 出网正常
curl -m 30 https://open.inexbot.com/   # → 200（0.83s）✅ 出网正常
```

⇒ **不是整个 GitHub、不是 DNS、不是本机 git 配置**
（`git config --global --list` 无 proxy / 无 `url.*` 覆盖；env 无 `*_proxy`）。
**故障面精确到「github.com 这一台机器的 443 端口」**。

---

## 🔴 关键坑：socket 探针会「假绿」——探针通过 ≠ 真实传输可用

**这是 11-10 结论的重要修正**。11-10 的规则是「先跑 socket 探针，探针决定走哪条通道」；
11-12 实测发现：**443 的可达性是波动的**，短时间内探针可以全通，而真实 git 传输仍然超时。

| 时刻 | 443 socket 探针 | 真实 `git push` |
|---|---|---|
| 11:04（push 前探针） | **3/3 OK**（0.23s） | ❌ **失败**：`Failed to connect ... after 129573 ms` |
| 11:13（push 失败后复探） | **0/3 OK**（全 TimeoutError） | ❌ HTTPS 不可用 |
| 11:13（同一时刻） | 22 **3/3 OK**（0.09s） | ✅ SSH 通道可用 |

**⇒ 判据必须改成「push 失败后立即复探；失败即切 SSH」**，
**不能**因为「探针 3/3 通过」就认定 HTTPS 可用、然后停在长超时重试循环里。

**代价量化**：11-12 那轮把 **130 秒**浪费在一次注定失败的 HTTPS push 上。

---

## 处置流程

### 第 1 步：短超时试一次 HTTPS（**别一上来就等 130 秒**）

```bash
cd <repo> && timeout 200 git -c http.version=HTTP/1.1 push origin main
# -c http.version=HTTP/1.1  → 规避 HTTP/2 framing layer 报错
# timeout 200             → 给失败设上限，别让它拖满 130s+
```

失败后**不要**再跑一轮长超时重试 → 直接进第 2 步。

### 第 2 步：复探 443 + 验 SSH 认证

```bash
# 443 探针（TLS）
python3 -c  # ← cron 里禁止内联！用 scripts/check_git_channel.py
```

见下方「复用脚本」。

### 第 3 步：走 SSH 传输通道（**不改动 remote 配置**）

```bash
cd <repo> && timeout 120 git push git@github.com:owner/repo.git main:main
```

> ⚠️ **不要用 `git remote set-url` 换成 SSH** —— 那是**全局副作用**，
> 两个 KB 的 cron 共用同一份仓库配置，改了会影响对方。
> **用 `git push <url> <refspec>` 的一次性语法**即可。

### 第 4 步：验证「到底入库没有」—— 不要只看 push 的返回值

```bash
git fetch git@github.com:owner/repo.git main:refs/remotes/sshcheck/main
git merge-base --is-ancestor <your-commit> refs/remotes/sshcheck/main && echo "IN remote"
```

> ⚠️ **「push 返回 `Everything up-to-date`」≠「我们的工作不在 remote」**。
> 11-12 实测：SSH push 返回 `Everything up-to-date`，
> 但 `git log refs/remotes/sshcheck/main` 显示 remote HEAD 已前进到姊妹的新 commit，
> 我们的 commit **确实在历史里**（`merge-base --is-ancestor` = YES）——
> 是**姊妹在我们之前已代推**（良性竞态，见陷阱 4）。
> ⇒ **必须用 `merge-base --is-ancestor` 判定自己的 commit 在不在历史里**。

---

## ⚠️ 副作用：HTTPS fetch 失败会让 `origin/main` 跟踪 ref 陈旧

**现象**：SSH push 成功、commit 确实在远端，但：

```
$ git status -sb
## main...origin/main [ahead 1]      ← ← 误报「没推上去」
```

**根因**：`origin/main` 这个**本地跟踪 ref** 只在 `git fetch` 时更新。
HTTPS fetch 失败 → 没人更新它 → 它停在**上一次成功 fetch 时的旧 sha**。

**⇒ 下一轮 cron 会把「已推送」误判成「未推送」，重复劳动。**

**修法**（用 SSH fetch 拿到的 sha 手工对齐跟踪 ref）：

```bash
git fetch git@github.com:owner/repo.git main:refs/remotes/sshcheck/main
git update-ref refs/remotes/origin/main $(git rev-parse refs/remotes/sshcheck/main)
git status -sb          # → ## main...origin/main  ✅ 不再误报
```

> 💡 这只是**本地 ref 的对齐**，不改变任何仓库配置、不影响姊妹 KB。
> 比 `git fetch origin main`（走 HTTPS，正是会失败的那条路）可靠。

---

## ⚠️ push 失败 ≠ 工作没入库

commit 已在本地（`git log` 可见），只是没推上 remote。
**必须区分这两件事**，否则会误报「未提交」而重复劳动。

收尾判据：`git rev-parse HEAD` 与远端 sha 是否一致。

> ⚠️ **push 成功后 HEAD 可能已经不是你的 commit** —— 姊妹 KB 可能在你 push 期间
> 又提交了一次（11-09 实测：我的 `6e6c1cf` 之后多了姊妹的 `3a55008`）。
> **不要**因此判定自己的提交丢失，用
> `git merge-base --is-ancestor <your-commit> origin/main` 确认它**在**历史里即可。

---

## 复用脚本

`scripts/check_git_channel.py`（两个 KB 各有一份，内容相同）：
探 `github.com:443`（TLS）与 `github.com:22`（TCP）各 N 次，输出 OK/DEGRADED/UNREACHABLE。

```bash
/usr/bin/python3 ~/.hermes/skills/productivity/inexbot-open-knowledge-base/scripts/check_git_channel.py
```

**⚠️ 判读时记住「假绿」**：
探针 443 报 **OK 不代表 push 会成功** —— 真正的判据是**push 本身的结果**。
探针的用途是**在 push 失败后快速定性**（是不是 443 的问题、SSH 能不能走），
**不是**在 push 之前做「绿了就放心用 HTTPS」的保证。

---

## 与其他陷阱的关系

- **陷阱 15**（`--amend` 后 push → non-fast-forward）：**症状完全不同**，
  看错误尾部是 `non-fast-forward`（历史分叉，要 `reset --hard`）
  还是 `Failed to connect` / `timed out`（网络，走本文流程）。
  **别把两者混判。**
- **陷阱 5**（commit message 含中文被 tirith 拦）：与通道无关，但**推送前**就会卡住。
- **陷阱 4**（并发 commit 良性竞态）：解释「push 返回 Everything up-to-date」
  但 remote HEAD 已被姊妹推进——**用 `merge-base --is-ancestor` 判读，别重复劳动**。
