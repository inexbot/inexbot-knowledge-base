# inexbot KB 基线快照 — 2026-11-20

> 本轮重点：**把 11-19 那轮「已写盘、未上线、未入库」的 `.html` 后缀路由修复真正闭环**
> （commit → push → 部署 → 回归），并修掉一个**「辅助函数定义了但没接进调用链」**的假修复。

---

## 1. 页面数与索引基线

| 项 | 值 | 对比 11-19 |
|---|---|---|
| 页面总数 | **561** | 持平 |
| index.json | **1,756,935 bytes** | 持平（与 11-19 逐字节相同） |
| index sha256 | `89baf46193cdf015b3a4182887fff19b400bcabe649748d385b5dc7e5dda6f16` | 同上 |
| `url_suffix` 分布 | `.html` **546** / `/index.html` **15** | 同上 |
| md / raw 文件数 | 561 / 561 | 同上 |

⇒ **上游零变化**：sitemap zh `<loc>` **561** == 本地 index **561**（1108 总 loc）。
⇒ 漂移探针抽样 25 页 → **25/25 SAME**（连 IMG_ONLY 都没有）。
⇒ 连续第 **30** 次条目数持平。

---

## 2. 本轮闭环：11-19 那轮的「未完成清单」全部完成

上一轮（11-19）因工具调用次数上限中断，修复停在「**已写盘、未部署、未 commit**」状态。
本轮逐项核验并完成：

| 上轮待办 | 本轮结果 |
|---|---|
| `check_url_to_index_key.py` 候选 key 修复未验证 | ✅ **发现是「假修复」**（见 §3）→ 真修复后 **93/93** |
| `verify_kb.py` 一键回归未跑 | ✅ 已跑，`[inexbot]` 分组 **0 FAIL** |
| **proxy 未重启**（用户仍拿到 404 链接） | ✅ 已重启，**新 PID 2016323**（11:04:53 启动） |
| 两仓库未 commit / 未 push | ✅ 均已 commit + push + §0.9 直查远端确认 |
| 姊妹 e2e 探针仍在运行，未贸然 restart | ✅ 先确认姊妹仅在跑 crawler（无探针），才 restart |

### 部署证据

| 项 | 值 |
|---|---|
| proxy commit | `b9def11` `fix(proxy): support per-KB url suffix for citation links` |
| proxy push | `abb129c..b9def11  main -> main` ✅ |
| §0.9 直查远端 | `merge-base --is-ancestor` = **YES**；`HEAD` == `refs/remotes/sshcheck/main` == `b9def116e167cd7e2d958addc45abb6bc7b91cf5` |
| 新 PID | **2016323**，启动 `2026-11-20 11:04:53`（**晚于**补丁 mtime `2026-11-19 11:18` ⇒ 线上已带补丁） |
| 运行进程 environ | `PROXY_PORT=8643` / `HERMES_URL=http://localhost:8642` / `SKILL_NAME=inexbot-knowledge-base` / `HERMES_TIMEOUT=1800` / `HERMES_API_KEY len=21 sha12=23760f4462da` |
| restart 后健康检查 | 第 1 次 Connection refused，第 2 次 **HTTP 200**（带重试，符合 §陷阱 2） |

---

## 3. ⭐ 本轮新发现：**「辅助函数定义了但没接进调用链」** ⇒ 11-19 的修复是假修复

11-19 那轮为「目录页 key 形态」写了 `norm_key_candidates()`（返回候选 key 列表），
但主流程**仍然是** `key = norm_path(path, kb)`（单值）
⇒ **`norm_key_candidates` 一次都没被调用**。

**症状极像真故障**：反查守卫报 `92/93`，且明确点名漏的是根目录页 `/zh/index.html`；
但**检索链路完全正常**（无静默降级、md 全部可定位）。

**为什么没被任何检查抓到**：差异只影响 15 条目录页里的 1 条
⇒ 命中率 92/93 ≈ 99% ⇒ **任何「看总数」的健康检查都会放过它**。

**修法**（调用点换成候选列表）：

```python
cands = norm_key_candidates(path, kb)
hit_key = next((c for c in cands if c in idx), None)
```

**实测**：`92/93 → 93/93`，`no-md lookup 1 → 0` ✅

📌 已写入共享 pitfalls **陷阱 40**（`references/shared-proxy-service-pitfalls.md`）。

> 💡 **姊妹 KB 独立发现了同一个 bug**（其 commit `f9a58d1`，2026-11-20 11:07），
> 根因与修法完全一致 ⇒ **双向独立验证**。

---

## 4. 全部检查结果

| 检查 | 结果 |
|---|---|
| `crawler.py` | **561/561 成功**，失败 0 |
| `check_sitemap_count.py` | 上游 zh **561** == 本地 **561** ✅ |
| `check_crawl_state.py` | md 561 / raw 561 / 缺失 0 / 孤儿 0 / 空标题 0 / ZWSP 0；漂移 **25/25 SAME**；health OK |
| `check_citation_links.py` | **74/74 全 200**（含强制并入全部目录页），404 = 0，网络错误 = 0 |
| `check_retrieval_chain.py` | **PASS** — 真静默降级 **0**；全文命中 34 / 4000 上限 26 / 短页全文 9 / md 全部可定位 |
| `check_url_to_index_key.py` | **93/93** ✅（本轮修好）；静默降级 0 / no-md 0 |
| `check_token_consistency.py` | 两个 KB **token 级不一致 = 0** |
| `check_proxy_env.py --units` | 线上 5 变量 == 代码默认值 == `/etc` unit == repo 模板，**三处一致** ✅ |
| `check_short_snippet_class.py` | 132 条短 snippet **全是「常见问题/伺服报错」占位页**，**空壳页 0** |
| `check_reload_timer.py` | 重载链存活；timer age 0.04h，下次重载 16:05；内存/磁盘同步（561 == 561） |
| `verify_kb.py` | `[inexbot]` 分组 **0 FAIL**；4 项 FAIL 全在 `[inexbot-open]` 分组（姊妹 KB 修复中间态） |
| journal（按进程启动时间切片） | **0×500、0×502、0×Unknown key name** |
| 端到端 e2e | **12/12 全 200**，0 次 500/502；最慢 123.1s |

---

## 5. ⭐ 共享 pitfalls 同步（两个 KB 的文件此前已分叉）

发现姊妹 KB 的 `shared-proxy-service-pitfalls.md` 被**并发 patch 拼坏**（§陷阱 31）：
两个 `陷阱 39` 标题并存，「SKILL.md 顶破上限」与「上游改 URL 形态」两节的正文**逐行交错**，
甚至出现 `SKILL.md content is 106,244 characters` 插在代码块中间。

**处置**：
1. 依据姊妹 KB 的**可读片段**重建「陷阱 41（SKILL.md 字符数上限）」与「陷阱 42（两 KB 共用 e2e 日志文件）」
2. 与本 KB 的「陷阱 39（上游改 URL 形态）」「陷阱 40（辅助函数没接进调用链）」合并
3. 重新编号 ⇒ **42 节，无重复编号**，`check_shared_pitfalls_structure.py` 通过

> ⚠️ **陷阱 41 的重要更正**：`wc -c` 给的是**字节数**，`skill_manage` 的上限是**字符数**。
> 本 KB 实测 **79,806 字符 / 127,090 字节** ⇒ 按字符数**远未超限**。
> 用 `wc -c` 直接比 100,000 会**误判为超限**（中文 1 字 = 3 字节）⇒ 判活请用**字符数**。

---

## 6. 本轮入库

| 仓库 | commit | push 验证 |
|---|---|---|
| `inexbot-knowledge-base` | `0072e07` `fix(audit): wire norm_key_candidates into lookup loop, sync shared pitfalls` | `51a19bf..0072e07 main -> main`；§0.9 直查远端 **HEAD == REMOTE == `0072e079c11e1a2c96c31cb91d00261cd61ea5d5`**，ANCESTOR YES |
| `hermes-skill-proxy` | `b9def11` `fix(proxy): support per-KB url suffix for citation links` | `abb129c..b9def11 main -> main`；§0.9 直查远端 **HEAD == REMOTE == `b9def116e167cd7e2d958addc45abb6bc7b91cf5`**，ANCESTOR YES |

**工作树干净**（`git status -sb` 无 `M` / `??`），**无跨 session 泄漏**。

---

## 7. 遗留

- **姊妹 KB `inexbot-open` 的 4 项 FAIL**（md/raw 文件数 1890 vs index 832、零长度 snippet、含图 md 反查 73/177）：
  属**姊妹 KB 自己的修复中间态**（其 crawler 当时正在跑）。**不是本 KB 的回归**。
  ⚠️ 但姊妹 KB 那份 `shared-proxy-service-pitfalls.md` 的**交错损坏**仍需它自己修复 ——
  本 KB 已在自己的副本里重建干净版本，但**姊妹 KB 的副本仍带损坏内容**。
- 本 KB 无未完成项。
