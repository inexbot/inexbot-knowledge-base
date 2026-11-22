# 上游 URL 形态变更 —— `.html` 后缀路由（2026-11-19 实测）

> ⚠️ **本文件记录的是「上游改了 URL 形态」这一类故障的通用诊断与修复流程。**
> 不只适用于 11-19 这次的 `.html` 后缀；上游任何一次改路由形态（加前缀、
> 换扩展名、强制尾斜杠）都适用同一套流程。

---

## ⭐ 0. 先读这一节：上游「URL 形态」是会反复漂移的变量（2026-11-21 实测）

**本文件 §二 描述的是 2026-11-19 那天的状态，不是永久状态。**
上游在 11-19 → 11-21 的两天内**切了两次，方向相反**：

| 日期 | 裸路径 `bare` | `bare + ".html"` | 目录页 `bare + "/index.html"` | 判定 |
|---|---|---|---|---|
| ~2026-11-18 及以前 | 200 | — | — | 裸路径路由 |
| **2026-11-19 / 11-20** | **404** | 200 | 200 | ⬅ **收紧为「只认后缀」** |
| **2026-11-21 起** | **200** | **200** | **200** | ⭐ **放宽为「两套并存」** |

2026-11-21 实测（抽样 **30 条真实 index 条目**）：
**裸形态 30/30 200，带后缀形态 30/30 200**；
姊妹 KB `open.inexbot.com` 裸路径仍 200（**未受影响**）。

### ⇒ 处置原则（照做，别自己推）

| 上游当前形态 | 该做什么 | 该**不**做什么 |
|---|---|---|
| **收紧**（裸 404 / 后缀 200） | 实施 §四 的全套修复（crawler + proxy + 6 个审计脚本） | ❌ 别只改 proxy 一个点 |
| **放宽**（两种都 200） | ⭐ **什么都不改** —— 现状（带后缀输出）已实测 74/74 全 200 | ❌ **绝不**因为「裸形态现在能用」就删掉 `url_suffix` 字段 / 把 proxy 改回裸形态 |

### ⚠️ 为什么「放宽」时也不能删兼容层

1. 上游**已经证明过**它会切路由形态（两天内两次，方向相反）⇒
   「今天能用」**不构成**「明天能用」的依据。
2. 一旦上游再次收紧，**删掉后缀 = 100% 引用链接 404** —— 正是 11-19 那轮，
   而且**表层检查会全绿**（`/health` 绿灯、检索链路 PASS、索引完整性 PASS、
   crawler 报「561/561 成功」），**只有实网引用链接检查能抓到**。
3. **保留后缀输出在两种路由下都可达** ⇒ 保留是**严格更稳**的选择，**零成本**。

### ⚠️⚠️ 探测必须用 `index.json` 的真实条目，别手拼 URL

**2026-11-21 实测踩到**：手拼的路径**可能根本不是 index 里的一条**
（例：手拼 `/zh/操作手册` 当普通页 + `.html` → **404**），
于是错误地得出「上游没放宽」的结论。

| 探测对象 | 裸形态 | 带后缀形态 |
|---|---|---|
| **手拼** `/zh/操作手册` | 200 | **404** ← 误判来源 |
| **index 里的真实条目**（`url_suffix=.html`） | **200** | **200** |

⇒ **URL 必须从 index.json 取**，再按 `url_suffix` 字段拼出「带后缀」形态，
两种都打一次。

### 通用通则

> **修复方向永远是「让链接在多种形态下都可达」或「让链接跟随上游当前形态」，
> 绝不**是「因为当前形态能用就删掉兼容层」。

📌 完整判读表见共享 pitfalls **§陷阱 43**（`references/shared-proxy-service-pitfalls.md`）。

---

## 一、症状：表层全绿，用户拿到的是坏链接

11-19 现场（doc.inexbot.com）：

| 检查 | 结果 | 真相 |
|---|---|---|
| `crawler.py` | 561/561 成功 | 增量爬虫，raw/md 命中缓存就跳过，**对 URL 形态变化完全无感** |
| `/health` | ok, docs=561 | 只看条目数 |
| 索引完整性 | 全 PASS | key 仍然合法、md 仍然可定位 |
| 检索链路 | 无静默降级 | 正文读取完全正常 |
| **引用链接实网** | **60/60 全 404** | ⬅ **用户点每一个链接都是 404** |

**关键认识**：这类故障**不影响检索、不影响正文、不影响 LLM 回答质量** ——
只影响回答末尾的引用链接。**「表层全绿」恰恰是这类故障的特征。**

---

## 二、根因

上游 `doc.inexbot.com` 从「裸路径路由」改成「`.html` 后缀路由」
（**⚠️ 这是 2026-11-19/11-20 期间的状态；2026-11-21 起上游已放宽为「两套并存」，
见 §0 —— 本节描述的是「收紧」那一档的根因与修法**）：

| 页面类型 | 旧（2026-11-18 及以前） | 收紧档（2026-11-19/11-20） |
|---|---|---|
| 普通页 | `/zh/产品资料/控制系统/T30示教器` → 200 | `/zh/产品资料/控制系统/T30示教器` → **404**<br>`/zh/产品资料/控制系统/T30示教器.html` → 200 |
| 目录页 | `/zh/产品资料/` → 200 | `/zh/产品资料/` → **404**<br>`/zh/产品资料/index.html` → 200 |

实测（20 条普通页 + 15 条目录页）：

```
bare        : {404: 20}
bare+.html  : {200: 19, 404: 1}     ← 那 1 条是目录页
bare/index.html: {404: 19, 200: 1} ← 目录页只有 /index.html 有效
```

### 为什么 index 里的信息不够

`index.json` 的 key 是**去掉后缀的相对路径**（`/zh/产品资料/`），
由 crawler 的正则 `(?:/zh/.*?)(?:\.html)?/?$` 归一化而来。

这个归一化把**「这页是目录页还是普通页」的信息丢掉了** ——
两条 URL 后缀规则不同（`.html` vs `/index.html`），但 key 长得一样。

⇒ **proxy 单靠 key 无法还原正确 URL** ⇒ 必须额外携带这个信息。

---

## 三、判别方法（下次遇到同类问题照做）

### 3.1 确认是「上游改路由」而不是「探针自己错了」

```python
# 对同一批 key 试三种形态，看哪种 200
bare          = BASE + quote(key, safe="/%")
with_html     = bare + ".html"
with_index    = bare.rstrip("/") + "/index.html"
```

- `bare` 全 404、`with_html` 全 200 ⇒ **上游加了 `.html` 后缀**
- `bare` 全 404、`with_index` 全 200（且只有目录页这样）⇒ **目录页要 `/index.html`**

> ⚠️ **务必同时确认姊妹 KB 未受影响**（11-19 实测 `open.inexbot.com` 裸路径仍 200）。
> **只有 doc 侧变了** ⇒ 修复必须**按 KB 分派**，绝不能做成全局规则。
> 把 `inexbot` 验证过的规则套到 `inexbot-open` 上 ⇒ 大面积假回归。

### 3.2 从 sitemap 拿到「目录页 vs 普通页」的唯一线索

sitemap 里的**原始 URL 形态**就是判据：

- 以 `/` 结尾 ⇒ **目录页** ⇒ 后缀 `/index.html`
- 以 `.html` 结尾 ⇒ **普通页** ⇒ 后缀 `.html`

⚠️ sitemap 是**单行 XML**，`grep -c "<loc>"` 返回 **1**（行数不是出现次数），
必须用 `re.findall`（见 §陷阱 32 / `check_sitemap_count.py`）。

### 3.3 全量验证派生规则

11-19 实测：按 sitemap 形态派生 URL，**561/561 全 200**，非 200 = 0。
⇒ 规则正确，可放心用它生成链接。

---

## 四、修复方案（11-19 已实施）

### 4.1 `crawler.py` —— 把 URL 后缀随 index 落盘

```python
# fetch_vitepress_metadata() 里
rel_links = []
suffix_map = {}
for u in links:
    m = re.search(r'(/zh/.*?)(?:\.html)?/?$', u)
    if m:
        rel = m.group(1)
        rel_links.append(rel)
        suffix_map[rel] = "/index.html" if u.endswith("/") else ".html"
# ...
return {"links": unique, "hash_map": hash_map, "html": html,
        "suffix_map": suffix_map}
```

并在 `build_search_index()` 的每条 entry 里写入：

```python
"url_suffix": page.get("url_suffix", ".html"),
```

⚠️ **`build_search_index()` 是共享函数** —— 姊妹 KB 也调它。
所以**默认值必须是 `.html`**，且姊妹 KB 的 index 没有这个字段时
`item.get("url_suffix", "")` 返回空串 ⇒ 不加后缀 ⇒ 行为不变。

### 4.2 proxy `_kb_url()` —— 支持后缀，且按 KB 分派

```python
def _kb_url(base_url: str, path: str, suffix: str = "") -> str:
    if "%" in path:
        url = base_url + url_quote(path, safe="/%")
    else:
        url = base_url + url_quote(path, safe="/")
    if suffix:
        if suffix.startswith("/"):
            return url.rstrip("/") + suffix   # 目录页
        return url + suffix                     # 普通页
    return url
```

调用方：

```python
"url": _kb_url(base_url, path, item.get("url_suffix", "")),
```

`KB_CONFIGS` 里加 `"url_suffix_mode": "html"`（inexbot）/ `"none"`（inexbot-open）
用于**显式声明**，但真正生效的是 **index 条目里的 `url_suffix` 字段**
（因为「目录页还是普通页」是**逐条**信息，不能靠 KB 级开关表达）。

### 4.3 审计脚本必须同步（否则造出假回归）

**这是本次最花时间的部分** —— 6 个脚本都要改：

| 脚本 | 改法 |
|---|---|
| `check_citation_links.py` | `kb_url(k, index[k].get("url_suffix", ".html"))`；**并把全部目录页强制并入样本**（只有 15 条，随机抽几乎抽不到，而它们恰是最易写错的那类） |
| `check_crawl_state.py` | 抽样 URL 加后缀，否则 100% 报 HTTP404 —— 看起来像「上游全挂了」，其实是**探针自己没跟上** |
| `check_retrieval_chain.py` | url→key 归一化要**先剥后缀**（`/index.html` 或 `.html`），否则 561 条全「md not found」 |
| `check_url_to_index_key.py` | 同上；且**目录页要试「带尾斜杠」和「不带」两种 key**（根目录页 key 是 `/zh/`，剥完 `/index.html` 只得 `/zh`） |
| `scan_kb_topic.py` | 新增 `official_url(base_url, key, val)`，链接不再裸拼 `base_url + key` |
| `retrieve.py` | `format_result()` 里按 `url_suffix` 拼链接 |

### 4.4 `rebuild_from_cache.py` —— 重建时也要拿 URL 形态

改了 index 结构后重建，**不能只从本地 key 推断** —— 目录页信息已经丢了。
必须**再取一次 sitemap**（1 次 GET，不重抓正文）：

```python
def fetch_suffix_map():
    try:
        meta = C.fetch_vitepress_metadata()
        return meta.get("suffix_map", {})
    except Exception as e:
        print(f"  WARN: sitemap 获取失败（{e}），退回按 key 推断后缀")
        return {}
```

11-19 实测：重建 561/561 成功，index 从 1,735,196 → 1,756,935 bytes。

---

## 五、⚠️ 顺带修掉的两个假阳性

### 5.1 字面零宽字符被吞 → 「ZWSP 条目数 = 全量」

`rebuild_from_cache.py` 里原本是 `ZWSP = ""`（字面 U+200B 被工具链**静默吞掉**
变成空串）⇒ `"" in title` **恒为 True** ⇒ 报「561 条含 ZWSP」。

实测 index 里**真实含 U+200B 的条目 = 0**。

**修法**（skill 里已有通则，这里再强调一次）：

```python
ZWSP = chr(0x200B)
```

或 `"[" + "".join(chr(c) for c in (0x200B, 0x200C, 0x200D, 0xFEFF)) + "]"`

**审计方法**（可复用）：用 `ast` 扫所有脚本的 ZWSP 类常量，
若是 `ast.Constant` 且值 == `""` ⇒ **BUG**；若是 `ast.Call`（`chr(...)`）⇒ 安全。

11-19 实测两个 KB 的全部 ZWSP 常量现已安全。

### 5.2 `check_crawl_state.py` 的 `HTTP404: 25/25`

漂移探针用 `urljoin(BASE_URL, k)` 拼 URL（裸路径）⇒ 全部 404。
**判读陷阱**：看到「抽样 25 页 → 100% HTTP404」**先怀疑探针自己**，
再怀疑上游。

---

## 六、⚠️ 本次教训：修复必须**先部署 + 先提交**，再写报告

11-19 的收尾被工具调用次数上限打断，导致：

- ❌ proxy **未重启** ⇒ 磁盘上的补丁没上线，**用户当前仍拿到 404 链接**
- ❌ 两仓库**未 commit / 未 push** ⇒ 下轮读到的是旧版代码
- ❌ 报告正文写了「已修复」但实际未部署 ⇒ **与 §0.6/§0.7 描述的跨 session 泄漏形态完全一致**

⇒ **第 6 步（修复 → 部署 → 回归）的顺序不能省**，尤其是：

```
改 → 验证 → 重启 proxy → 回归 → commit → push → 写报告正文
```

**「改了磁盘上的文件」≠「用户拿到的是好结果」。**
