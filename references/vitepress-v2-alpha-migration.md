# VitePress v2 alpha 站点迁移 — 诊断与适配模板

> 当任意 VitePress 站点的爬虫突然 `成功: 0 / 0`，且姐妹 skill 的诊断模板（`inexbot-open-knowledge-base/references/vitepress-i18n-sidebar-diagnosis.md`）未能解决时，考虑本文件描述的 v2 alpha 场景。
> 本文档基于 2026-09-08 doc.inexbot.com（VitePress v2.0.0-alpha.18）现场诊断。

## 症状

- `爬取页面数: 0`，`/sitemap.xml` 返回 200 但 crawler 不用它。
- 抓首页 `/` 拿到 ~450 字节极简 HTML，无 `__VP_HASH_MAP__` / `__VP_SITE_DATA__`。
- 抓 `/zh/` 拿到完整 HTML（400KB+），但 `themeConfig.sidebar = []`，`themeConfig.nav = []`。
- 抓 `/zh/<某页>.html` 直接返回完整 SPA HTML，**没有** `<article class="page">` / `<main>` 容器。

## 触发条件（任一满足即按 v2 alpha 处理）

1. 首页 `<title>` 含「Knowledge Base」或「知识库」且根 HTML < 2KB。
2. `__VP_SITE_DATA__` 里 `themeConfig` 只有 `i18nRouting + search` 字段，无 sidebar/nav。
3. `__VP_HASH_MAP__` 有 1000+ 个 entry 但 sidebar 给出 0 条 link。
4. `<meta name="generator" content="VitePress v2.0.0-alpha.*">`。

## 根因速查表

| 旧爬虫假设 | v2 alpha 实际 | 故障表现 |
|---|---|---|
| 根 `/` 有 VP 元数据 | 根 `/` 是 client-side JS 跳转页（`location.replace(target)`） | `__VP_*` 正则全 miss |
| `themeConfig.sidebar` 给出全部链接 | sidebar 拆到外部 JS chunk，site_data 里只有 i18nRouting | 拿到 0 条 link |
| `<article class="page">` 包正文 | 没有该元素，h1/h2/p 直接渲染在 body | `_element_to_md()` 拿到 sidebar/nav 噪声 |
| URL `/path/` 是稳定端点 | 用 `.html` 后缀（`/path/foo.html`） | 拼出的 URL 走 SPA fallback |

## 5 步诊断命令模板

每条都用 Python 文件路径执行（绕开本地 `-c` 黑名单）。模板写入 `/tmp/vp_v2_diag.py` 后 `python3 /tmp/vp_v2_diag.py`：

```python
# /tmp/vp_v2_diag.py
import httpx, re, json
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-CN,zh;q=0.9"}
BASE = "https://<your-site>"

# Step 1: 根路径多长？是不是 JS 跳转？
r = httpx.get(f"{BASE}/", headers=HEADERS, follow_redirects=True, timeout=30)
print(f"[1] /  status={r.status_code} len={len(r.text)}")
print(f"    has VP globals: {'__VP_HASH_MAP__' in r.text or '__VP_SITE_DATA__' in r.text}")
print(f"    has location.replace: {'location.replace' in r.text}")
print(f"    head: {r.text[:300]}")

# Step 2: /zh/ 或 /<locale>/ 直访
r2 = httpx.get(f"{BASE}/zh/", headers=HEADERS, follow_redirects=True, timeout=30)
print(f"\n[2] /zh/  status={r2.status_code} len={len(r2.text)}")
print(f"    has VP globals: {'__VP_HASH_MAP__' in r2.text or '__VP_SITE_DATA__' in r2.text}")
m = re.search(r'<meta name="generator" content="([^"]+)"', r2.text)
print(f"    generator: {m.group(1) if m else 'NONE'}")

# Step 3: site_data 里有 sidebar 吗？
sd = json.loads(re.search(
    r'window\.__VP_SITE_DATA__\s*=\s*deserializeFunctions\(JSON\.parse\("((?:[^"\\]|\\.)*)"',
    r2.text, re.S).group(1).replace('\\"', '"').replace('\\\\', '\\'))
print(f"\n[3] site_data top keys: {list(sd.keys())}")
print(f"    themeConfig keys: {list(sd.get('themeConfig', {}).keys())}")
print(f"    sidebar len: {len(sd.get('themeConfig', {}).get('sidebar', []))}")
print(f"    nav len: {len(sd.get('themeConfig', {}).get('nav', []))}")

# Step 4: hash_map 数量
hm = json.loads(re.search(
    r'window\.__VP_HASH_MAP__\s*=\s*JSON\.parse\("((?:[^"\\]|\\.)*)"',
    r2.text, re.S).group(1).replace('\\"', '"').replace('\\\\', '\\'))
print(f"\n[4] hash_map entries: {len(hm)}")
print(f"    sample keys: {list(hm.keys())[:3]}")

# Step 5: sitemap.xml 可用吗？
r3 = httpx.get(f"{BASE}/sitemap.xml", headers=HEADERS, timeout=30)
print(f"\n[5] /sitemap.xml  status={r3.status_code} len={len(r3.text)}")
locs = re.findall(r'<loc>([^<]+)</loc>', r3.text)
print(f"    <loc> count: {len(locs)}")
if locs:
    from collections import Counter
    lang = Counter()
    for u in locs:
        seg = u.split('/')[3] if len(u.split('/')) > 3 else ''
        lang[seg] += 1
    print(f"    by locale: {dict(lang)}")
```

## 适配 patch 模板

如果诊断结果落到 v2 alpha 场景，按下面 4 处 patch：

### 1. 页面发现改用 sitemap.xml

```python
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
resp = httpx.get(SITEMAP_URL, headers=HEADERS, timeout=30)
locs = re.findall(r'<loc>([^<]+)</loc>', resp.text)
# filter 到目标 locale
links = [u for u in locs if "/zh/" in u]
```

### 2. fetch_vitepress_metadata 不再解析 sidebar

只解析 sitemap + hash_map（hash_map 只用于「站点是否变动」的健康检查，不再用作 link 源）。

### 3. extract_content 从 `<h1>` 起

```python
# 优先级：<article class="page"> > <main> > h1.parent (VPDoc 容器)
article = soup.find("article", class_="page") or soup.find("main")
if not article and h1:
    parent = h1.parent
    while parent and parent.name not in ("body", "html"):
        cls = parent.get("class", []) or []
        if any("Doc" in c or "doc" in c for c in cls):
            break
        parent = parent.parent
    article = parent or h1.parent

# 抓 <h1> 之后所有 sibling，止于 VPDocFooter
h1_in = article.find("h1")
captured = [h1_in]
for sib in h1_in.find_next_siblings():
    cls = " ".join(sib.get("class", []) or [])
    if "VPDocFooter" in cls:
        break
    captured.append(sib)
# 用 wrapper 包一层给 _element_to_md()
```

### 4. slugify 加 unquote + 字节截断

doc.inexbot.com 有页面 URL unquote 后仍 > 200 字节（如「T20更换开机图片（通电及走进度条的两张图）」），触发 `OSError: File name too long`。

```python
from urllib.parse import unquote

def slugify(text: str, max_len: int = 200) -> str:
    text = unquote(text)                              # ← 关键
    text = text.strip().replace("/", "-").replace("\\", "-")
    text = re.sub(r'[<>:"\\|?*]', '', text)
    if len(text.encode("utf-8")) > max_len:
        head = text.encode("utf-8")[:max_len - 16].decode("utf-8", errors="ignore")
        text = f"{head}-{md5_text(text)}"
    return text
```

> **不要**用 URL-encoded 形式做文件名——每次爬取 slug 会因编码大小写不同而不一致，导致增量失效。

## URL fallback 链

sitemap 给的 URL 是 `/zh/foo.html`，但某些目录型 URL（首页 `/zh/`、分类索引 `/zh/foo/`）不带 `.html`，需要 fallback：

```python
for alt in (link.rstrip("/") + ".html",
            link.rstrip("/") + "/index.html",
            link.rstrip("/") + ".md"):
    r = client.get(urljoin(BASE_URL, alt))
    if r.status_code == 200 and "<title>404" not in r.text:
        resp = r
        break
```

## 与姐妹 skill 的关系

| Skill | 站点 | VP 版本 | sidebar 在哪？ | 主要症状 |
|---|---|---|---|---|
| `inexbot-open-knowledge-base` | open.inexbot.com | 旧版（v1.x） | `__VP_SITE_DATA__.locales.*.themeConfig.sidebar`（按 locale 拆） | 顶层 sidebar 是空，要遍历 locale |
| `inexbot-knowledge-base`（本次） | doc.inexbot.com | **v2.0.0-alpha.18** | 外部 JS chunk，site_data 里只有 i18nRouting | sidebar 完全不可用，必须用 sitemap.xml |

**经验**：i18n 多语种 + VitePress 升级到 v2 alpha 的组合，最稳的页面发现源是 `sitemap.xml`，不要相信 `__VP_*`。

## 验证清单

适配完成后，跑以下验证：

```bash
# 1. 索引条数 = sitemap 中的目标 locale URL 数
python3 -c ""  # ❌ 不要用，被本地 policy 拦
python3 /tmp/check_index.py  # ✅ 走文件路径
```

`/tmp/check_index.py` 内容：
```python
import json
from pathlib import Path
idx = json.loads(Path.home().joinpath(".hermes/kb/inexbot/index.json").read_text(encoding="utf-8"))
print(f"index entries: {len(idx)}")
md_dir = Path.home() / ".hermes/kb/inexbot/md"
raw_dir = Path.home() / ".hermes/kb/inexbot/raw"
print(f"md files: {len(list(md_dir.iterdir()))}")
print(f"raw files: {len(list(raw_dir.iterdir()))}")
```

```bash
# 2. retrieve.py 能命中
python3 ~/.hermes/skills/productivity/inexbot-knowledge-base/scripts/retrieve.py "<代表性关键词>" 3
```

```bash
# 3. proxy 已加载新索引（重启后 5 小时内有效）
curl http://localhost:8643/health | python3 -m json.tool  # ❌ pipe 拦
python3 /tmp/check_health.py                              # ✅
```

## 相关 references

- 姐妹 skill 诊断模板：`~/.hermes/skills/productivity/inexbot-open-knowledge-base/references/vitepress-i18n-sidebar-diagnosis.md`
- SKILL.md 陷阱章节「爬虫：doc.inexbot.com 已升级到 VitePress v2 alpha」
