# 大族检索：KB 里几百条同类别条目怎么查（分库导航）

适用场景：KB 某个类别条目数很大（几十到几百条）且**按子品牌 / 子型号分库**存放时，proxy 的 top-5 检索必然只能覆盖前几条，用户问的恰好在第 200 条。比如「伺服报错 339 条」「报警代码一览表」「各品牌驱动错误码」。

先例：`~/.hermes/kb/inexbot/md/` 下 `zh-常见问题-伺服报错-<品牌>-<0x码> -<品牌>.md` 共 339 条，分库：
系统问题 40 / 清能德创 77 / 久同 53 / 迈信 51 / 摩通 43 / 禾川 26 / 新时达 20 / 杰美康 29。

---

## 1. 核心原则：先建"分库索引"，再按码精确定位

proxy 注入的 top-5 是**跨库混排**的，不读完所有分库就无法回答"某品牌某码"。

**步骤 A — 列出全部分库及条目数**（读 `zh-常见问题-伺服报错.md` 这类"总目录页"，它本身就是一个索引）：

```bash
# 总目录页通常直接列出分库和条数
cat ~/.hermes/kb/inexbot/md/zh-常见问题-伺服报错.md
```

**步骤 B — 从目录页拿到品牌清单，再按 `ls` 过滤文件名**：

```bash
ls ~/.hermes/kb/inexbot/md/ | grep -v "久同"        # 先看非目标品牌的规模
ls ~/.hermes/kb/inexbot/md/ | grep "伺服报错-摩通"   # 定位目标分库
```

**步骤 C — 拿到具体文件名后读全文**（一条通常 20–60 行，格式统一：标题 / 原因 / 解决方法）。

---

## 2. ⚠️ 工具陷阱：`search_files` 对中文 KB 正文检索无效

本次实测：`search_files(pattern="报警|故障码|错误码", path=~/.hermes/kb/inexbot/md, target="files")` 返回 **total_count: 0**，而同一目录下明明有几百篇含"报警"的文档。

原因：该参数走的是路径/名称侧的匹配，对**中文正文内容**无匹配能力。

**正确做法**：

| 目的 | 用什么 |
|---|---|
| 按文件名/标题找 | `search_files(pattern="*报警*", target="files")`（glob 走文件名，**有效**） |
| 列出某分库 | `ls <md_root> \| grep "<关键词>"` |
| 在正文里找关键词 | `terminal` 跑 `grep -rn "<关键词>" <md_root> \| head -30` |
| 读全文 | `read_file(path, limit=200)` |

不要因为 `search_files` 返回 0 就断定"KB 没有这条"——那是**工具用法错误**，不是知识盲区。这个区分很重要：前者要写"无法确认"，后者是假的。

---

## 3. 同码多义：`_2.md` 陷阱

同一个 0x 码在**同一品牌下**可能出现多个文件（含义不同）：

```
zh-常见问题-伺服报错-久同-0x0014 - 久同.md
zh-常见问题-伺服报错-久同-0x0014 - 久同_2.md
zh-常见问题-伺服报错-新时达-0x7180 - 新时达.md
zh-常见问题-伺服报错-新时达-0x7180 - 新时达_2.md
```

**必须把 `_2` / `_N` 变体全部读完再回答**，不能只读第一个就下结论。

跨品牌同码含义更是完全不同（`0x0001` 在久同是"超速"，在别的品牌未必同义）——**回答里必须带品牌名**。

---

## 4. 一览表型页面（如星辰二号 Er 码表）

当某分库里有一张"总表"页（几百行、表格形式：代码/名称/原因/处理措施），**它比逐码散页更有价值**，优先读它。

```
zh-常见问题-伺服报错-X02驱控一体柜-星辰二号报警代码一览表.md   # 297 行表格
```

读法：`read_file(path, limit=400)` 分段读；`total_lines` 已知就不会漏。表格里 `z` 是原始爬取残留的列表符号，读的时候按 `z ` 分行拆成多行处理措施。

---

## 5. 回答时必须区分「查到的」和「推断的」

大族检索容易滑向"凭通用伺服经验补全"。铁律：

- 只有**具体读到的条目**才写具体处理措施，并注明是哪个品牌哪个码。
- 品牌/码**没读到原文**就写"该品牌该码未在 KB 中找到对应条目"，**不要**套用另一品牌的措施。
- 一览表里只在"处理措施"列中被顺带提及、没有独立条目的码（如 `ALFA.0`），要注明"KB 中仅在处理措施列被提及，无独立条目"。

---

## 6. 配套：把大族知识固化成 references/

一次性把几百条读完后，**不要**指望下次重新检索。应在 `robotics/robot-control-systems-rd/references/` 下写一份**人工提炼的速查表**（品牌分库计数表 + 高频码处理措施 + 文件命名规律 + KB 盲区声明），SKILL.md 加一行触发指针。

实例：
- [`robot-control-systems-rd/references/alarm-triage-playbook.md`](../../../robotics/robot-control-systems-rd/references/alarm-triage-playbook.md)（伺服报错 339 条分库索引 + 星辰二号 Er 码表 + 报警分诊表）
- [`robot-control-systems-rd/references/servo-alarm-code-full-index.md`](../../../robotics/robot-control-systems-rd/references/servo-alarm-code-full-index.md)（**全量 code→含义对照表** + 溯源链接构造法）

### 6.1 全量索引的生成方法（比逐条 read_file 快一个数量级）

几百条同族条目的 **H1 标题就是「码 - 含义」**，所以**读一遍标题就能建出完整索引**，不必逐条读正文：

```python
import os, re, glob
base = os.path.expanduser("~/.hermes/kb/inexbot/md")
for f in sorted(glob.glob(base + "/zh-常见问题-伺服报错-*.md")):
    name = os.path.basename(f)[len("zh-常见问题-伺服报错-"):-3]
    title = re.search(r"^#\s+(.+)$", open(f).read(), re.M).group(1).strip()
    brand, _, code = name.rpartition("-")
    print(f"{code:14} | {title}")
```

一次 `glob` + 一次正则扫描 ≈ 几百条索引，工具往返只有 1 次；逐条 `read_file` 要几百次往返。

### 6.2 `index.json` → 官方引用链接（批量生成可点击溯源）

`index.json` 的 **key 就是 percent-encoded URL path**，`value.title` 是去零宽字符后的标题。这两样拼起来能**批量产出可点击的 doc.inexbot.com 引用链接**，不必手工拼中文 URL：

```python
import json, urllib.parse
d = json.load(open(os.path.expanduser("~/.hermes/kb/inexbot/index.json")))
for path, v in d.items():
    if v.get("title", "").startswith("0x8611"):
        print(v["title"], "->", "https://doc.inexbot.com" + path)
```

- key 已是 percent-encoded，**直接 `"https://doc.inexbot.com" + path` 即可访问**；要中文可读形式再 `urllib.parse.quote(path, safe="/%")`。
- 按 `title` 匹配码比按 path 匹配可靠 —— path 是 percent-encoded 中文，`grep "伺服报错"` 会 0 命中。
- 同码跨品牌会有多条命中（title 前缀相同），正是「跨品牌同码不同义」的证据来源。

---

## 7. 长手册型主题（几十到几百行整本手册）怎么读

大族是「几百条散页」，另一类是「**一本 300–800 行的操作手册**」（冲压工艺 2.0 手册 636 行、3.0 手册 330 行、JSON 协议工艺章 2183 行）。这类主题的导航法不一样：

**Step 1 — 一次扫 `index.json` 标题，列出该主题的全部页面**

```python
import json, os
for kb in ["/home/ecs-user/.hermes/kb/inexbot", "/home/ecs-user/.hermes/kb/inexbot-open"]:
    d = json.load(open(kb + "/index.json"))
    for k, v in d.items():
        if "冲压" in v.get("title", ""):
            print(kb, "|", v["title"], "|", k)
```

一次遍历（558 / 799 条）就把该主题的**全部**页面 + 官方链接 + md slug 位置列全了，比逐个 read_file 试错快一个数量级。`index.json` 的 value 还带 `content_snippet`（约 4000 字符），可先看片段判断值不值得读全文。

**Step 2 — `wc -l` 确认体量**，再决定读法。

**Step 3 — 分段 `read_file(offset=…, limit=…)`**，或 terminal `sed -n 'a,bp'`。注意 `read_file` 命中同一文件时会返回 `unchanged` 去重，此时先前那次的结果仍在上下文里，直接引用即可。

**Step 4 — 手动构造官方链接**：`https://doc.inexbot.com` + key（open 侧是 `https://open.inexbot.com` + key）。

### 7.1 proxy 注入装不下一本手册

`content_snippet` 上限约 4000–6000 字符，而一本手册动辄 2 万–3 万字符。**凡是需要"逐项参数清单"的问题，proxy 注入一定不够，必须读 md 全文。** 判据：用户问的是「参数怎么设 / 有哪些参数 / 全表」→ 直接走全文路线，不要试图用 snippet 拼。

### 7.2 中文 md 文件名的定位

KB 的 md 文件名是中文，`search_files` 按内容 pattern 检索中文正文**恒返回 0 命中**。定位文件名用：
- `ls ~/.hermes/kb/inexbot/md | grep -E "冲压|工艺"`（文件名 glob 有效）
- 或 Step 1 的 `index.json` 标题扫描（更稳，title 是去零宽字符的干净标题）

### 7.3 多代手册并存的命名规律

同一主题常有多个代次的手册并存（冲压工艺 2.0 / 3.0）。代次通常**只在标题末尾**（`冲压工艺2.0手册` / `冲压工艺3.0手册`），主体名相同 → **按 title 包含匹配，一次列出所有代次**，然后在回答开头先说明「有哪几代并存，参数名不同」，再按代次分节列出。

### 7.4 版本边界要自己核

`index.json` 里有全部页面标题 → 扫一遍就知道某主题手册**只存在于哪个固件版本**（例如冲压工艺手册只有 22.07 版的 2.0 / 3.0 两册，24.03 / 25.01 未收录）。不要默认"最新版本也有"，也不要在别的版本上类推参数名。

---

## 8. 一句话清单

1. 读**总目录页**拿分库清单和条数。
2. `ls | grep` 定位分库 → 精确定位文件名（**不要用 `search_files` 的内容 pattern**）。
3. 同码的 `_N` 变体**全读**。
4. 优先读该分库的**一览表页**。
5. 回答带品牌名 + 官方链接；读不到的明写"未找到对应条目"。
6. 沉淀成 references 速查表，别每次重检索。
7. 建索引时**扫 H1 标题**（一次 glob），别逐条读正文。
8. 溯源链接从 `index.json` 的 key + title **批量生成**。
9. **长手册主题**：先扫 `index.json` 标题一次列全页面 → `wc -l` → 分段读全文 → 按代次分节。proxy 的 4000 字符 snippet 装不下。
10. **多代手册并存**要在答案开头声明；**版本边界**自己用 index 标题核，别默认别的版本也有。
