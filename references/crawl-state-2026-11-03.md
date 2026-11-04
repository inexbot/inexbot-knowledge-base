# 2026-11-03 爬取基线快照（inexbot KB）

**结论**：内容侧**完全稳态**（558 篇，第 15 次连续持平，index 逐字节未变）；
链路侧**新暴露一个偶发 502**（proxy 300s timeout < gateway 900s provider timeout）。

---

## 一、爬取结果

```bash
/usr/bin/python3 ~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/crawler.py
```

| 项目 | 值 |
|---|---|
| 爬取页数 | **558 / 558 成功，0 失败** |
| 耗时 | **3:00.9** |
| 网络请求 | **0**（全部命中 `raw/` 缓存） |
| `index.json` | **1,722,769 bytes**，sha256 `d565c39c433370c3e66ff8f1abd3e0c0cb42cf442f9fd88df922fca94d21d523` |
| md / raw | 558 / 558（missing 0，**orphan 0**） |
| 漂移 verdict | **IDENTICAL** —— 抽样 25 页全部 `SAME` |
| `meta.yaml` version | `20261103` |

索引与 11-02 基线**逐字节相同** → **558 篇连续第 15 次持平**。
index mtime（11-03 11:04:33）晚于 proxy 启动时间（10-31 11:36:48），
但**索引内容未变** → **无需重启 proxy**（判断依据是「内容变没变」，不是「mtime 新不新」）。

---

## 二、验证闭环（`[inexbot]` 分组全绿）

| 检查 | 结果 |
|---|---|
| `verify_kb.py` | **`[inexbot]` 10/10 PASS**；`[inexbot-open]` 4 FAIL 与 11-02 逐项一致（非新回归） |
| 独立完整性审计 | 零长度 snippet 0 / `Not Found` 0 / 空标题 0 / 零宽字符 0 / 裸 `%` 0 / md 空壳页 0 / `path != key` 0 |
| 孤儿 md 精确计数 | **0**（558 可达 − 558 文件） |
| slug 契约 | **558/558**（复用 proxy `_md_slug_candidates()`，自己拼 `.md` 后缀） |
| 检索链路 | 35 条结果：**snippet_len == 800 为 0**、**双重编码 `%25` 为 0**；8 条短正文经复核均为上游单行占位页 |
| 内存 vs 磁盘 | **token 级 0 不一致**（558↔558，无单边 key，word_counts 齐全） |
| 引用链接实网 | `verify_kb` 抽样 **12/12 HTTP 200**；独立复测唯一高风险 `&` URL → **HTTP 200（464 KB）** |
| proxy 服务 | `/health` ok（558 + 799）、`Unknown key` **0**、HTTP 500 **0**、`NRestarts=0` |
| 环境变量 | 4 个变量在 `/proc/<pid>/environ` 全部到位 |
| 重载链 | **存活** —— 定时器线程创建于 **11-03 09:37:34**（= start+22h，第 5 次 5h 排期） |
| 端口 | 干净，仅 8643 + 8642 |

---

## 三、🔴 新发现：偶发 502（proxy 300s < gateway 900s）

### 现象

- 本 KB e2e 探针：**11/12 成功，1 次 FAIL** —— HTTP 502，耗时 **300.1s**，
  body：`Read timed out. (read timeout=300)`
- **姊妹 KB 独立跑的探针同时命中同样的 502 / 300.1s**
- proxy 自 10-31 启动：73 次 chat/completions 中 **3 次 502**（11-02 基线 **0 次**）
- 同期 `/health` 绿灯、检索 PASS、引用链接 200、index 逐字节未变 → **只有 e2e 探针能抓到**

### 精确定位

| 层 | timeout | 位置 |
|---|---|---|
| proxy → gateway | **300s** | `hermes-skill-proxy.py` `HERMES_TIMEOUT`（默认 300） |
| gateway → provider | **900s** | `agent/anthropic_adapter.py` `_read_timeout`（默认 900.0） |
| gateway 整轮 | **1800s** | `config.yaml` `agent.gateway_timeout` |

**决定性证据**：请求 11:08:13 到达 → proxy 11:13:13 返回 502（**恰好 300.0s**）；
**同一个请求在 gateway 侧 11:29:23 才完成（1270s，HTTP 200）**，晚 970s。
另一个请求到 11:31 仍挂起（>1363s）。

→ **请求没丢，是 proxy 提前放弃。** 正常延迟区间 33–164s；直打 8642 量得 98.0s / 46.1s 均 200。

### 待办（本轮**未**实施）

1. **降本（治根）**：限制注入 context 体积（当前 top-5 × 2 KB 全量注入，
   system prompt 可达 20k–60k 字符）
2. **兜底（治标）**：unit 里显式 `Environment="HERMES_TIMEOUT=1800"`，与 `agent.gateway_timeout` 对齐
3. **体验**：proxy 侧对 timeout 做一次自动重试

> 完整诊断方法与判读表见 `references/shared-proxy-service-pitfalls.md` §陷阱 17。

---

## 四、本轮自己脚本里的一个误判（已修正）

首次 token 比对报 **1116 条不一致**（desc 558 + content 558）—— 实为**字段名写错**：
用了 `d.get("desc")` / `d.get("content")`，磁盘实际字段是 **`description`** / **`content_snippet`** →
切成空 token 集 → 全量假阳性。

按 proxy 真实规则修正后 = **0 不一致**。
**「整齐的 558」本身就是字段名错的指纹**（真实数据损坏不会这么齐）。
详见 `references/shared-proxy-service-pitfalls.md` §陷阱 18。

---

## 五、⚠️ 未完成事项（下一轮先接手）

1. **本 skill 仓库仍有 11-02 轮遗留的未提交改动**（本轮独立 `git status` 实测）：
   - `SKILL.md`（version 2.14.0 → **2.15.0**）
   - `references/shared-proxy-service-pitfalls.md`（+114 行：陷阱 15 / 16）
   - 合计 2 files / +128 −4 —— **陷阱 14 又一次复现**
2. **未实施**第三节的 502 修复，**未重启** proxy
3. 本轮在 `~/.hermes/kb/inexbot/` 留下 6 个临时探针脚本
   （`_round_probe_1103.py` / `_round_probe_tokens_1103.py` / `_round_audit_1103.py` /
   `_round_urlcheck_1103.py` / `_round_502diag_1103.py` / `_round_latency_1103.py`）
   —— 在 KB 数据目录内，**不影响 index/md/raw**，但属应清理残留
   （⚠️ cron 下 `rm` 会被 `delete in root path` 拦，见陷阱 7）
4. 姊妹 KB `inexbot-open` 的 4 项 `verify_kb.py` FAIL 仍未闭环

---

## 六、基线速查

| 项 | 值 |
|---|---|
| docs | **558**（连续第 15 次持平） |
| index.json | **1,722,769 bytes** |
| index sha256 | `d565c39c433370c3e66ff8f1abd3e0c0cb42cf442f9fd88df922fca94d21d523` |
| proxy PID / 启动 | 1792095 / 2026-10-31 11:36:48 |
| 端到端 | **11/12**，1 次 502 @ 300.1s（见第三节） |
| 正常延迟区间 | 33–164s |
