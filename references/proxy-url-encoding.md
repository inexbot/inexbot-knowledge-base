# 引用链接编码验证（proxy citation URL encoding）

2026-10-25 建立。用于验证 proxy 注入的引用链接**没有双重编码**且**实网可达**。

## 背景

`index.json` 的 key 在两个 KB 里编码形态相反：

| KB | key 形态 | 例子 |
|---|---|---|
| `inexbot` | 已 percent 编码 | `/zh/%E6%8A%80%E6%9C%AF%E8%B5%84%E6%96%99` |
| `inexbot-open` | 明文中文 | `/zh/04.上位机/01.C++/` |

对 `inexbot` 再做一次 `quote()` → `%` 变 `%25` → 双重编码 → 链接 404。

修复见 proxy 的 `_kb_url(base_url, path)`：key 含 `%` 时用 `quote(path, safe="/%")`，
否则用 `quote(path, safe="/")`。

## 三层验证

### 1. 进程内：确认没有 `%25`

```python
import importlib.util, sys
from pathlib import Path

PROXY = Path("/home/ecs-user/hermes-skill-proxy/hermes-skill-proxy.py")
spec = importlib.util.spec_from_file_location("hsp", PROXY)
mod = importlib.util.module_from_spec(spec); sys.modules["hsp"] = mod
spec.loader.exec_module(mod)
mod.load_all_indexes()          # 不调用这个，_doc_scores 是空的，检索返回 []

for kb in ["inexbot", "inexbot-open"]:
    for q in ["冲压工艺手册 参数设置", "示教器 操作手册", "Modbus 功能 使用"]:
        for r in mod.search_single_kb(kb, q, 5):
            assert "%25" not in r["url"], r["url"]
print("no double-encoded URLs")
```

> ⚠️ **必须用 `/usr/bin/python3`**（沙盒 `python3` 没装 flask）。
> ⚠️ **必须先 `load_all_indexes()`**，否则 `_doc_scores` 为空 → `search_single_kb` 返回 `[]`，
> 会误判成「检索坏了」。

### 2. 实网：抽样的 url 全部 200

对 `search_single_kb()` 返回的 `url` 逐条 `curl -o /dev/null -w "%{http_code}" -L`。
期望：全部 200。

### 3. 端到端：POST /v1/chat/completions

```python
payload = json.dumps({
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "冲压工艺手册 参数设置"}],
    "max_tokens": 1,
})
s = subprocess.run(["curl","-s","--max-time","150","-X","POST",
                    "http://127.0.0.1:8643/v1/chat/completions",
                    "-H","Content-Type: application/json","-d",payload],
                   capture_output=True, text=True).stdout
blob = json.dumps(json.loads(s), ensure_ascii=False)
links = list(dict.fromkeys(re.findall(r"https?://doc\.inexbot\.com/zh/[^\s\"'\\)]+", blob)))
```

- `%25` 数量应为 **0**
- 逐条 curl 应全部 200

> ⚠️ **gateway(8642) 偶尔会超时返回空 body**——这是网关侧慢，不是 proxy 检索的问题。
> 脚本要带**重试**（空响应就 sleep 8s 再试，最多 4 次），
> 否则会把「网关抖动」误判成「检索层坏了」。

## 常见误判

| 现象 | 真实原因 |
|---|---|
| `search_single_kb` 返回 `[]` | 忘了 `load_all_indexes()` |
| import 报 `No module named 'flask'` | 用了沙盒 python3，要换 `/usr/bin/python3` |
| `/v1/chat/completions` 返回空 body | gateway 慢，重试即可 |
| 图片链接 404 但文档链接 200 | `assets/*.png` 是带 hash 的静态资源，重命名会失效，属正常 |
