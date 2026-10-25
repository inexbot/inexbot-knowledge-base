# proxy ↔ crawler slug 契约断裂（2026-10-23 发现，2026-10-24 已修）

> **状态更新（2026-10-24）**：proxy 侧**已修复**并实测验证通过。
> 本文档保留根因与验证方法，因为「改了 crawler 的 `slugify()` 就要来复查」这件事仍然成立。
>
> 实测结果（2026-10-24，`/usr/bin/python3` 跑检索）：
>
> | 查询 | 结果 |
> |---|---|
> | `冲压工艺 手册 参数设置` | 5 条全部 `snippet_len=4000`（正文命中） |
> | `示教器 换图` | 顶层 `snippet_len=4000` |
> | `伺服报警 0x0051 IPM故障` | 无 `OSError`，但顶层 `snippet_len=71`（该页正文本来就只有一行，见下） |
> | `通讯协议 地址码 Modbus 寄存器` | 顶层 `通讯协议与地址码`，`snippet_len=2701` |
>
> 判定标准仍是 **`snippet_len` 远大于 800**（800 = index.json 的摘要兜底，没读到正文）。
> 注意：`0x0051` 这类伺服报错页正文**本来就只有一行**，所以 `snippet_len=71` 是正确的，
> 不是 bug —— 区分「本来就短」和「没读到」要靠对照 `md/` 文件实际大小。

## 一句话（历史根因）

crawler 迁到 VitePress v2 alpha 后改了 md 文件名的 slug 算法，**hermes-skill-proxy 没同步**，
导致 **557/558 个 md 文件解析不到**，其中 **147 条在 `exists()` 处抛未捕获 `OSError`**，整个
`/v1/chat/completions` 请求直接 500。

## 症状（修复前）

调用 proxy 的 `search_all_kb()`：

| 查询 | 结果 |
|---|---|
| 伺服报警 0x0051 IPM故障 | ❌ OSError [Errno 36] |
| 示教器 换图 | ❌ OSError |
| 冲压工艺 手册 参数设置 | ❌ OSError |
| 工业机器人控制器 C1102 | ❌ OSError |
| C2202 嵌入式控制主板 | ⚠️ 不报错，但 snippet_len=800（退回索引摘要，非正文） |

不抛错的那条最危险：**看起来完全正常**，实际正文根本没读到，只是退化成 index.json 里的
800 字 `content_snippet`。LLM 拿到的是摘要而非全文，且没有任何报错线索。

## 根因：两套 slug 算法不一致

**crawler.py（新版，v2 alpha 迁移后）**：

```python
def slugify(text: str, max_len: int = 200) -> str:
    text = unquote(text)                      # ← 先解码 URL 编码
    text = text.strip().replace("/", "-")
    text = re.sub(r'[<>:"\|?*]', "", text)
    if len(text.encode("utf-8")) > max_len:
        head = text.encode("utf-8")[:max_len-16].decode("utf-8", errors="ignore")
        text = head + "-" + md5_text(text)    # ← 超长则 MD5 截断
    return text
```

**hermes-skill-proxy.py `read_full_content()`（旧版，从没同步过）**：

```python
slug  = path.lstrip("/").replace("/", "-")                       # 候选 1：保留 %XX
slug2 = url_quote(path.lstrip("/"), safe="").replace("/", "-")   # 候选 2：再编码一次
md_path = md_dir / f"{slug}.md"
if not md_path.exists():                                          # ← 不在 try 内！
    md_path = md_dir / f"{slug2}.md"
if not md_path.exists():
    return ""
```

三个问题叠加：

1. **两个候选都不含 `unquote`** → 实际文件名是 `zh-常见问题-伺服报错-久同-0x0001 - 久同.md`
   （已解码），proxy 找的是 `zh-%E5%B8%B8...md`（未解码）→ 永远 miss。
2. **候选 2 是 `url_quote` 再编码**——把 `%` 变成 `%25`，离真实文件名更远，且长度爆炸。
3. **`exists()` 未包 try** → 超长文件名抛 `OSError [Errno 36]`，冒泡到
   `search_single_kb` → `search_all_kb` → 500。

## 现在的修法（proxy 侧）

proxy 已改为 `_md_slug_candidates()`：生成多个候选（`unquote` 后的真名、`url_quote` 再编码等），
**谁先存在用谁**，并且 `exists()` 包在 try/except 里（文件名过长等异常一律降级成 `""`，
绝不冒泡成 500）。这样即便某个 crawler 改了 slug 规则也不会全线崩。

## 验证方法

不要只测「不抛异常」——**必须测正文长度**。用 system python（proxy 服务用的那个，
沙盒 `python3` 没装 flask）：

```bash
cp /home/ecs-user/hermes-skill-proxy/hermes-skill-proxy.py /tmp/proxy_mod.py
```

```python
# /tmp/test_proxy_retrieval.py
import importlib.util as _iu
_s = _iu.spec_from_file_location("px", "/tmp/proxy_mod.py")
P = _iu.module_from_spec(_s); _s.loader.exec_module(P)
P.load_all_indexes()
for q in ["伺服报警 0x0051 IPM故障", "示教器 换图", "冲压工艺 手册 参数设置"]:
    for label, items in P.search_all_kb(q).items():
        for it in items:
            print(f"  [{it['score']:.1f}] {it['title'][:38]:40s} snippet_len={len(it['content_snippet'])}")
```

```bash
/usr/bin/python3 /tmp/test_proxy_retrieval.py
```

**判定标准**：`snippet_len` 应远大于 800（正文命中时是 4000 上限量级）。全是 800 = 没修好。

## 教训：跨组件的 slug 算法是隐式契约

crawler 改了 slug 规则，proxy 没跟着改，**两边都不报错、索引照常生成、`/health` 照样返回
`docs=558 loaded=true`**——所有表层健康检查都看不出来。

**任何时候改了 crawler 的 `slugify()`，必须同步检查**：
- `hermes-skill-proxy.py` 的 `_md_slug_candidates()`
- 本 skill 的 `scripts/retrieve.py`（若它自行算 md 路径）
- `scripts/check_crawl_state.py` 里的 `slugify()` 副本
- `scripts/refresh_drift.py`（它 import `crawler.slugify`，会自动跟随）

建议把这几个调用点都收敛到一处（proxy 侧的公共函数），而不是各自复刻。

## ⚠️ 关键：proxy 同时服务两个 KB，修完必须两个都验

`hermes-skill-proxy` 同时检索 `inexbot`（doc.inexbot.com）和 `inexbot-open`
（open.inexbot.com），**共用同一个 `read_full_content()`**。

- 姊妹 KB 修好了，**不代表** `inexbot-open` 也好了 —— 它走完全相同的代码路径
- 两个 KB 的 URL 形态不同，slug 碰撞的表现也不同：`inexbot` 的 URL 长（中文 + URL
  编码混杂，容易超 255 字节触发 `OSError`），`inexbot-open` 的 URL 短且带
  `en-`/`kr-`/`zh-` locale 前缀

**所以「本 skill 的检索验证通过」≠「两个 KB 都正常」。** 统一用一个脚本一次验两个：

```bash
/usr/bin/python3 ~/.hermes/skills/productivity/inexbot-open-knowledge-base/scripts/check_retrieval_chain.py
```

判定标准：`snippet_len` **> 800** = 正文命中；**== 800** = 静默降级成摘要（BUG）；
**< 200** = 该页正文本来就短（如伺服报错页只有一行，不是 bug）。
有降级或 `OSError` → exit 1。

详见姊妹 skill `inexbot-open-knowledge-base/references/retrieval-chain-verification.md`。

## 另一个同源教训：`index.json` 里 `content_snippet` 长度为 0 = 抓到了 404 空壳页

2026-10-24 修的 sitemap `&amp;` bug 就是同一类问题（见 SKILL.md 对应章节）。
`snippet<60ch` 的 132 条里混着「真·占位页」和「抓取失败的空壳页」，
用 `description == 'Not Found'` 区分。

排查该类问题的通用探针（`index.json` 里的 key 是 **URL-encoded**，按中文匹配前
要先 `unquote(key)`，否则一个都匹配不到）：

```python
import json
from pathlib import Path
idx = json.loads(Path.home().joinpath(".hermes/kb/inexbot/index.json").read_text(encoding="utf-8"))
zero     = [k for k, v in idx.items() if len(v.get("content_snippet") or "") == 0]
notfound = [k for k, v in idx.items() if (v.get("description") or "") == "Not Found"]
print("空 snippet:", len(zero), " Not Found:", len(notfound))
```

修完 2026-10-24 实测：`空 snippet: 0, Not Found: 0` —— 该类 bug 已彻底消除。
